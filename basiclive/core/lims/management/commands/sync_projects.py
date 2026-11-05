from django.core.management.base import BaseCommand, CommandError

from basiclive.core.lims.models import User
from basiclive.core.lims.providers import get_project_provider


class Command(BaseCommand):
    help = "Synchronizes active and pending Projects and ProjectMembership rosters from the configured ProjectProvider."

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            type=str,
            default=None,
            help="Synchronize projects and memberships for a specific existing username.",
        )

    def handle(self, *args, **options):
        provider = get_project_provider()
        if not provider:
            self.stdout.write(self.style.WARNING("No PROJECT_PROVIDER is configured."))
            return

        username = options.get("user")
        if username:
            user = User.objects.filter(username__iexact=username).first()
            if not user:
                raise CommandError(f"User '{username}' does not exist.")
            provider.sync_user(user, force=True)
            self.stdout.write(
                self.style.SUCCESS(f"Synchronized project memberships for user '{user.username}'.")
            )
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
