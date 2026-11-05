from __future__ import annotations

from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from basiclive.core.acl.conf import settings


def close_connections():
    from basiclive.core.acl import models

    now = timezone.now()
    old = now - timedelta(days=settings.MAX_OPEN_AGE)
    old_connections = models.Access.objects.filter(
        status__in=[models.Access.Status.DISCONNECTED, models.Access.Status.CONNECTED],
        start_time__lt=old
    )
    old_connections.update(status=models.Access.Status.FINISHED)
    old_connections.filter(end_time__isnull=True).update(end_time=now)


class Command(BaseCommand):
    help = 'Closes connections older than MAX_OPEN_AGE that are still open'

    def handle(self, *args, **options):
        close_connections()

