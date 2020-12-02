from django.db import models
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from django.utils import timezone
from django.template.loader import render_to_string
from model_utils import Choices
from model_utils.models import TimeFramedModel
from django.db.models import F, Sum
from basiclive.utils.functions import Shifts, ShiftEnd, ShiftStart

from colorfield.fields import ColorField
from datetime import datetime, timedelta

from basiclive.core.lims.models import Project, Beamline, Stretch

from geopy import geocoders
import timezonefinder, pytz

tf = timezonefinder.TimezoneFinder()

MIN_SUPPORT_HOUR = getattr(settings, 'MIN_SUPPORT_HOUR', 0)
MAX_SUPPORT_HOUR = getattr(settings, 'MAX_SUPPORT_HOUR', 24)
APP_NAME = getattr(settings, 'APP_NAME', 'basiclive')

class AccessType(models.Model):
    name = models.CharField(blank=True, max_length=30)
    color = ColorField(default="#000000")
    email_subject = models.CharField(max_length=100, verbose_name=_('Email Subject'))
    email_body = models.TextField(blank=True)
    remote = models.BooleanField(_("Remote Access"), default=False)

    def __str__(self):
        return self.name


class FacilityMode(models.Model):
    kind = models.CharField(max_length=30)
    description = models.CharField(blank=True, max_length=60)
    color = ColorField(default="#000000")

    def __str__(self):
        return self.kind

    def css_classes(self):
        return [k.strip() for k in self.kind.split(',')]


class BeamlineSupport(models.Model):
    staff = models.ForeignKey(Project, related_name="support", on_delete=models.CASCADE)
    date = models.DateField()

    def __str__(self):
        return "{} {}".format(self.staff.first_name, self.staff.last_name)

    def active(self):
        now = timezone.localtime()
        return now.date() == self.date and MIN_SUPPORT_HOUR <= now.hour < MAX_SUPPORT_HOUR


class BeamtimeQuerySet(models.QuerySet):
    def with_duration(self):
        return self.annotate(
            duration=Sum(F('end') - F('start')),
            shift_duration=ShiftEnd('end') - ShiftStart('start'),
            shifts=Shifts(F('end') - F('start'))
        )


class BeamtimeManager(models.Manager.from_queryset(BeamtimeQuerySet)):
    use_for_related_fields = True


class Beamtime(models.Model):
    project = models.ForeignKey(Project, related_name="beamtime", on_delete=models.CASCADE, null=True, blank=True)
    beamline = models.ForeignKey(Beamline, related_name="beamtime", on_delete=models.CASCADE)
    comments = models.TextField(blank=True)
    access = models.ForeignKey(AccessType, related_name="beamtime", on_delete=models.SET_NULL, null=True)
    cancelled = models.BooleanField(default=False)
    start = models.DateTimeField(verbose_name=_('Start'))
    end = models.DateTimeField(verbose_name=_('End'))

    objects = BeamtimeManager()

    @property
    def start_time(self):
        return datetime.strftime(timezone.localtime(self.start), '%Y-%m-%dT%H')

    @property
    def end_time(self):
        return datetime.strftime(timezone.localtime(self.end), '%Y-%m-%dT%H')

    @property
    def start_times(self):
        st = self.start
        slot = settings.HOURS_PER_SHIFT
        start_times = []
        while st < self.end:
            start_times.append(datetime.strftime(timezone.localtime(st), '%Y-%m-%dT%H'))
            st += timedelta(hours=slot)

        return start_times

    @property
    def local_contact(self):
        dt = max(self.start.date(), timezone.localtime().date())
        return BeamlineSupport.objects.filter(date=dt).first()

    def display(self, detailed=False):
        return render_to_string('schedule/templates/schedule/beamtime.html', {'bt': self, 'detailed': detailed})

    def notification(self):
        return self.notifications.first()

    def sessions(self):
        return self.project.sessions.filter(beamline=self.beamline).filter(
            pk__in=Stretch.objects.filter(start__lte=self.end, end__gte=self.start).values_list('session__pk', flat=True))

    def name(self):
        name = 'User'
        if self.project:
            name = self.project.contact_person or '{person.first_name} {person.last_name}'.format(person=self.project)
        return name

    def start_date_display(self):
        return datetime.strftime(timezone.localtime(self.start), '%A, %B %-d')

    def start_time_display(self):
        return datetime.strftime(timezone.localtime(self.start), '%-I%p')

    def format_info(self):
        return {
            'name': self.name(),
            'beamline': self.beamline.acronym,
            'start_date': self.start_date_display(),
            'start_time': self.start_time_display()
        }

    def info_subject(self):
        return self.access.email_subject.format(**self.format_info())

    def info_body(self):
        return self.access.email_body.format(**self.format_info())

    def __str__(self):
        return "{} on {}".format(self.project, self.beamline.acronym)


class Downtime(TimeFramedModel):
    SCOPE_CHOICES = Choices(
        (0, 'FACILITY', _('Facility Downtime')),
        (1, 'BEAMLINE', _('Beamline Maintenance'))
    )
    scope = models.IntegerField(choices=SCOPE_CHOICES, default=SCOPE_CHOICES.FACILITY)
    beamline = models.ForeignKey(Beamline, related_name="downtime", on_delete=models.CASCADE)
    comments = models.TextField(blank=True)

    objects = BeamtimeManager()

    @property
    def start_time(self):
        return datetime.strftime(timezone.localtime(self.start), '%Y-%m-%dT%H')

    @property
    def end_time(self):
        return datetime.strftime(timezone.localtime(self.end), '%Y-%m-%dT%H')

    @property
    def start_times(self):
        st = self.start
        slot = settings.HOURS_PER_SHIFT
        start_times = []
        while st < self.end:
            start_times.append(datetime.strftime(timezone.localtime(st), '%Y-%m-%dT%H'))
            st += timedelta(hours=slot)

        return start_times


class EmailNotification(models.Model):
    beamtime = models.ForeignKey(Beamtime, related_name="notifications", on_delete=models.CASCADE)
    email_subject = models.CharField(max_length=100, verbose_name=_('Email Subject'))
    email_body = models.TextField(blank=True)
    send_time = models.DateTimeField(verbose_name=_('Send Time'), null=True)
    sent = models.BooleanField(default=False)

    def recipient_list(self):
        return list(set([e for e in [self.beamtime.project.email, self.beamtime.project.contact_email] if e]))

    def unsendable(self):
        late = timezone.now() > (self.send_time - timedelta(minutes=30))
        empty = not self.recipient_list()
        return not self.sent and any([late, empty, self.beamtime.cancelled])

    def save(self, *args, **kwargs):
        # Get user's local timezone
        if not self.pk:
            try:
                locator = geocoders.Nominatim(user_agent=APP_NAME)
                address = "{user.city}, {user.province}, {user.country}".format(user=self.beamtime.project)
                _, (latitude, longitude) = locator.geocode(address)
                usertz = tf.certain_timezone_at(lat=latitude, lng=longitude) or settings.TIME_ZONE
            except:
                usertz = settings.TIME_ZONE
            t = self.beamtime.start - timedelta(days=7 + (self.beamtime.start.weekday() > 4 and self.beamtime.start.weekday() - 4 or 0))
            self.send_time = pytz.timezone(usertz).localize(datetime(year=t.year, month=t.month, day=t.day, hour=10))
            self.email_subject = self.beamtime.info_subject()
            self.email_body = self.beamtime.info_body()

        super().save(*args, **kwargs)
