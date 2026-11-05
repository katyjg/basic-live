from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from basiclive.core.lims.conf import settings
from basiclive.core.lims.models import (
    ActivityLog,
    AnalysisReport,
    Beamline,
    Data,
    Session,
    Stretch,
)

try:
    from basiclive.core.crm.models import Feedback
except (ImportError, RuntimeError):
    Feedback = None


class Command(BaseCommand):
    help = "Cleans expired simulated sessions, datasets, stretches, and analysis reports."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help=f"Lifetime threshold in days (default: {settings.SIMULATED_SESSION_LIFETIME_DAYS}).",
        )
        parser.add_argument(
            "--beamline",
            type=str,
            default=None,
            help="Filter cleanup to a specific simulated beamline acronym.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Output candidate records that would be removed without modifying the database.",
        )
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Skip confirmation prompt when run in non-interactive environments.",
        )

    def handle(self, *args, **options):
        days = options.get("days")
        if days is None:
            days = settings.SIMULATED_SESSION_LIFETIME_DAYS

        if days < 0:
            raise CommandError("Days threshold must be non-negative.")

        cutoff_date = timezone.now() - timedelta(days=days)

        beamlines = Beamline.objects.filter(simulated=True)
        beamline_filter = options.get("beamline")
        if beamline_filter:
            beamline_match = Beamline.objects.filter(acronym=beamline_filter).first()
            if not beamline_match:
                raise CommandError(f"Beamline '{beamline_filter}' does not exist.")
            if not beamline_match.simulated:
                raise CommandError(f"Beamline '{beamline_filter}' is not a simulated beamline.")
            beamlines = beamlines.filter(pk=beamline_match.pk)

        # 1. Target Sessions
        sessions = Session.objects.filter(beamline__in=beamlines, created__lt=cutoff_date)
        session_ids = list(sessions.values_list("id", flat=True))

        # 2. Target Stretches
        target_stretches = Stretch.objects.filter(session_id__in=session_ids)
        stretch_count = target_stretches.count()

        # 3. Target Datasets (datasets belonging to candidate sessions + orphan datasets on simulated beamlines)
        target_datasets = Data.objects.filter(
            Q(session_id__in=session_ids)
            | Q(beamline__in=beamlines, session__isnull=True, created__lt=cutoff_date)
        )
        target_dataset_ids = list(target_datasets.values_list("id", flat=True))

        # 4. Target AnalysisReports
        # A report is purged if all of its associated datasets belong to the purged set
        candidate_reports = AnalysisReport.objects.filter(data__id__in=target_dataset_ids).distinct()
        reports_with_external_data = candidate_reports.filter(
            data__id__in=Data.objects.exclude(id__in=target_dataset_ids).values("id")
        ).values_list("id", flat=True)
        reports_to_delete = candidate_reports.exclude(id__in=reports_with_external_data)
        report_ids_to_delete = list(reports_to_delete.values_list("id", flat=True))

        # 5. Target CRM Feedback
        target_feedback = None
        feedback_count = 0
        if Feedback:
            target_feedback = Feedback.objects.filter(session_id__in=session_ids)
            feedback_count = target_feedback.count()

        # 6. Target ActivityLog entries
        session_ct = ContentType.objects.get_for_model(Session)
        data_ct = ContentType.objects.get_for_model(Data)
        report_ct = ContentType.objects.get_for_model(AnalysisReport)

        target_logs = ActivityLog.objects.filter(
            (Q(content_type=session_ct, object_id__in=session_ids))
            | (Q(content_type=data_ct, object_id__in=target_dataset_ids))
            | (Q(content_type=report_ct, object_id__in=report_ids_to_delete))
        )
        log_count = target_logs.count()

        session_count = len(session_ids)
        dataset_count = len(target_dataset_ids)
        report_count = len(report_ids_to_delete)

        # Dry-run handling
        if options.get("dry_run"):
            self.stdout.write(
                self.style.WARNING(
                    f"[DRY RUN] Simulated session cleanup preview (cutoff: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}, lifetime: {days} days):"
                )
            )
            self.stdout.write(f"  Sessions to delete: {session_count}")
            self.stdout.write(f"  Session Stretches to delete: {stretch_count}")
            self.stdout.write(f"  Datasets to delete: {dataset_count}")
            self.stdout.write(f"  Analysis Reports to delete: {report_count}")
            if Feedback:
                self.stdout.write(f"  CRM Feedback entries to delete: {feedback_count}")
            self.stdout.write(f"  Activity Log entries to delete: {log_count}")
            return

        # Nothing to clean
        if session_count == 0 and dataset_count == 0:
            self.stdout.write(self.style.SUCCESS("No expired simulated sessions or records found."))
            return

        # Interactive confirmation
        if not options.get("no_input"):
            confirm = input(
                f"This will permanently delete {session_count} session(s), {dataset_count} dataset(s), "
                f"{report_count} analysis report(s), and related records older than {days} days.\n"
                "Are you sure you want to proceed? [y/N]: "
            )
            if confirm.strip().lower() not in ("y", "yes"):
                self.stdout.write(self.style.NOTICE("Operation cancelled."))
                return

        # Perform atomic deletion
        with transaction.atomic():
            if log_count > 0:
                target_logs.delete()
            if target_feedback is not None and feedback_count > 0:
                target_feedback.delete()
            if report_count > 0:
                reports_to_delete.delete()
            if dataset_count > 0:
                target_datasets.delete()
            if session_count > 0:
                sessions.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully cleaned expired simulated records older than {days} days:\n"
                f"  - {session_count} Sessions\n"
                f"  - {stretch_count} Stretches\n"
                f"  - {dataset_count} Datasets\n"
                f"  - {report_count} Analysis Reports\n"
                f"  - {feedback_count} CRM Feedback entries\n"
                f"  - {log_count} Activity Log entries"
            )
        )
