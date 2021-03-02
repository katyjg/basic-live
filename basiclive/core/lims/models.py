import copy
import hashlib
import json
import mimetypes
import os
from collections import OrderedDict, defaultdict
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q, F, Count, CharField, BooleanField, Value, Sum
from django.db.models.functions import Coalesce, Concat
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import ugettext as _

from memoize import memoize
from model_utils import Choices
from model_utils.models import TimeStampedModel

from basiclive.utils.data import parse_frames, frame_ranges
from basiclive.utils.encrypt import encrypt
from basiclive.utils.functions import ShiftEnd, ShiftStart

IDENTITY_FORMAT = '-%y%m'
RESTRICT_DOWNLOADS = getattr(settings, 'RESTRICT_DOWNLOADS', False)
SHIFT_HRS = getattr(settings, 'HOURS_PER_SHIFT', 8)
SHIFT_SECONDS = SHIFT_HRS * 3600

MAX_CONTAINER_DEPTH = getattr(settings, 'MAX_CONTAINER_DEPTH', 2)
SAMPLE_PORT_FIELDS = [
                         "container{}__location__name".format("__".join([""] + (["parent"] * i)))
                         for i in reversed(range(MAX_CONTAINER_DEPTH))
                     ] + ['location__name']

CONTAINER_PORT_FIELDS = [
    "{}location__name".format("__".join((["parent"] * i) + [""]))
    for i in reversed(range(MAX_CONTAINER_DEPTH))
]

DRAFT = 0
SENT = 1
ON_SITE = 2
LOADED = 3
RETURNED = 4
ACTIVE = 5
PROCESSING = 6
COMPLETE = 7
ARCHIVED = 9
TRASHED = 10

GLOBAL_STATES = Choices(
    (0, 'DRAFT', _('Draft')),
    (1, 'SENT', _('Sent')),
    (2, 'ON_SITE', _('On-site')),
    (3, 'LOADED', _('Loaded')),
    (4, 'RETURNED', _('Returned')),
    (5, 'ACTIVE', _('Active')),
    (6, 'PROCESSING', _('Processing')),
    (7, 'COMPLETE', _('Complete')),
    (9, 'ARCHIVED', _('Archived')),
    (10, 'TRASHED', _('Trashed'))
)


class OrphanSample(object):
    def __init__(self):
        self.name = ""
        self.orphaned_datasets = []
        self.orphaned_reports = []


class Beamline(models.Model):
    """
    A Beamline object should be created for every unique facility that will be uploading data or reports,
    or has its own automounter layout.
    """
    name = models.CharField(max_length=600)
    acronym = models.CharField(max_length=50)
    energy_lo = models.FloatField(default=4.0)
    energy_hi = models.FloatField(default=18.5)
    contact_phone = models.CharField(max_length=60)
    automounters = models.ManyToManyField('Container', through='Automounter', through_fields=('beamline', 'container'))
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.acronym

    def active_session(self):
        """
        Returns the session that is currently running on the beamline, if there is one.
        """
        return self.sessions.filter(pk__in=Stretch.objects.active().values_list('session__pk')).first()

    def active_automounter(self):
        """
        Returns the first active automounter pointing to the beamline. Generally, there should be
        only one active automounter referencing each beamline at any given time.
        """
        return self.layouts.filter(active=True).first()


class Carrier(models.Model):
    """
    A Carrier object should be created for each courier company that may be used for shipping to the beamline.
    To link to shipment tracking, provide a URL that can be completed using a tracking number to link to a
    courier-specific tracking page.
    """

    name = models.CharField(max_length=60)
    url = models.URLField()

    def __str__(self):
        return self.name


class ProjectType(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class ProjectDesignation(TimeStampedModel):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Project(AbstractUser):
    HELP = {
        'contact_person': _("Full name of contact person"),
    }
    name = models.SlugField()
    contact_person = models.CharField(max_length=200, blank=True, null=True)
    contact_email = models.EmailField(max_length=100, blank=True, null=True)
    carrier = models.ForeignKey(Carrier, blank=True, null=True, on_delete=models.SET_NULL)
    account_number = models.CharField(max_length=50, blank=True, null=True)
    department = models.CharField(max_length=600, blank=True, null=True)
    address = models.CharField(max_length=600, blank=True, null=True)
    city = models.CharField(max_length=180, blank=True, null=True)
    province = models.CharField(max_length=180, blank=True, null=True)
    postal_code = models.CharField(max_length=30, blank=True, null=True)
    country = models.CharField(max_length=180, blank=True, null=True)
    contact_phone = models.CharField(max_length=60, blank=True, null=True)
    contact_fax = models.CharField(max_length=60, blank=True, null=True)
    organisation = models.CharField(max_length=600, blank=True, null=True)
    show_archives = models.BooleanField(default=True)
    key = models.TextField(blank=True)
    kind = models.ForeignKey(ProjectType, blank=True, null=True, on_delete=models.SET_NULL,
                             verbose_name=_("Project Type"))
    alias = models.CharField(max_length=20, blank=True, null=True)
    designation = models.ManyToManyField(ProjectDesignation, verbose_name=_("Project Designation"), blank=True)
    created = models.DateTimeField(_('date created'), auto_now_add=True, editable=False)
    modified = models.DateTimeField(_('date modified'), auto_now=True, editable=False)
    updated = models.BooleanField(default=False)

    def __str__(self):
        return self.name.upper()

    def get_absolute_url(self):
        return reverse('user-detail', kwargs={'username': self.username})

    def onsite_containers(self):
        return self.containers.filter(status=Container.STATES.ON_SITE).count()

    def label_hash(self):
        return self.name

    def active_status(self):
        try:
            if not self.sessions.count():
                return 'New'
            if self.last_session() >= (timezone.localtime() - timedelta(days=365)):
                return 'Active'
        except TypeError:
            return 'Active'
        return 'Idle'

    def last_session(self):
        session = self.sessions.first()
        return session.created if session else None

    def save(self, *args, **kwargs):
        if not self.kind:
            self.kind = ProjectType.objects.first()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = _("Project Account")


class SSHKey(TimeStampedModel):
    name = models.CharField(max_length=60)
    key = models.TextField()
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="sshkeys")

    class Meta:
        verbose_name = "SSH Key"

    def fingerprint(self):
        import hashlib
        fp = hashlib.md5(self.key.encode()).hexdigest()
        return ':'.join(a + b for a, b in zip(fp[::2], fp[1::2]))


