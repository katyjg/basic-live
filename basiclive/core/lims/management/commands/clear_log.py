from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from basiclive.core.lims.conf import settings
from basiclive.core.lims.models import ActivityLog


class Command(BaseCommand):
    help = f"Deletes activity older than {settings.KEEP_ACTIVITY_WEEKS} weeks"

    def handle(self, *args, **options):
        # Calculate the cutoff based on settings
        cutoff_date = timezone.now() - timedelta(weeks=settings.KEEP_ACTIVITY_WEEKS)

        # Filter the queryset
        old_entries = ActivityLog.objects.filter(created__lt=cutoff_date)
        count = old_entries.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS("No old entries found to clean up."))
            return

        # Perform the deletion (or your custom logic)
        old_entries.delete()

        # Success message in the console
        self.stdout.write(
            self.style.SUCCESS(f"Deleted {count} entries older than {settings.KEEP_ACTIVITY_WEEKS} weeks.")
        )
