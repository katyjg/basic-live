from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import timezonefinder
from colorfield.fields import ColorField
from django.conf import settings as django_settings
from django.db import models
from django.db.models import F, Sum
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from geopy import geocoders
from model_utils import Choices
from model_utils.models import TimeFramedModel

from basiclive.core.lims.models import Project, Beamline, Stretch
from basiclive.core.schedule.conf import settings
from basiclive.utils.functions import Shifts, ShiftEnd, ShiftStart

tf = timezonefinder.TimezoneFinder()

MIN_SUPPORT_HOUR = settings.MIN_SUPPORT_HOUR
MAX_SUPPORT_HOUR = settings.MAX_SUPPORT_HOUR


class AccessType(models.Model):
    name = models.CharField(blank=True, max_length=30)
    color = ColorField(default="#000000")
    email_subject = models.CharField(max_length=100, verbose_name=_('Email Subject'))
    email_body = models.TextField(blank=True)
    remote = models.BooleanField(_("Remote Access"), default=False)

    class Meta:
        verbose_name = _("Access Type")
        verbose_name_plural = _("Access Types")

    def __str__(self):
        return self.name


class BeamtimeQuerySet(models.QuerySet):
    def with_duration(self):
        return self.annotate(
            duration=Sum(F('end') - F('start')),
            shift_duration=ShiftEnd('end') - ShiftStart('start'),
            shifts=Shifts(F('end') - F('start'))
        )


class BeamtimeManager(models.Manager.from_queryset(BeamtimeQuerySet)):
    use_for_related_fields = True


class FacilityModeType(models.Model):
    code = models.SlugField(max_length=30, unique=True)
    description = models.CharField(blank=True, max_length=60)
    color = ColorField(default="#000000")

    class Meta:
        verbose_name = _("Facility Mode Type")
        verbose_name_plural = _("Facility Mode Types")
        ordering = ["code"]

    def __str__(self):
        return self.description or self.code

    @property
    def css_class(self) -> str:
        return f"mode-{self.code}"


class FacilityMode(TimeFramedModel):
    mode = models.ForeignKey(
        FacilityModeType,
        related_name="intervals",
        on_delete=models.CASCADE,
    )
    comments = models.TextField(blank=True)
    source_id = models.CharField(
        _("External Source ID"),
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
    )

    objects = BeamtimeManager()

    class Meta:
        verbose_name = _("Facility Mode")
        verbose_name_plural = _("Facility Modes")
        ordering = ["start"]

    def __str__(self):
        return f"{self.mode} ({self.start} - {self.end})"


class BeamlineSupport(models.Model):
    staff = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, related_name="support", on_delete=models.CASCADE
    )
    date = models.DateField()

    class Meta:
        verbose_name = _("Beamline Support")
        verbose_name_plural = _("Beamline Support")

    def __str__(self):
        return f"{self.staff.first_name} {self.staff.last_name}".strip() or str(self.staff)

    def active(self):
        now = timezone.localtime()
        return now.date() == self.date and MIN_SUPPORT_HOUR <= now.hour < MAX_SUPPORT_HOUR


class Beamtime(models.Model):
    project = models.ForeignKey(Project, related_name="beamtime", on_delete=models.CASCADE, null=True, blank=True)
    beamline = models.ForeignKey(Beamline, related_name="beamtime", on_delete=models.CASCADE)
    comments = models.TextField(blank=True)
    access = models.ForeignKey(AccessType, related_name="beamtime", on_delete=models.SET_NULL, null=True)
    cancelled = models.BooleanField(default=False)
    start = models.DateTimeField(verbose_name=_('Start'))
    end = models.DateTimeField(verbose_name=_('End'))

    objects = BeamtimeManager()

    class Meta:
        verbose_name = _("Beamtime")
        verbose_name_plural = _("Beamtimes")
        ordering = ['start']

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
        return render_to_string('schedule/beamtime.html', {'bt': self, 'detailed': detailed})

    def notification(self):
        return self.notifications.first()

    def sessions(self):
        return self.project.sessions.filter(beamline=self.beamline).filter(
            pk__in=Stretch.objects.filter(start__lte=self.end, end__gte=self.start).values_list('session__pk', flat=True))

    def name(self):
        name = 'User'
        if self.project and self.project.pi:
            name = self.project.pi.last_name or 'User'
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
        return f"{self.project} on {self.beamline.acronym}"


class Downtime(TimeFramedModel):
    SCOPE_CHOICES = Choices(
        (0, 'FACILITY', _('Facility Downtime')),
        (1, 'BEAMLINE', _('Beamline Maintenance'))
    )
    scope = models.IntegerField(choices=SCOPE_CHOICES, default=SCOPE_CHOICES.FACILITY)
    beamline = models.ForeignKey(Beamline, related_name="downtime", on_delete=models.CASCADE)
    comments = models.TextField(blank=True)

    objects = BeamtimeManager()

    class Meta:
        verbose_name = _("Downtime")
        verbose_name_plural = _("Downtimes")

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

    class Meta:
        verbose_name = _("Email Notification")
        verbose_name_plural = _("Email Notifications")

    def recipient_list(self):
        pi_email = self.beamtime.project.pi.email if (self.beamtime.project and self.beamtime.project.pi) else None
        contact_email = self.beamtime.project.contact_email if self.beamtime.project else None
        return list(filter(None, {pi_email, contact_email}))

    def unsendable(self):
        late = timezone.now() > (self.send_time - timedelta(minutes=30))
        empty = not self.recipient_list()
        return not self.sent and any([late, empty, self.beamtime.cancelled])

    def save(self, *args, **kwargs):
        # Get user's local timezone
        if not self.pk:
            try:
                proj = self.beamtime.project
                addr_parts = [proj.city, proj.region.name if proj.region else None, proj.country.name if proj.country else None]
                address = ", ".join(p for p in addr_parts if p)
                _, (latitude, longitude) = locator.geocode(address)
                usertz = tf.certain_timezone_at(lat=latitude, lng=longitude)
                tz = ZoneInfo(usertz) if usertz else timezone.get_current_timezone()
            except Exception:
                tz = timezone.get_current_timezone()
            t = self.beamtime.start - timedelta(days=7 + (self.beamtime.start.weekday() > 4 and self.beamtime.start.weekday() - 4 or 0))
            self.send_time = timezone.make_aware(datetime(year=t.year, month=t.month, day=t.day, hour=10), timezone=tz)
            self.email_subject = self.beamtime.info_subject()
            self.email_body = self.beamtime.info_body()

        super().save(*args, **kwargs)