class StretchQuerySet(models.QuerySet):

    def active(self, extras=None):
        if extras is None:
            extras = {}
        return self.filter(end__isnull=True, **extras)

    def recent(self, extras=None):
        if extras is None:
            extras = {}
        recently = timezone.now() - timedelta(minutes=5)
        return self.filter(end__gte=recently, **extras)

    def recent_days(self, days):
        recently = timezone.now() - timedelta(days=days)
        return self.filter(Q(end__isnull=True) | Q(end__gte=recently))

    def with_duration(self):
        return self.annotate(
            duration=Coalesce('end', timezone.now()) - F('start'),
            shift_duration=ShiftEnd(Coalesce('end', timezone.now())) - ShiftStart('start')
        )


class StretchManager(models.Manager.from_queryset(StretchQuerySet)):
    use_for_related_fields = True


class ProjectObjectManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related('project')


class SessionQuerySet(models.QuerySet):
    def with_duration(self):
        return self.annotate(
            duration=Sum(
                Coalesce('stretches__end', timezone.now()) - F('stretches__start')
            ),
            shift_duration=Sum(
                ShiftEnd(Coalesce('stretches__end', timezone.now())) - ShiftStart('stretches__start')
            ),
        )


class SessionManager(models.Manager.from_queryset(SessionQuerySet)):
    use_for_related_fields = True

    def get_queryset(self):
        return super().get_queryset().select_related('project')


class Session(models.Model):
    created = models.DateTimeField(_('date created'), auto_now_add=True, editable=False)
    name = models.CharField(max_length=100)
    project = models.ForeignKey(Project, related_name="sessions", on_delete=models.CASCADE)
    beamline = models.ForeignKey(Beamline, related_name="sessions", on_delete=models.CASCADE)
    comments = models.TextField()
    url = models.CharField(max_length=200, null=True)

    objects = SessionManager()

    class Meta:
        ordering = ('-created',)

    def __str__(self):
        return '{}-{}'.format(self.project.name.upper(), self.name)

    def identity(self):
        return 'SES-{:07,d}'.format(self.id).replace(',', '-')

    def download_url(self):
        return '{}/{}.tar.gz'.format(self.url, self.name)

    def feedback_key(self):
        return encrypt("{user}:{name}".format(user=self.project.username, name=self.name))

    def launch(self):
        Stretch.objects.active(extras={'session__beamline': self.beamline}).exclude(session=self).update(
            end=timezone.now())
        self.stretches.recent().update(end=None)
        stretch = self.stretches.active().last() or Stretch.objects.create(session=self, start=timezone.now())
        return stretch

    def close(self):
        self.stretches.active().update(end=timezone.now())

    def groups(self):
        return Group.objects.filter(samples__datasets__session=self, project=self.project).distinct()

    def reports(self):
        return self.project.reports.filter(data__session=self).distinct()

    def orphans(self):
        samples = defaultdict(OrphanSample)
        for data in self.datasets.filter(sample__isnull=True).all():
            samples[data.name].name = data.name
            samples[data.name].orphaned_datasets.append(data)
            samples[data.name].orphaned_reports.extend(data.reports.all())

        return list(samples.values())

    def num_datasets(self):
        return self.datasets.count()

    num_datasets.short_description = _("Datasets")

    def num_reports(self):
        return self.reports().count()

    num_reports.short_description = _("Reports")

    def samples(self):
        return self.project.samples.filter(datasets__session=self).distinct()

    @memoize(60)
    def is_active(self):
        return self.stretches.active().exists()

    @memoize(60)
    def is_recent(self):
        return self.end() >= (timezone.now() - timedelta(days=7))

    def shifts(self):
        total = self.stretches.with_duration().aggregate(time=Sum('shift_duration'))
        return total['time'].total_seconds() / SHIFT_SECONDS

    def shift_parts(self):
        shifts = set()
        for stretch in self.stretches.all():
            st = timezone.localtime(stretch.start) - timedelta(hours=timezone.localtime(stretch.start).hour % SHIFT_HRS,
                                                               minutes=stretch.start.minute,
                                                               seconds=stretch.start.second)
            end = timezone.localtime(stretch.end) if stretch.end else timezone.now()
            et = end - timedelta(hours=end.hour % SHIFT_HRS, minutes=end.minute, seconds=end.second)
            shifts.add(st)
            while st < et:
                st += timedelta(hours=SHIFT_HRS)
                shifts.add(st)
            return len(shifts)

    @memoize(60)
    def total_time(self):
        """
        Returns total time the session was active, in hours
        """
        total = self.stretches.with_duration().aggregate(time=Sum('duration'))

        return total['time'].total_seconds() / 3600

    total_time.short_description = _("Duration")

    @memoize(60)
    def start(self):
        return timezone.localtime(self.stretches.earliest('start').start)

    @memoize(60)
    def end(self):
        return timezone.localtime(self.stretches.latest('start').end or timezone.localtime())

    @memoize(60)
    def last_record_time(self):
        last_data = self.datasets.last()
        return last_data.modified if last_data else self.created

    def gaps(self):
        data = list(self.datasets.order_by('start_time'))
        max_gap = timedelta(minutes=10)

        return [
            (
                timezone.localtime(first.end_time),
                timezone.localtime(second.start_time),
                (second.start_time - first.end_time)
            )
            for first, second in zip(data[:-1], data[1:]) if (second.start_time - first.end_time) > max_gap
        ]


class Stretch(models.Model):
    start = models.DateTimeField(null=False, blank=False)
    end = models.DateTimeField(null=True, blank=True)
    session = models.ForeignKey(Session, related_name='stretches', on_delete=models.CASCADE)
    objects = StretchManager()

    class Meta:
        verbose_name = _("Beamline Usage")
        verbose_name_plural = _("Beamline Usage")
        ordering = ['-start', ]


