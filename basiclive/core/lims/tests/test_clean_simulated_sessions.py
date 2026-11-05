import io
from datetime import timedelta
from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from basiclive.core.crm.models import Feedback
from basiclive.core.lims.models import (
    ActivityLog,
    AnalysisReport,
    Beamline,
    Data,
    DataType,
    Project,
    Session,
    Stretch,
    User,
)


class CleanSimulatedSessionsCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.org")
        self.project = Project.objects.create(name="test-project", pi=self.user)
        self.data_type = DataType.objects.create(name="MX", description="Macromolecular")

        self.sim_beamline = Beamline.objects.create(
            name="Simulated Station",
            acronym="SIM-01",
            active=True,
            simulated=True,
        )
        self.sim_beamline_2 = Beamline.objects.create(
            name="Simulated Station 2",
            acronym="SIM-02",
            active=True,
            simulated=True,
        )
        self.prod_beamline = Beamline.objects.create(
            name="Production Station",
            acronym="PROD-01",
            active=True,
            simulated=False,
        )

    def _create_session(self, beamline, name, days_ago, is_active=False):
        session = Session.objects.create(
            project=self.project,
            beamline=beamline,
            name=name,
        )
        created_time = timezone.now() - timedelta(days=days_ago)
        Session.objects.filter(pk=session.pk).update(created=created_time)
        session.refresh_from_db()

        # Add a stretch
        stretch = Stretch.objects.create(
            session=session,
            start=created_time,
            end=None if is_active else created_time + timedelta(hours=2),
        )
        return session, stretch

    def _create_dataset(self, session, beamline, name, days_ago):
        data = Data.objects.create(
            project=self.project,
            session=session,
            beamline=beamline,
            kind=self.data_type,
            name=name,
            url=f"/data/{name}",
        )
        created_time = timezone.now() - timedelta(days=days_ago)
        Data.objects.filter(pk=data.pk).update(created=created_time)
        data.refresh_from_db()
        return data

    def test_age_filtering_and_production_isolation(self):
        # Expired simulated session (>30 days)
        old_sim_sess, _ = self._create_session(self.sim_beamline, "old-sim", days_ago=40)
        old_sim_data = self._create_dataset(old_sim_sess, self.sim_beamline, "data-old-sim", days_ago=40)

        # Recent simulated session (<30 days)
        recent_sim_sess, _ = self._create_session(self.sim_beamline, "recent-sim", days_ago=10)
        recent_sim_data = self._create_dataset(recent_sim_sess, self.sim_beamline, "data-recent-sim", days_ago=10)

        # Expired production session (>30 days) - must NEVER be touched
        old_prod_sess, _ = self._create_session(self.prod_beamline, "old-prod", days_ago=50)
        old_prod_data = self._create_dataset(old_prod_sess, self.prod_beamline, "data-old-prod", days_ago=50)

        out = io.StringIO()
        call_command("clean_simulated_sessions", no_input=True, stdout=out)

        # Expired simulated session and data are purged
        self.assertFalse(Session.objects.filter(pk=old_sim_sess.pk).exists())
        self.assertFalse(Data.objects.filter(pk=old_sim_data.pk).exists())

        # Recent simulated session and data remain
        self.assertTrue(Session.objects.filter(pk=recent_sim_sess.pk).exists())
        self.assertTrue(Data.objects.filter(pk=recent_sim_data.pk).exists())

        # Expired production session and data remain
        self.assertTrue(Session.objects.filter(pk=old_prod_sess.pk).exists())
        self.assertTrue(Data.objects.filter(pk=old_prod_data.pk).exists())

    def test_strict_creation_date_purge_active_session(self):
        # Active simulated session created 35 days ago (still has open stretch end=None)
        active_sess, active_stretch = self._create_session(self.sim_beamline, "active-old", days_ago=35, is_active=True)
        self.assertTrue(active_sess.is_active())

        out = io.StringIO()
        call_command("clean_simulated_sessions", no_input=True, stdout=out)

        self.assertFalse(Session.objects.filter(pk=active_sess.pk).exists())
        self.assertFalse(Stretch.objects.filter(pk=active_stretch.pk).exists())

    def test_orphan_datasets_cleanup_on_simulated_beamlines(self):
        # Expired orphan dataset on simulated beamline
        old_orphan = self._create_dataset(None, self.sim_beamline, "orphan-old-sim", days_ago=45)

        # Recent orphan dataset on simulated beamline
        recent_orphan = self._create_dataset(None, self.sim_beamline, "orphan-recent-sim", days_ago=5)

        # Expired orphan dataset on production beamline
        prod_orphan = self._create_dataset(None, self.prod_beamline, "orphan-prod", days_ago=60)

        out = io.StringIO()
        call_command("clean_simulated_sessions", no_input=True, stdout=out)

        self.assertFalse(Data.objects.filter(pk=old_orphan.pk).exists())
        self.assertTrue(Data.objects.filter(pk=recent_orphan.pk).exists())
        self.assertTrue(Data.objects.filter(pk=prod_orphan.pk).exists())

    def test_analysis_report_purging_and_preservation(self):
        old_sess, _ = self._create_session(self.sim_beamline, "sess-rep", days_ago=40)
        sim_data1 = self._create_dataset(old_sess, self.sim_beamline, "data-rep-1", days_ago=40)
        sim_data2 = self._create_dataset(old_sess, self.sim_beamline, "data-rep-2", days_ago=40)

        prod_sess, _ = self._create_session(self.prod_beamline, "sess-prod-rep", days_ago=10)
        prod_data = self._create_dataset(prod_sess, self.prod_beamline, "data-prod-rep", days_ago=10)

        # Report 1: only has data from expired simulated session -> should be deleted
        rep_pure_sim = AnalysisReport.objects.create(
            project=self.project,
            kind="Test Analysis",
            name="Report Pure Sim",
            url="/rep/1",
        )
        rep_pure_sim.data.add(sim_data1, sim_data2)

        # Report 2: has data from expired simulated session AND production data -> should be preserved
        rep_mixed = AnalysisReport.objects.create(
            project=self.project,
            kind="Mixed Analysis",
            name="Report Mixed",
            url="/rep/2",
        )
        rep_mixed.data.add(sim_data1, prod_data)

        out = io.StringIO()
        call_command("clean_simulated_sessions", no_input=True, stdout=out)

        self.assertFalse(AnalysisReport.objects.filter(pk=rep_pure_sim.pk).exists())
        self.assertTrue(AnalysisReport.objects.filter(pk=rep_mixed.pk).exists())
        # The mixed report should now only reference prod_data
        self.assertEqual(list(rep_mixed.data.all()), [prod_data])

    def test_crm_feedback_and_activity_log_cleanup(self):
        old_sess, _ = self._create_session(self.sim_beamline, "sess-aux", days_ago=40)
        sim_data = self._create_dataset(old_sess, self.sim_beamline, "data-aux", days_ago=40)

        rep = AnalysisReport.objects.create(
            project=self.project,
            kind="Test Analysis",
            name="Report Aux",
            url="/rep/aux",
        )
        rep.data.add(sim_data)

        # Create Feedback
        feedback = Feedback.objects.create(
            session=old_sess,
            comments="Simulated session feedback",
        )

        # Create ActivityLog entries
        sess_ct = ContentType.objects.get_for_model(Session)
        data_ct = ContentType.objects.get_for_model(Data)
        rep_ct = ContentType.objects.get_for_model(AnalysisReport)

        log_sess = ActivityLog.objects.create(
            content_type=sess_ct,
            object_id=old_sess.pk,
            action_type=ActivityLog.TYPE.CREATE,
            ip_number="127.0.0.1",
            description="Session launched",
        )
        log_data = ActivityLog.objects.create(
            content_type=data_ct,
            object_id=sim_data.pk,
            action_type=ActivityLog.TYPE.CREATE,
            ip_number="127.0.0.1",
            description="Data uploaded",
        )
        log_rep = ActivityLog.objects.create(
            content_type=rep_ct,
            object_id=rep.pk,
            action_type=ActivityLog.TYPE.CREATE,
            ip_number="127.0.0.1",
            description="Report generated",
        )

        # Control log for production session
        prod_sess, _ = self._create_session(self.prod_beamline, "sess-prod-log", days_ago=40)
        log_prod = ActivityLog.objects.create(
            content_type=sess_ct,
            object_id=prod_sess.pk,
            action_type=ActivityLog.TYPE.CREATE,
            ip_number="127.0.0.1",
            description="Prod session launched",
        )

        out = io.StringIO()
        call_command("clean_simulated_sessions", no_input=True, stdout=out)

        self.assertFalse(Feedback.objects.filter(pk=feedback.pk).exists())
        self.assertFalse(ActivityLog.objects.filter(pk=log_sess.pk).exists())
        self.assertFalse(ActivityLog.objects.filter(pk=log_data.pk).exists())
        self.assertFalse(ActivityLog.objects.filter(pk=log_rep.pk).exists())
        self.assertTrue(ActivityLog.objects.filter(pk=log_prod.pk).exists())

    def test_dry_run_does_not_modify_database(self):
        old_sess, _ = self._create_session(self.sim_beamline, "dry-sess", days_ago=45)
        old_data = self._create_dataset(old_sess, self.sim_beamline, "dry-data", days_ago=45)

        out = io.StringIO()
        call_command("clean_simulated_sessions", dry_run=True, stdout=out)
        output = out.getvalue()

        self.assertIn("[DRY RUN]", output)
        self.assertIn("Sessions to delete: 1", output)
        self.assertIn("Datasets to delete: 1", output)

        # Database remains untouched
        self.assertTrue(Session.objects.filter(pk=old_sess.pk).exists())
        self.assertTrue(Data.objects.filter(pk=old_data.pk).exists())

    def test_beamline_filter(self):
        sess_1, _ = self._create_session(self.sim_beamline, "sess-bl-1", days_ago=40)
        sess_2, _ = self._create_session(self.sim_beamline_2, "sess-bl-2", days_ago=40)

        out = io.StringIO()
        call_command("clean_simulated_sessions", beamline="SIM-01", no_input=True, stdout=out)

        self.assertFalse(Session.objects.filter(pk=sess_1.pk).exists())
        self.assertTrue(Session.objects.filter(pk=sess_2.pk).exists())

    def test_days_override(self):
        sess, _ = self._create_session(self.sim_beamline, "sess-15-days", days_ago=20)

        # With default 30 days -> not deleted
        out = io.StringIO()
        call_command("clean_simulated_sessions", no_input=True, stdout=out)
        self.assertTrue(Session.objects.filter(pk=sess.pk).exists())

        # With --days=15 -> deleted
        call_command("clean_simulated_sessions", days=15, no_input=True, stdout=out)
        self.assertFalse(Session.objects.filter(pk=sess.pk).exists())

    def test_invalid_arguments_raise_command_error(self):
        with self.assertRaises(CommandError) as ctx:
            call_command("clean_simulated_sessions", days=-1, no_input=True)
        self.assertIn("must be non-negative", str(ctx.exception))

        with self.assertRaises(CommandError) as ctx:
            call_command("clean_simulated_sessions", beamline="NONEXISTENT", no_input=True)
        self.assertIn("does not exist", str(ctx.exception))

        with self.assertRaises(CommandError) as ctx:
            call_command("clean_simulated_sessions", beamline=self.prod_beamline.acronym, no_input=True)
        self.assertIn("is not a simulated beamline", str(ctx.exception))

    def test_interactive_cancellation(self):
        sess, _ = self._create_session(self.sim_beamline, "sess-cancel", days_ago=40)

        out = io.StringIO()
        with patch("builtins.input", return_value="n"):
            call_command("clean_simulated_sessions", stdout=out)

        output = out.getvalue()
        self.assertIn("Operation cancelled", output)
        self.assertTrue(Session.objects.filter(pk=sess.pk).exists())
