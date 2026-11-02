from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date

from basiclive.core.schedule.providers import get_schedule_provider


class Command(BaseCommand):
    help = "Synchronizes schedule records (modes, beamtime, downtime, support) from the configured ScheduleProvider."

    def add_arguments(self, parser):
        parser.add_argument(
            "--start",
            type=str,
            default=None,
            help="Start date in YYYY-MM-DD format (defaults to Monday of the current week).",
        )
        parser.add_argument(
            "--end",
            type=str,
            default=None,
            help="End date in YYYY-MM-DD format (defaults to start + 28 days).",
        )
        parser.add_argument(
            "--types",
            type=str,
            default=None,
            help="Comma-separated entity types to sync (e.g. modes,beamtime,downtime,support).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Bypass TTL cache and force synchronization.",
        )

    def handle(self, *args, **options):
        provider = get_schedule_provider()
        if not provider:
            self.stdout.write(self.style.WARNING("No SCHEDULE_PROVIDER is configured."))
            return

        today = timezone.localdate()
        default_start = today - timedelta(days=today.weekday())

        start_str = options.get("start")
        if start_str:
            start_date = parse_date(start_str)
            if not start_date:
                raise CommandError(f"Invalid --start date '{start_str}'. Expected YYYY-MM-DD.")
        else:
            start_date = default_start

        end_str = options.get("end")
        if end_str:
            end_date = parse_date(end_str)
            if not end_date:
                raise CommandError(f"Invalid --end date '{end_str}'. Expected YYYY-MM-DD.")
        else:
            end_date = start_date + timedelta(days=28)

        if end_date <= start_date:
            raise CommandError("--end date must be after --start date.")

        types_str = options.get("types")
        types_list = (
            [t.strip() for t in types_str.split(",") if t.strip()]
            if types_str
            else None
        )

        stats = provider.sync(
            start=start_date,
            end=end_date,
            types=types_list,
            force=bool(options.get("force")),
        )
        summary = ", ".join(f"{k}: {v}" for k, v in stats.items())
        self.stdout.write(
            self.style.SUCCESS(
                f"Schedule sync complete for [{start_date} .. {end_date}] ({summary})."
            )
        )