class ProjectObjectMixin(models.Model):
    """ STATES/TRANSITIONS define a finite state machine (FSM) for the Shipment (and other
    models.Model instances also defined in this file).

    STATES: an Enum specifying all of the valid states for instances of Shipment.

    TRANSITIONS: a dict specifying valid state transitions. the keys are starting STATES and the
        values are lists of valid final STATES.
     """

    STATES = GLOBAL_STATES
    TRANSITIONS = {
        STATES.DRAFT: [STATES.SENT, STATES.ON_SITE],
        STATES.SENT: [STATES.ON_SITE, STATES.DRAFT],
        STATES.ON_SITE: [STATES.SENT, STATES.RETURNED],
        STATES.LOADED: [STATES.ON_SITE],
        STATES.RETURNED: [STATES.ARCHIVED, STATES.ON_SITE],
        STATES.ACTIVE: [STATES.PROCESSING, STATES.COMPLETE, STATES.ARCHIVED],
        STATES.PROCESSING: [STATES.COMPLETE, STATES.ARCHIVED],
        STATES.COMPLETE: [STATES.ACTIVE, STATES.PROCESSING, STATES.ARCHIVED],
    }

    name = models.CharField(max_length=60)
    staff_comments = models.TextField(blank=True, null=True)
    created = models.DateTimeField(_('date created'), auto_now_add=True, editable=False)
    modified = models.DateTimeField(_('date modified'), auto_now=True, editable=False)

    class Meta:
        abstract = True

    def __str__(self):
        return self.name

    def is_editable(self):
        return self.status == self.STATES.DRAFT

    def is_deletable(self):
        return self.status == self.STATES.DRAFT

    def is_closable(self):
        return self.status == self.STATES.RETURNED

    def has_comments(self):
        return '*' if self.comments or self.staff_comments else None

    def delete(self, *args, **kwargs):
        if self.is_deletable:
            super().delete(*args, **kwargs)

    def archive(self, request=None):
        if self.is_closable():
            self.change_status(self.STATES.ARCHIVED)

    def send(self, request=None):
        self.change_status(self.STATES.SENT)

    def unsend(self, request=None):
        self.change_status(self.STATES.DRAFT)

    def unreturn(self, request=None):
        self.change_status(self.STATES.ON_SITE)

    def unreceive(self, request=None):
        self.change_status(self.STATES.SENT)

    def receive(self, request=None):
        self.change_status(self.STATES.ON_SITE)

    def load(self, request=None):
        self.change_status(self.STATES.LOADED)

    def unload(self, request=None):
        self.change_status(self.STATES.ON_SITE)

    def returned(self, request=None):
        self.change_status(self.STATES.RETURNED)

    def trash(self, request=None):
        self.change_status(self.STATES.TRASHED)

    def change_status(self, status):
        if status == self.status:
            return
        if status not in self.TRANSITIONS[self.status]:
            raise ValueError("Invalid transition on '{}.{}':  '{}' -> '{}'".format(
                self.__class__, self.pk, self.STATES[self.status], self.STATES[status]))
        self.status = status
        self.save()

    def add_comments(self, message):
        if self.staff_comments:
            if self.staff_comments not in message:
                self.staff_comments += ' ' + message
        else:
            self.staff_comments = message
        self.save()


class TransitStatusMixin(ProjectObjectMixin):
    STATUS_CHOICES = Choices(
        (ProjectObjectMixin.STATES.DRAFT, 'DRAFT', _('Draft')),
        (ProjectObjectMixin.STATES.SENT, 'SENT', _('Sent')),
        (ProjectObjectMixin.STATES.ON_SITE, 'ON_SITE', _('On-site')),
        (ProjectObjectMixin.STATES.RETURNED, 'RETURNED', _('Returned')),
        (ProjectObjectMixin.STATES.ARCHIVED, 'ARCHIVED', _('Archived'))
    )
    status = models.IntegerField(choices=STATUS_CHOICES, default=ProjectObjectMixin.STATES.DRAFT)

    class Meta:
        abstract = True


class ActiveStatusMixin(ProjectObjectMixin):
    STATUS_CHOICES = (
        (ProjectObjectMixin.STATES.ACTIVE, _('Active')),
        (ProjectObjectMixin.STATES.ARCHIVED, _('Archived')),
        (ProjectObjectMixin.STATES.TRASHED, _('Trashed'))
    )
    TRANSITIONS = copy.deepcopy(ProjectObjectMixin.TRANSITIONS)
    TRANSITIONS[ProjectObjectMixin.STATES.ACTIVE] = [ProjectObjectMixin.STATES.TRASHED,
                                                     ProjectObjectMixin.STATES.ARCHIVED]
    TRANSITIONS[ProjectObjectMixin.STATES.ARCHIVED] = [ProjectObjectMixin.STATES.TRASHED]

    status = models.IntegerField(choices=STATUS_CHOICES, default=ProjectObjectMixin.STATES.ACTIVE)

    def is_closable(self):
        return self.status not in [ProjectObjectMixin.STATES.ARCHIVED, ProjectObjectMixin.STATES.TRASHED]

    class Meta:
        abstract = True


