from django.core.management.base import BaseCommand

from basiclive.core.lims.providers import get_project_provider


class Command(BaseCommand):
    help = "Synchronizes active and pending Projects and ProjectMembership rosters from the configured ProjectProvider."

    def handle(self, *args, **options):
        provider = get_project_provider()
        if not provider:
            self.stdout.write(self.style.WARNING("No PROJECT_PROVIDER is configured."))
            return

        stats = provider.sync_projects()
        self.stdout.write(
            self.style.SUCCESS(
                f"Project sync complete. Created: {stats['created']}, "
                f"Updated: {stats['updated']}, "
                f"Memberships synced: {stats['memberships_synced']}, "
                f"Memberships removed: {stats['memberships_removed']}."
            )
        )
