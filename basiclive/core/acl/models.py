import os
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from model_utils import Choices

if settings.LIMS_USE_SCHEDULE:
    from basiclive.core.schedule.models import Beamtime
    HOURS_PER_SHIFT = getattr(settings, 'HOURS_PER_SHIFT', 8)


def get_storage_path(instance, filename):
    return os.path.join('uploads/', 'links', filename)


class AccessList(models.Model):
    name = models.CharField(max_length=60, unique=True)
    description = models.TextField(blank=True, null=True)
    address = models.GenericIPAddressField()
    users = models.ManyToManyField("lims.Project", blank=True)
    active = models.BooleanField(default=False)
    created = models.DateTimeField('date created', auto_now_add=True, editable=False)
    modified = models.DateTimeField('date modified', auto_now_add=True, editable=False)
    beamline = models.ManyToManyField("lims.Beamline", blank=True, related_name="access_lists")

    def allowed_users(self):
        return ' | '.join(self.users.values_list('username', flat=True))

    def current_users(self):
        return ' | '.join(self.connections.filter(status__in=['Connected', 'Disconnected']).values_list('user__username', flat=True).distinct())

    def scheduled_users(self):
        return ' | '.join(self.scheduled())

    def scheduled(self):
        if settings.LIMS_USE_SCHEDULE:
            now = timezone.localtime()
            return list(Beamtime.objects.filter(cancelled=False, access__remote=True, beamline__in=self.beamline.all(),
                                                start__lte=now,
                                                end__gte=now - timedelta(hours=int(HOURS_PER_SHIFT / 2))).values_list(
                'project__username', flat=True))
        return []

    def access_users(self):
        users = list(self.users.values_list('username', flat=True))
        if settings.LIMS_USE_SCHEDULE:
            users += self.scheduled()
        return users

    def identity(self):
        return self.name

    def __str__(self):
        return str(self.name)

    class Meta:
        verbose_name = "Access List"


class Access(models.Model):
    STATES = Choices(
        ('CONNECTED', 'Connected'),
        ('DISCONNECTED', 'Disconnected'),
        ('FAILED', 'Failed'),
        ('FINISHED', 'Finished'),
    )
    name = models.CharField(max_length=48)
    user = models.ForeignKey("lims.Project", on_delete=models.CASCADE)
    userlist = models.ForeignKey(AccessList, related_name="connections", on_delete=models.CASCADE)
    status = models.CharField(max_length=20)
    created = models.DateTimeField('date created', auto_now_add=True, editable=True)
    end = models.DateTimeField('date ended', null=True, blank=True)

    def is_active(self):
        return self.status in ['Connected', 'Disconnected']

    def total_time(self):
        end = self.end or timezone.now()
        return (end - self.created).total_seconds()/3600.
    total_time.short_description = "Duration"