class Shipment(TransitStatusMixin):
    HELP = {
        'name': _("This should be an externally visible label"),
        'carrier': _("Select the company handling this shipment. To change the default option, edit your profile."),
        'cascade': _('containers and samples (along with groups, datasets and results)'),
        'cascade_help': _('All associated containers will be left without a shipment')
    }
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='shipments')
    comments = models.TextField(blank=True, null=True, max_length=200)
    tracking_code = models.CharField(blank=True, null=True, max_length=60)
    return_code = models.CharField(blank=True, null=True, max_length=60)
    date_shipped = models.DateTimeField(null=True, blank=True)
    date_received = models.DateTimeField(null=True, blank=True)
    date_returned = models.DateTimeField(null=True, blank=True)
    carrier = models.ForeignKey(Carrier, null=True, blank=True, on_delete=models.SET_NULL, related_name='projects')
    storage_location = models.CharField(max_length=60, null=True, blank=True)

    objects = ProjectObjectManager()

    def identity(self):
        return 'SHP-{:07,d}'.format(self.id).replace(',', '-')

    def get_absolute_url(self):
        return reverse('shipment-detail', kwargs={'pk': self.id})

    def groups_by_priority(self):
        return self.groups.order_by('priority')

    def barcode(self):
        return self.tracking_code or self.name

    def num_containers(self):
        return self.containers.count()

    def num_samples(self):
        return self.containers.aggregate(sample_count=Count('samples'))['sample_count']

    def datasets(self):
        return self.project.datasets.filter(sample__container__shipment__pk=self.pk)

    def num_datasets(self):
        return self.datasets().count()

    def reports(self):
        return self.project.reports.filter(data__sample__container__shipment__pk=self.pk)

    def num_reports(self):
        return self.reports().count()

    def is_sendable(self):
        return self.status == self.STATES.DRAFT and not self.shipping_errors()

    def is_receivable(self):
        return self.status == self.STATES.SENT

    def is_returnable(self):
        return self.status == self.STATES.ON_SITE

    def has_labels(self):
        return self.status <= self.STATES.SENT and (self.num_containers() or self.components.filter(label=True))

    def is_processed(self):
        # if all groups in shipment are complete, then it is a processed shipment.
        group_list = Group.objects.filter(shipment__get_container_list=self)
        for container in self.containers.all():
            for group in container.get_group_list():
                if group not in group_list:
                    group_list.append(group)
        for group in group_list:
            if group.is_reviewable():
                return False
        return True

    def is_processing(self):
        return self.project.samples.filter(container__shipment__exact=self).filter(
            Q(pk__in=self.project.datasets.values('sample')) |
            Q(pk__in=self.project.result_set.values('sample'))).exists()

    def add_component(self):
        return self.status <= self.STATES.SENT

    def label_hash(self):
        # use dates of project, shipment, and each container within to determine
        # when contents were last changed
        txt = str(self.project) + str(self.project.modified) + str(self.modified)
        for container in self.containers.all():
            txt += str(container.modified)
        h = hashlib.new('ripemd160')  # no successful collision attacks yet
        h.update(txt)
        return h.hexdigest()

    def shipping_errors(self):
        """ Returns a list of descriptive string error messages indicating the Shipment is not
            in a 'shippable' state
        """
        errors = []
        if self.num_containers() == 0:
            errors.append(_("No Containers"))
        if not self.num_samples():
            errors.append(_("No Samples in any Container"))
        return errors

    def groups(self):
        return self.groups.order_by('-priority')

    def requests(self):
        return self.project.requests.filter(Q(groups__shipment=self) | Q(samples__group__shipment=self)).distinct()

    def sample_requests(self):
        return self.project.requests.filter(samples__group__shipment=self)

    def receive(self, request=None):
        self.date_received = timezone.now()
        self.save()
        for obj in self.containers.all():
            obj.receive(request=request)
        super(Shipment, self).receive(request=request)

    def send(self, request=None):
        if self.is_sendable():
            self.date_shipped = timezone.now()
            self.save()
            for obj in self.containers.all():
                obj.send(request=request)
            self.groups.all().update(status=Group.STATES.ACTIVE)
            self.requests().update(status=Request.STATUS_CHOICES.PENDING)
            super(Shipment, self).send(request=request)

    def unsend(self, request=None):
        if self.status == self.STATES.SENT:
            self.date_shipped = None
            self.status = self.STATES.DRAFT
            self.save()
            for obj in self.containers.all():
                obj.unsend()
            self.groups.all().update(status=Group.STATES.DRAFT)
            self.requests().update(status=Request.STATUS_CHOICES.DRAFT)

    def unreturn(self, request=None):
        if self.status == self.STATES.RETURNED:
            self.date_shipped = None
            self.status = self.STATES.ON_SITE
            self.save()
            for obj in self.containers.all():
                obj.unreturn()

    def unreceive(self, request=None):
        if self.status == self.STATES.ON_SITE:
            self.date_received = None
            self.status = self.STATES.SENT
            self.save()
            for obj in self.containers.all():
                obj.unreceive()

    def returned(self, request=None):
        if self.is_returnable():
            self.date_returned = timezone.now()
            self.save()
            self.containers.all().update(parent=None, location="")
            LoadHistory.objects.filter(child__in=self.containers.all()).active().update(end=timezone.now())
            for obj in self.containers.all():
                obj.returned(request=request)
            super(Shipment, self).returned(request=request)

    def archive(self, request=None):
        for obj in self.containers.all():
            obj.archive(request=request)
        super(Shipment, self).archive(request=request)


