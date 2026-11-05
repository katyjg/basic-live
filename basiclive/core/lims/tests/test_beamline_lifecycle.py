import json
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import RequestFactory, TestCase
from django.utils import timezone

from basiclive.core.api.views import LaunchSession
from basiclive.core.lims.models import Beamline, Project, Session, User
from basiclive.core.schedule.models import AccessType, Beamtime
from basiclive.core.schedule.views import CalendarView


class BeamlineLifecycleAndSimulationTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.user = User.objects.create_user(username="researcher", email="res@example.org")
        self.project = Project.objects.create(name="proj-101", pi=self.user)

        self.bl_prod_active = Beamline.objects.create(
            name="Production Active Beamline",
            acronym="08B1-PROD",
            active=True,
            simulated=False,
        )
        self.bl_sim_active = Beamline.objects.create(
            name="Simulation Active Beamline",
            acronym="08B1-SIM",
            active=True,
            simulated=True,
        )
        self.bl_prod_decom = Beamline.objects.create(
            name="Decommissioned Production Beamline",
            acronym="08B1-OLD",
            active=False,
            simulated=False,
        )
        self.bl_sim_decom = Beamline.objects.create(
            name="Decommissioned Simulation Beamline",
            acronym="08B1-SIM-OLD",
            active=False,
            simulated=True,
        )

    def test_model_defaults_and_properties(self):
        default_bl = Beamline.objects.create(name="Default Beamline", acronym="08B1-DEF")
        self.assertTrue(default_bl.active)
        self.assertFalse(default_bl.simulated)
        self.assertFalse(default_bl.is_decommissioned)
        self.assertTrue(default_bl.is_production)

        self.assertFalse(self.bl_prod_decom.is_production)
        self.assertTrue(self.bl_prod_decom.is_decommissioned)

        self.assertFalse(self.bl_sim_active.is_production)
        self.assertFalse(self.bl_sim_active.is_decommissioned)

        self.assertFalse(self.bl_sim_decom.is_production)
        self.assertTrue(self.bl_sim_decom.is_decommissioned)

    def test_calendar_view_filters_active_production_only(self):
        view = CalendarView()
        view.request = self.rf.get("/schedule/")
        view.kwargs = {}
        context = view.get_context_data()

        beamline_pks = set(context["beamlines"].values_list("pk", flat=True))
        self.assertIn(self.bl_prod_active.pk, beamline_pks)
        self.assertNotIn(self.bl_sim_active.pk, beamline_pks)
        self.assertNotIn(self.bl_prod_decom.pk, beamline_pks)
        self.assertNotIn(self.bl_sim_decom.pk, beamline_pks)

    @patch("basiclive.core.api.views.make_secure_path", return_value="test-token")
    def test_launch_session_decommissioned_beamlines_rejected(self, mock_secure_path):
        view = LaunchSession.as_view()

        # Attempt to launch on decommissioned production beamline -> 403 Forbidden
        req = self.rf.post(
            f"/api/session/{self.bl_prod_decom.acronym}/sess-old/start/",
            data={"project": self.project.name},
        )
        req.user = self.user
        req.project = self.project
        resp = view(req, beamline=self.bl_prod_decom.acronym, session="sess-old")
        self.assertEqual(resp.status_code, 403)
        self.assertIn(b"Beamline is inactive or decommissioned", resp.content)

        # Attempt to launch on decommissioned simulation beamline -> 403 Forbidden
        req_sim = self.rf.post(
            f"/api/session/{self.bl_sim_decom.acronym}/sess-sim-old/start/",
            data={"project": self.project.name},
        )
        req_sim.user = self.user
        req_sim.project = self.project
        resp_sim = view(req_sim, beamline=self.bl_sim_decom.acronym, session="sess-sim-old")
        self.assertEqual(resp_sim.status_code, 403)
        self.assertIn(b"Beamline is inactive or decommissioned", resp_sim.content)

    @patch("basiclive.core.api.views.make_secure_path", return_value="test-token")
    def test_launch_session_simulation_allows_ad_hoc_session(self, mock_secure_path):
        view = LaunchSession.as_view()

        with self.settings(USE_SCHEDULE=True):
            # Active simulation beamline without scheduled beamtime gets a 2h end_time
            req = self.rf.post(
                f"/api/session/{self.bl_sim_active.acronym}/sess-sim/start/",
                data={"project": self.project.name},
            )
            req.user = self.user
            req.project = self.project
            resp = view(req, beamline=self.bl_sim_active.acronym, session="sess-sim")
            self.assertEqual(resp.status_code, 200)

            data = json.loads(resp.content)
            self.assertIsNotNone(data.get("end_time"))

    @patch("basiclive.core.api.views.make_secure_path", return_value="test-token")
    def test_launch_session_production_requires_scheduled_beamtime(self, mock_secure_path):
        view = LaunchSession.as_view()

        with self.settings(USE_SCHEDULE=True):
            # 1. Without scheduled beamtime, active production beamline grants NO default end_time
            req = self.rf.post(
                f"/api/session/{self.bl_prod_active.acronym}/sess-prod-no-bt/start/",
                data={"project": self.project.name},
            )
            req.user = self.user
            req.project = self.project
            resp = view(req, beamline=self.bl_prod_active.acronym, session="sess-prod-no-bt")
            self.assertEqual(resp.status_code, 200)
            data = json.loads(resp.content)
            self.assertIsNone(data.get("end_time"))

            # 2. With scheduled beamtime, active production beamline uses scheduled end_time
            now = timezone.now()
            access_type = AccessType.objects.create(name="Remote")
            expected_end = now + timedelta(hours=4)
            Beamtime.objects.create(
                project=self.project,
                beamline=self.bl_prod_active,
                access=access_type,
                start=now - timedelta(hours=1),
                end=expected_end,
            )

            req_with_bt = self.rf.post(
                f"/api/session/{self.bl_prod_active.acronym}/sess-prod-bt/start/",
                data={"project": self.project.name},
            )
            req_with_bt.user = self.user
            req_with_bt.project = self.project
            resp_with_bt = view(req_with_bt, beamline=self.bl_prod_active.acronym, session="sess-prod-bt")
            self.assertEqual(resp_with_bt.status_code, 200)
            data_with_bt = json.loads(resp_with_bt.content)
            self.assertEqual(data_with_bt.get("end_time"), expected_end.isoformat())