class ComponentType(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class Component(models.Model):
    shipment = models.ForeignKey(Shipment, related_name="components", on_delete=models.CASCADE)
    kind = models.ForeignKey(ComponentType, on_delete=models.CASCADE)


class ContainerType(models.Model):
    """
    A ContainerType should be defined for each container that has a unique layout. (e.g. Uni-Puck, Adaptor, Autmounter, etc.)

    :param envelope: 'rect' or 'circle' are supported.
        If 'rect', location__name lists are assumed to be [x, y] coordinates relative to width and height.
        If 'circle', location__name value lists are assumed to be polar coordinates [r, theta], relative to width.
    :param radius: radius of the circle (in range(0,100)) to draw for each location.
    :param height: provides the aspect ratio of the envelope, relative to a default width of 1.
    """
    STATES = Choices(
        (0, 'PENDING', _('Pending')),
        (1, 'LOADED', _('Loaded')),
    )
    ENVELOPES = Choices(
        ('rect', 'RECT', _('Rectangle')),
        ('circle', 'CIRCLE', _('Circle')),
        ('list', 'LIST', _('List'))
    )
    TRANSITIONS = {
        STATES.PENDING: [STATES.LOADED],
        STATES.LOADED: [STATES.PENDING],
    }
    name = models.CharField(max_length=20)
    height = models.FloatField(default=1.0)
    radius = models.FloatField(default=8.0)
    envelope = models.CharField(max_length=200, blank=True, choices=ENVELOPES)
    active = models.BooleanField("User option", default=False)

    def __str__(self):
        return self.name


class ContainerLocation(models.Model):
    name = models.CharField(max_length=5)
    accepts = models.ManyToManyField(ContainerType, blank=True, related_name="acceptors")
    kind = models.ForeignKey(ContainerType, on_delete=models.CASCADE, null=True, related_name="locations")
    x = models.FloatField(default=0.0)
    y = models.FloatField(default=0.0)

    def __str__(self):
        return self.name


class ContainerQuerySet(models.QuerySet):
    def with_port(self):
        return self.annotate(port_name=Concat(*CONTAINER_PORT_FIELDS))


class ContainerManager(models.Manager.from_queryset(ContainerQuerySet)):
    def get_queryset(self):
        return super().get_queryset().select_related('kind', 'project', 'location').with_port()


class Container(TransitStatusMixin):
    HELP = {
        'name': _("A visible label on the container. If there is a barcode on the container, scan it here"),
    }
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='containers')
    kind = models.ForeignKey(ContainerType, blank=False, null=False, on_delete=models.CASCADE,
                             related_name='containers')
    shipment = models.ForeignKey(Shipment, blank=True, null=True, on_delete=models.SET_NULL, related_name='containers')
    comments = models.TextField(blank=True, null=True)
    priority = models.IntegerField(default=0)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, blank=True, null=True, related_name="children")
    location = models.ForeignKey(ContainerLocation, blank=True, null=True, on_delete=models.SET_NULL,
                                 related_name='contents')
    objects = ContainerManager()

    class Meta:
        unique_together = (
            ("project", "name", "shipment"),
        )
        ordering = ('kind', 'location', 'name')

    def __str__(self):
        return "{} | {} | {}".format(self.kind.name.title(), self.project.name.upper(), self.name)

    def identity(self):
        return 'CNT-{:07,d}'.format(self.id).replace(',', '-')

    def get_absolute_url(self):
        return reverse('container-detail', kwargs={'pk': self.id})

    def barcode(self):
        return self.name

    def num_samples(self):
        return self.samples.count()

    def aspect_ratio(self):
        return 100.0 * (self.kind.height or 1.0)

    def capacity(self):
        return self.kind.locations.count()

    def has_children(self):
        return self.children.count() > 0

    @memoize(3600)
    def accepts_children(self):
        return self.kind.locations.filter(accepts__isnull=False).exists()

    def accepted_by(self):
        return ContainerType.objects.filter(pk__in=self.kind.locations.values_list('contents', flat=True))

    def children_by_location(self):
        return self.children.order_by('location')

    def is_assigned(self):
        return self.shipment is not None

    def groups(self):
        groups = set([])
        for sample in self.samples.all():
            for group in sample.groups.all():
                groups.add('%s-%s' % (group.project.name, group.name))
        return ', '.join(groups)

    def get_group_list(self):
        groups = list()
        for sample in self.samples.all():
            if sample.group not in groups:
                groups.append(sample.group)
        return groups

    @memoize(timeout=60)
    def automounter(self):
        return self.beamlines.filter(active=True).first() or self.parent and self.parent.automounter() or None

    def port(self):
        if hasattr(self, 'port_name'):  # fetch from default annotation
            return self.port_name
        elif self.parent and self.location:
            return "{}{}".format(self.parent.port(), self.location.name)
        return ""

    def get_project(self):
        if self.children.count():
            return '/'.join(set(self.children.values_list('project__username', flat=True)))
        return self.project

    def get_location_name(self):
        return None if not (self.parent and self.location) else self.location.name

    def placeholders(self):
        """
        Generate a list of container locations that can hold samples or samples contained in the container.
        """
        samples = {s.location: s for s in self.samples.select_related('location', 'group').all()}
        return [
            {
                'location': loc
            } if loc not in samples else samples[loc]
            for loc in self.kind.locations.order_by('pk')
        ]

    def get_layout(self, with_samples=True):
        """
        Generate a nested dictionary of data representing the hierarchy of containers and samples
        :param with_samples: Whether to include sample information or not
        :return: dictionary
        """

        locations = list(
            self.kind.locations.values(
                'x', 'y', loc=F('name'), num_accepts=Count('accepts')
            )
        )
        layout = {
            'type': self.kind.name,
            'id': self.pk,
            'name': self.name,
            'parent': None if not self.parent else self.parent.pk,
            'owner': self.project.name.upper(),
            'height': self.kind.height,
            'url': self.get_absolute_url(),
            'loc': self.get_location_name(),
            'envelope': self.kind.envelope,
            'accepts': self.accepts_children(),
            'port': self.port()
        }

        contents = {}
        if self.children.exists():
            contents = {
                info['loc']: info
                for child in self.children.all()
                for info in [child.get_layout()]
                if info['loc']
            }
        elif not layout['accepts']:
            layout['final'] = True
            # only try fetch samples if container does not accept other containers
            if with_samples:
                samples = list(
                    self.samples.values(
                        'id', 'name', loc=F('location__name'), sample=Value(True, BooleanField()),
                        batch=F('group__pk'), envelope=Value('circle', CharField()),
                        started=Count('datasets')
                    )
                )

                contents = {
                    info['loc']: info
                    for info in samples
                    if info['loc']
                }

        # compile data
        for loc in locations:
            key = loc['loc']
            loc['radius'] = self.kind.radius
            loc['accepts'] = bool(loc.pop('num_accepts'))
            loc['parent'] = self.pk
            loc.update(contents.get(key, {}))
        layout['children'] = list(locations)

        return layout


class LoadHistory(models.Model):
    start = models.DateTimeField(auto_now_add=True, editable=False)
    end = models.DateTimeField(null=True, blank=True)
    child = models.ForeignKey(Container, null=False, blank=False, related_name='parent_history',
                              on_delete=models.CASCADE)
    parent = models.ForeignKey(Container, null=False, blank=False, related_name='children_history',
                               on_delete=models.CASCADE)
    location = models.ForeignKey(ContainerLocation, blank=True, null=True, on_delete=models.SET_NULL)

    objects = StretchManager()

    class Meta:
        ordering = ['-start', ]

    def __str__(self):
        return '{}|{}|{}|{}'.format(self.child, self.parent, self.start, self.end)


class Automounter(models.Model):
    """
    A through-model relating a Beamline object to a Container object. The container referenced here should be the
    one that samples or containers can be added to during a Project's beamtime. If a beamline has multiple possible
    containers (ie. Automounter objects), only the current one should be marked 'active'.
    """
    beamline = models.ForeignKey(Beamline, on_delete=models.CASCADE, related_name="layouts")
    container = models.ForeignKey(Container, on_delete=models.CASCADE, related_name="beamlines")
    staff_comments = models.TextField(blank=True, null=True)
    modified = models.DateTimeField('date modified', auto_now=True, editable=False)
    active = models.BooleanField(default=False)

    def __str__(self):
        return "{} | {}".format(self.beamline.acronym, self.container.name)

    def identity(self):
        return 'ATM-{:07,d}'.format(self.id).replace(',', '-')

    def json_dict(self):
        return {
            'project_id': self.project.pk,
            'id': self.pk,
            'name': self.beamline.name,
            'comments': self.staff_comments,
            'container': [container.pk for container in self.children.all()]
        }


REQUEST_SPEC_SCHEMA = {
    "title": "Request Type Schema",
    "type": "object",
    "propertyNames": {
        "pattern": r"^[^\d\W]\w*\Z$"
    },
    "additionalProperties": { "$ref": "#/definitions/field"},
    "definitions": {
        "field": {
            "title": "Request Type Specification",
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "description": "Human-readable label*"
                },
                "type": {
                    "type": "string",
                    "enum": ["string", "boolean", "number", "json"],
                    "description": "Type"
                },
                "choices": {
                    "type": "array",
                    "description": "Choices (comma-separated list)",
                    "items": { "$ref": "#/definitions/choice" },
                    "uniqueItems": True
                },
                "required": {"type": "boolean", "default": False},
            },
            "required": ["label", "type"]
        },
        "choice": {
            "type": "array",
            "items": [
                {"type": "string"},
                {"type": "string"}
            ],
            "additionalItems": False
        }
    }
}


class RequestType(models.Model):
    SCOPES = Choices(
        ('ONE_SAMPLE', _('Single Sample')),
        ('ONE_GROUP', _('Single Group')),
        ('SAMPLES', _('Multiple samples')),
        ('GROUPS', _('Multiple groups')),
        ('UNLIMITED', _('Unlimited')),
    )

    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    scope = models.CharField(max_length=15, default=SCOPES.UNLIMITED)
    edit_template = models.CharField(max_length=100, default="requests/base-edit.html")
    view_template = models.CharField(max_length=100, default="")
    spec = models.JSONField(blank=True)
    layout = models.JSONField(blank=True, default=list)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    def field_styles(self):
        layout = {k: v for row in self.layout for k, v in row if k in self.spec.keys()}
        layout.update({k: 'hidden' for k in self.spec.keys() if k not in layout.keys()})
        return layout


class Request(ProjectObjectMixin):
    STATUS_CHOICES = Choices(
        (0, 'DRAFT', _('Draft')),
        (1, 'PENDING', _('Pending')),
        (2, 'COMPLETE', _('Complete')),
    )

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='requests')
    kind = models.ForeignKey(RequestType, on_delete=models.CASCADE, related_name='requests')
    status = models.IntegerField(choices=STATUS_CHOICES, default=STATUS_CHOICES.DRAFT)
    parameters = models.JSONField(blank=True, null=True)
    comments = models.TextField(blank=True, null=True)
    priority = models.IntegerField(blank=True, null=True)
    samples = models.ManyToManyField('Sample', blank=True, related_name='requests')
    groups = models.ManyToManyField('Group', blank=True, related_name='requests')

    objects = ProjectObjectManager()

    class Meta:
        verbose_name = _('Request')
        ordering = ['priority']

    def identity(self):
        return 'REQ-{:07,d}'.format(self.id).replace(',', '-')

    def parameter_labels(self):
        parameters = self.parameters or {}
        p = {self.kind.spec.get(k, {}).get('label') or k: v for k, v in parameters.items() if v not in [None, '']}
        return p

    def shipment(self):
        group = self.groups.first()
        sample = self.samples.first()
        return group and group.shipment or sample and sample.container.shipment or None

    def num_samples(self):
        return len(self.sample_list())

    def sample_list(self):
        samples = list(self.samples.all())
        for group in self.groups.all():
            samples += list(group.samples.all())
        return list(set(samples))

    def json_dict(self):
        return {
            'project_id': self.project.pk,
            'id': self.pk,
            'kind_id': self.kind.pk,
            'kind_name': self.kind.name,
            'name': self.name,
            'comments': self.comments,
            'parameters': self.parameters
        }


class Group(ProjectObjectMixin):
    STATUS_CHOICES = (
        (ProjectObjectMixin.STATES.DRAFT, _('Draft')),
        (ProjectObjectMixin.STATES.ACTIVE, _('Active')),
        (ProjectObjectMixin.STATES.PROCESSING, _('Processing')),
        (ProjectObjectMixin.STATES.COMPLETE, _('Complete')),
        (ProjectObjectMixin.STATES.ARCHIVED, _('Archived'))
    )

    TRANSITIONS = copy.deepcopy(ProjectObjectMixin.TRANSITIONS)
    TRANSITIONS[ProjectObjectMixin.STATES.DRAFT] = [ProjectObjectMixin.STATES.ACTIVE]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='sample_groups')
    status = models.IntegerField(choices=STATUS_CHOICES, default=ProjectObjectMixin.STATES.DRAFT)
    shipment = models.ForeignKey(Shipment, null=True, blank=True, on_delete=models.SET_NULL, related_name='groups')
    comments = models.TextField(blank=True, null=True)
    priority = models.IntegerField(blank=True, null=True)

    objects = ProjectObjectManager()

    class Meta:
        verbose_name = _('Group')
        unique_together = (
            ("project", "name", "shipment"),
        )
        ordering = ['priority']

    def identity(self):
        return 'GRP-{:07,d}'.format(self.id).replace(',', '-')

    def get_absolute_url(self):
        return reverse('group-detail', kwargs={'pk': self.id})

    def num_samples(self):
        return self.samples.count()

    def all_requests(self):
        return self.project.requests.filter(Q(groups=self) | Q(samples__group=self)).distinct()

    def complete(self):
        return not self.samples.filter(collect_status=False).exists()

    def is_closable(self):
        return self.samples.all().exists() and not self.samples.exclude(
            status__in=[Sample.STATES.RETURNED, Sample.STATES.ARCHIVED]).exists() and \
               self.status != self.STATES.ARCHIVED

    def archive(self, request=None):
        for obj in self.samples.exclude(status__exact=Sample.STATES.ARCHIVED):
            obj.archive(request=request)
        super(Group, self).archive(request=request)


def get_sample_path(instance, filename):
    return os.path.join('uploads/', 'samples', filename)


class SampleQuerySet(models.QuerySet):
    def with_port(self):
        return self.annotate(port_name=Concat(*SAMPLE_PORT_FIELDS))


class SampleManager(models.Manager.from_queryset(SampleQuerySet)):
    def get_queryset(self):
        return super().get_queryset().select_related('group', 'location', 'container', 'project').with_port()


class Sample(ProjectObjectMixin):
    HELP = {
        'name': _("Avoid using spaces or special characters in sample names"),
        'barcode': _("If there is a data-matrix code on sample, please scan or input the value here"),
    }
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='samples')
    barcode = models.SlugField(null=True, blank=True)
    container = models.ForeignKey(Container, null=True, blank=True, on_delete=models.CASCADE, related_name='samples')
    location = models.ForeignKey(ContainerLocation, on_delete=models.CASCADE, related_name='samples', null=True, blank=True)
    comments = models.TextField(blank=True, null=True)
    collect_status = models.BooleanField(default=False)
    priority = models.IntegerField(null=True, blank=True)
    group = models.ForeignKey(Group, null=True, blank=True, on_delete=models.SET_NULL, related_name='samples')
    image = models.ImageField(blank=True, upload_to=get_sample_path)

    objects = SampleManager()

    class Meta:
        unique_together = (
            ("container", "location"),
        )
        ordering = ['group__priority', 'priority', 'container__name', 'location__pk', 'name']

    def get_absolute_url(self):
        return reverse('sample-detail', kwargs={'pk': self.id})

    def identity(self):
        return 'SPL-{:07,d}'.format(self.id).replace(',', '-')

    def automounter(self):
        return self.container.automounter()

    def reports(self):
        return AnalysisReport.objects.filter(project=self.project, data__sample=self)

    def all_requests(self):
        return list(self.requests.all()) + list(self.group.requests.all())

    def port(self):
        if hasattr(self, 'port_name'):  # fetch from default annotation
            return self.port_name
        elif self.container and self.location:
            return "{}{}".format(self.container.port(), self.location.name)
        return ""

    def is_editable(self):
        return self.container.status == self.container.STATES.DRAFT

    def delete(self, *args, **kwargs):
        if self.is_deletable:
            if self.group and self.group.samples.count() == 1:
                self.group.delete(*args, **kwargs)
            super().delete(*args, **kwargs)


class FrameField(models.TextField):
    description = _("List of frames")

    def get_prep_value(self, value):
        if value is None or isinstance(value, str):
            return value
        else:
            try:
                value = isinstance(json.loads(value), list) and json.loads(value)
            except:
                pass
            if isinstance(value, list):
                val_str = ",".join([r[0] == r[1] and "{}".format(r[0]) or "{}-{}".format(r[0], r[1])
                                    for r in list(frame_ranges(value))])
                return val_str
        return value

    def from_db_value(self, value, expression, connection):
        if value is None or isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                v = json.loads(value)
                if isinstance(v, list):
                    return v
            except Exception:
                pass
            return parse_frames(value)
        return value


class DataTypeManager(models.Manager):
    def get_by_natural_key(self, acronym):
        return self.get(acronym=acronym)


class DataType(models.Model):
    name = models.CharField(max_length=20)
    acronym = models.SlugField(unique=True)
    description = models.TextField()
    template = models.CharField(max_length=100)
    metadata = models.JSONField(default=list)

    objects = DataTypeManager()

    def natural_key(self):
        return self.acronym,

    def __str__(self):
        return self.name


class DataManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related('kind', 'project')


class Data(ActiveStatusMixin):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='datasets')
    group = models.ForeignKey(Group, null=True, blank=True, on_delete=models.SET_NULL, related_name='datasets')
    sample = models.ForeignKey(Sample, null=True, blank=True, on_delete=models.SET_NULL, related_name='datasets')
    session = models.ForeignKey(Session, null=True, blank=True, on_delete=models.SET_NULL, related_name='datasets')
    start_time = models.DateTimeField(null=True, blank=False)
    end_time = models.DateTimeField(null=True, blank=False)
    file_name = models.CharField(max_length=200, null=True, blank=True)
    frames = FrameField(null=True, blank=True)
    num_frames = models.IntegerField(_("Frame Count"), default=1)
    frames_per_file = models.IntegerField(_("Maximum Frames per File"), default=1)
    exposure_time = models.FloatField(null=True, blank=True)
    attenuation = models.FloatField(default=0.0)
    energy = models.DecimalField(decimal_places=4, max_digits=10)
    beamline = models.ForeignKey(Beamline, on_delete=models.PROTECT, related_name='datasets')
    beam_size = models.FloatField(null=True, blank=True)
    url = models.CharField(max_length=200)
    kind = models.ForeignKey(DataType, on_delete=models.PROTECT, related_name='datasets', null=True)
    download = models.BooleanField(default=False)
    meta_data = models.JSONField(default=dict)

    objects = DataManager()

    class Meta:
        verbose_name = _('Dataset')
        ordering = ['created', ]

    def __str__(self):
        return '%s (%d)' % (self.name, self.num_frames)

    def identity(self):
        return 'DAT-{:07,d}'.format(self.id).replace(',', '-')

    def get_absolute_url(self):
        return reverse('data-detail', kwargs={'pk': self.id})

    def download_url(self):
        return "{}/{}.tar.gz".format(self.url, self.name)

    def frame_sets(self):
        if isinstance(self.frames, list):
            val_str = ",".join([r[0] == r[1] and "{}".format(r[0]) or "{}-{}".format(r[0], r[1])
                                for r in list(frame_ranges(self.frames))])
            return val_str
        return self.frames

    def first_frame(self):
        return 1 if not len(self.frames) else self.frames[0]

    def first_file(self):
        return self.file_name.format(self.first_frame())

    def snapshot_url(self):
        return "{}/{}.png".format(self.url, self.name)

    def get_meta_data(self):
        return OrderedDict([(k, self.meta_data.get(k)) for k in self.kind.metadata if k in self.meta_data])

    def report(self):
        return self.reports.first()

    def total_angle(self):
        return float(self.meta_data.get('delta_angle', 0)) * self.num_frames

    def archive(self, request=None):
        for obj in self.reports.all():
            if obj.status not in [GLOBAL_STATES.ARCHIVED, GLOBAL_STATES.TRASHED]:
                obj.archive(request=request)
        super(Data, self).archive(request=request)

    def trash(self, request=None):
        for obj in self.reports.all():
            if obj.status not in [GLOBAL_STATES.TRASHED]:
                obj.trash(request=request)
        super(Data, self).trash(request=request)


class AnalysisReport(ActiveStatusMixin):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='reports')
    kind = models.CharField(max_length=100)
    score = models.FloatField(_("Analysis Report Score"), null=True, default=0.0)
    data = models.ManyToManyField(Data, blank=True, related_name="reports")
    url = models.CharField(max_length=200)
    details = models.JSONField(default=list)

    objects = ProjectObjectManager()

    class Meta:
        ordering = ['created', '-score']

    def download_url(self):
        dataset = self.data.first()
        return '{}/{}-report-{}.tar.gz'.format(self.url, dataset.name, self.pk)

    def identity(self):
        return 'RPT-{:07,d}'.format(self.id).replace(',', '-')

    def label(self):
        if 'MX' in self.kind:
            if 'Anom' in self.kind:
                return 'ANO'
            elif 'Merg' in self.kind:
                return 'MRG'
            elif 'MAD' in self.kind:
                return 'MAD'
            elif 'Screen' in self.kind:
                return 'SCR'
            else:
                return 'NAT'
        return self.kind[:3].upper()

    def get_absolute_url(self):
        return reverse('report-detail', kwargs={'pk': self.id})

    def sessions(self):
        return self.project.sessions.filter(pk__in=self.data.values_list('session__pk', flat=True)).distinct()


class ActivityLogManager(models.Manager):
    def log_activity(self, request, obj, action_type, description=''):
        e = self.model()
        if obj is None:
            try:
                project = request.user
                e.project_id = project.pk
            except Project.DoesNotExist:
                pass

        else:
            if getattr(obj, 'project', None) is not None:
                e.project_id = obj.project.pk
            elif getattr(request, 'project', None) is not None:
                e.project_id = request.project.pk
            elif isinstance(obj, Project):
                e.project_id = obj.pk

            e.object_id = obj.pk
            e.affected_item = obj
            e.content_type = ContentType.objects.get_for_model(obj)
        try:
            e.user = request.user
            e.user_description = request.user.username
        except:
            e.user_description = _("System")
        e.ip_number = request.META['REMOTE_ADDR']
        e.action_type = action_type
        e.description = description
        if obj is not None:
            e.object_repr = '%s: %s' % (obj.__class__.__name__.upper(), obj)
        else:
            e.object_repr = 'N/A'
        e.save()

    def last_login(self, request):
        logs = self.filter(user__exact=request.user, action_type__exact=ActivityLog.TYPE.LOGIN)
        if logs.count() > 1:
            return logs[1]
        else:
            return None


class ActivityLog(models.Model):
    TYPE = Choices(
        (0, 'LOGIN', _('Login')),
        (1, 'LOGOUT', _('Logout')),
        (2, 'TASK', _('Task')),
        (3, 'CREATE', _('Create')),
        (4, 'MODIFY', _('Modify')),
        (5, 'DELETE', _('Delete')),
        (6, 'ARCHIVE', _('Archive'))
    )
    created = models.DateTimeField(_('Date/Time'), auto_now_add=True, editable=False)
    project = models.ForeignKey(Project, blank=True, null=True, on_delete=models.SET_NULL)
    user = models.ForeignKey(Project, blank=True, null=True, related_name='activities', on_delete=models.SET_NULL)
    user_description = models.CharField(_('User name'), max_length=60, blank=True, null=True)
    ip_number = models.GenericIPAddressField(_('IP Address'))
    object_id = models.PositiveIntegerField(blank=True, null=True)
    content_type = models.ForeignKey(ContentType, blank=True, null=True, on_delete=models.SET_NULL)
    affected_item = GenericForeignKey('content_type', 'object_id')
    action_type = models.IntegerField(choices=TYPE)
    object_repr = models.CharField(_('Entity'), max_length=200, blank=True, null=True)
    description = models.TextField(blank=True)

    objects = ActivityLogManager()

    class Meta:
        ordering = ('-created',)

    def __str__(self):
        return str(self.created)


def get_storage_path(instance, filename):
    return os.path.join('uploads/', 'links', filename)


DOCUMENT_MIME_TYPES = [
    'application/x-abiword', 'text/csv', 'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/epub+zip', 'application/vnd.oasis.opendocument.presentation',
    'application/vnd.oasis.opendocument.spreadsheet', 'application/vnd.oasis.opendocument.text',
    'application/pdf', 'application/vnd.ms-powerpoint', 'application/rtf', 'text/plain', 'application/vnd.visio',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation', 'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
]


class Guide(TimeStampedModel):
    TYPE = Choices(
        ('snippet', _('Text')),
        ('video', _('Video')),
        ('image', _('Image')),
    )
    title = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    priority = models.IntegerField(null=False, default=0)
    attachment = models.FileField(blank=True, upload_to=get_storage_path)
    staff_only = models.BooleanField(default=False)
    kind = models.CharField(_("Content Type"), max_length=20, default=TYPE.snippet, choices=TYPE)
    modal = models.BooleanField(default=False)
    url = models.CharField(_("URL or Resource"), max_length=200, blank=True, null=True)

    def has_document(self):
        if self.attachment:
            mime, encoding = mimetypes.guess_type(self.attachment.url)
            return mime in DOCUMENT_MIME_TYPES

    def has_image(self):
        if self.attachment:
            mime, encoding = mimetypes.guess_type(self.attachment.url)
            return mime.startswith('image')

    def has_video(self):
        if self.attachment:
            mime, encoding = mimetypes.guess_type(self.attachment.url)
            return mime.startswith('video')

    def __str__(self):
        return self.title

    class Meta:
        ordering = ("-staff_only", "priority",)
