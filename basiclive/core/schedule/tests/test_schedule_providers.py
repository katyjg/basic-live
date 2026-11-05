from datetime import date, datetime, timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

import httpx2
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from basiclive.core.lims.models import Beamline, Project, User
from basiclive.core.schedule.models import (
    AccessType,
    BeamlineSupport,
    Beamtime,
    Downtime,
    EmailNotification,
    FacilityMode,
    FacilityModeType,
)
from basiclive.core.schedule.providers import (
    BaseScheduleProvider,
    ExternalBeamtimeData,
    ExternalDowntimeData,
    ExternalModeData,
    ExternalSupportData,
    HttpScheduleProvider,
    get_schedule_provider,
)
from basiclive.core.schedule.templatetags.calendar import calendar_view


class FacilityModeModelTests(TestCase):
    def test_canonical_seeded_facility_mode_types_and_css_class(self):
        expected = {
            "normal": ("Normal", "mode-normal"),
            "development": ("Development", "mode-development"),
            "maintenance": ("Maintenance", "mode-maintenance"),
            "shutdown": ("Shutdown (Beam Off)", "mode-shutdown"),
            "special": ("Special Beam", "mode-special"),
        }
        types = {m.code: m for m in FacilityModeType.objects.all()}
        for code, (desc, css_cls) in expected.items():
            self.assertIn(code, types)
            self.assertEqual(types[code].description, desc)
            self.assertEqual(types[code].css_class, css_cls)

    def test_facility_mode_interval_and_with_duration_annotation(self):
        normal_type = FacilityModeType.objects.get(code="normal")
        start = timezone.make_aware(datetime(2026, 5, 4, 8, 0, 0))
        end = start + timedelta(hours=16)

        interval = FacilityMode.objects.create(
            mode=normal_type,
            start=start,
            end=end,
            comments="User operations",
            source_id="MODE-101",
        )

        annotated = FacilityMode.objects.with_duration().get(pk=interval.pk)
        self.assertEqual(annotated.mode, normal_type)
        self.assertEqual(annotated.source_id, "MODE-101")
        self.assertEqual(annotated.duration, timedelta(hours=16))
        self.assertEqual(annotated.shifts, 2)

    def test_schedule_events_support_nullable_source_id(self):
        beamline = Beamline.objects.create(name="08ID-1", acronym="08ID-1", active=True)
        staff = User.objects.create_user(username="staff1", is_staff=True)
        start = timezone.make_aware(datetime(2026, 5, 4, 8, 0, 0))
        end = start + timedelta(hours=8)

        bt_local = Beamtime.objects.create(beamline=beamline, start=start, end=end)
        bt_ext = Beamtime.objects.create(
            beamline=beamline, start=start, end=end, source_id="BT-EXT-1"
        )
        self.assertIsNone(bt_local.source_id)
        self.assertEqual(Beamtime.objects.get(pk=bt_ext.pk).source_id, "BT-EXT-1")

        dt_local = Downtime.objects.create(beamline=beamline, start=start, end=end)
        dt_ext = Downtime.objects.create(
            beamline=beamline, start=start, end=end, source_id="DT-EXT-1"
        )
        self.assertIsNone(dt_local.source_id)
        self.assertEqual(Downtime.objects.get(pk=dt_ext.pk).source_id, "DT-EXT-1")

        sup_local = BeamlineSupport.objects.create(staff=staff, date=date(2026, 5, 4))
        sup_ext = BeamlineSupport.objects.create(
            staff=staff, date=date(2026, 5, 5), source_id="SUP-EXT-1"
        )
        self.assertIsNone(sup_local.source_id)
        self.assertEqual(BeamlineSupport.objects.get(pk=sup_ext.pk).source_id, "SUP-EXT-1")


class DummyScheduleProvider(BaseScheduleProvider):
    modes_to_return: list[ExternalModeData] = []

    def fetch_modes(self, start: date, end: date):
        return list(self.modes_to_return)


class ScheduleProviderConfigAndModeSyncTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_get_schedule_provider_config_resolution(self):
        self.assertIsNone(get_schedule_provider())

        with override_settings(
            BASICLIVE_SCHEDULE={
                "SCHEDULE_PROVIDER": "basiclive.core.schedule.tests.test_schedule_providers.DummyScheduleProvider"
            }
        ):
            provider = get_schedule_provider()
            self.assertIsInstance(provider, DummyScheduleProvider)
            self.assertEqual(provider.cache_ttl, 900)

        with override_settings(
            BASICLIVE_SCHEDULE={
                "SCHEDULE_PROVIDER": {
                    "BACKEND": "basiclive.core.schedule.providers.HttpScheduleProvider",
                    "CACHE_TTL": 600,
                    "OPTIONS": {
                        "base_url": "https://schedule.facility.example.org/api",
                        "endpoints": {"modes": "/modes?start={start}&end={end}"},
                        "mode_map": {"CUSTOM_M": "maintenance"},
                    },
                }
            }
        ):
            provider = get_schedule_provider()
            self.assertIsInstance(provider, HttpScheduleProvider)
            self.assertEqual(provider.cache_ttl, 600)
            self.assertTrue(provider.supports("modes"))
            self.assertFalse(provider.supports("beamtime"))
            self.assertEqual(provider.translate_mode("CUSTOM_M"), "maintenance")

        with override_settings(BASICLIVE_SCHEDULE={"SCHEDULE_PROVIDER": 999}):
            with self.assertRaises(ValueError):
                get_schedule_provider()

    def test_translate_mode_maps_default_and_custom_codes(self):
        FacilityModeType.objects.create(
            code="commissioning", description="Commissioning", color="#AABBCC"
        )
        provider = BaseScheduleProvider(
            mode_map={
                "BEAM_STUDY": "development",
                "COMM": "commissioning",
                "NORMAL": "special",  # Explicit mode_map override takes precedence over default
            }
        )
        self.assertEqual(provider.translate_mode("N"), "normal")
        self.assertEqual(provider.translate_mode("D"), "development")
        for m_code in ("M", "MV", "M0", "MT"):
            self.assertEqual(provider.translate_mode(m_code), "maintenance")
        self.assertEqual(provider.translate_mode("X"), "shutdown")
        for s_code in ("NS", "DS", "DST", "DS-CSR"):
            self.assertEqual(provider.translate_mode(s_code), "special")
        self.assertEqual(provider.translate_mode("BEAM_STUDY"), "development")
        self.assertEqual(provider.translate_mode("COMM"), "commissioning")
        self.assertEqual(provider.translate_mode("commissioning"), "commissioning")
        self.assertEqual(provider.translate_mode("normal"), "special")
        self.assertIsNone(provider.translate_mode("UNKNOWN_CODE"))

        # Subclass that only overrides fetch_modes supports only 'modes'
        dummy = DummyScheduleProvider()
        self.assertTrue(dummy.supports("modes"))
        self.assertFalse(dummy.supports("beamtime"))
        self.assertFalse(dummy.supports("downtime"))
        self.assertFalse(dummy.supports("support"))

    def test_sync_modes_reconciles_window_and_preserves_local_intervals(self):
        win_start = date(2026, 6, 1)
        win_end = date(2026, 6, 8)
        t0 = timezone.make_aware(datetime(2026, 6, 1, 0, 0, 0))
        t1 = timezone.make_aware(datetime(2026, 6, 1, 8, 0, 0))
        t2 = timezone.make_aware(datetime(2026, 6, 1, 16, 0, 0))

        normal_type = FacilityModeType.objects.get(code="normal")
        maint_type = FacilityModeType.objects.get(code="maintenance")
        shutdown_type = FacilityModeType.objects.get(code="shutdown")

        # Locally managed interval (source_id=None) inside the window -> must be preserved
        local_mode = FacilityMode.objects.create(
            mode=shutdown_type,
            start=t0,
            end=t1,
            comments="Local manual shutdown",
            source_id=None,
        )

        # Stale external interval inside the window -> must be pruned
        stale_external = FacilityMode.objects.create(
            mode=maint_type,
            start=t1,
            end=t2,
            comments="Stale maintenance",
            source_id="EXT-STALE-1",
        )

        # External interval outside the window -> must not be pruned by this window sync
        outside_start = timezone.make_aware(datetime(2026, 7, 1, 0, 0, 0))
        outside_end = timezone.make_aware(datetime(2026, 7, 1, 8, 0, 0))
        outside_external = FacilityMode.objects.create(
            mode=normal_type,
            start=outside_start,
            end=outside_end,
            source_id="EXT-OUTSIDE-1",
        )

        DummyScheduleProvider.modes_to_return = [
            ExternalModeData(
                mode_code="normal",
                start=t0,
                end=t1,
                source_id="EXT-M-1",
                comments="Morning normal beam",
            ),
            ExternalModeData(
                mode_code="MV",  # Sub-code translated to 'maintenance'
                start=t1,
                end=t2,
                source_id=None,  # Deterministic composite source_id generated
                comments="Vacuum maintenance",
            ),
        ]

        provider = DummyScheduleProvider(cache_ttl=900)
        stats = provider.sync(win_start, win_end, types=["modes"])
        self.assertEqual(stats["modes"], 2)

        # Stale external interval in window was deleted
        self.assertFalse(FacilityMode.objects.filter(pk=stale_external.pk).exists())
        # Local interval in window and external interval outside window remain intact
        self.assertTrue(FacilityMode.objects.filter(pk=local_mode.pk).exists())
        self.assertTrue(FacilityMode.objects.filter(pk=outside_external.pk).exists())

        synced_m1 = FacilityMode.objects.get(source_id="EXT-M-1")
        self.assertEqual(synced_m1.mode, normal_type)
        self.assertEqual(synced_m1.comments, "Morning normal beam")

        synced_mv = FacilityMode.objects.exclude(
            pk__in=[local_mode.pk, outside_external.pk, synced_m1.pk]
        ).get()
        self.assertEqual(synced_mv.mode, maint_type)
        self.assertIsNotNone(synced_mv.source_id)

        # Second call within TTL window is skipped unless force=True
        with patch.object(provider, "fetch_modes") as mock_fetch:
            provider.sync(win_start, win_end, types=["modes"], force=False)
            self.assertEqual(mock_fetch.call_count, 0)

            mock_fetch.return_value = DummyScheduleProvider.modes_to_return
            provider.sync(win_start, win_end, types=["modes"], force=True)
            self.assertEqual(mock_fetch.call_count, 1)

    @patch("basiclive.core.schedule.providers.httpx2.get")
    def test_http_schedule_provider_fetch_modes(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "id": "M-500",
                "kind": "DS-CSR",
                "start": "2026-06-01T00:00:00-06:00",
                "end": "2026-06-01T08:00:00-06:00",
                "description": "CSR special shift",
            }
        ]
        mock_get.return_value = mock_resp

        provider = HttpScheduleProvider(
            base_url="https://schedule.facility.example.org/api",
            endpoints={"modes": "/modes?start={start}&end={end}"},
        )
        modes = list(provider.fetch_modes(date(2026, 6, 1), date(2026, 6, 8)))

        mock_get.assert_called_once_with(
            "https://schedule.facility.example.org/api/modes?start=2026-06-01&end=2026-06-08",
            headers={},
            timeout=10.0,
            follow_redirects=True,
        )
        self.assertEqual(len(modes), 1)
        self.assertEqual(modes[0].mode_code, "special")
        self.assertEqual(modes[0].source_id, "M-500")
        self.assertEqual(modes[0].comments, "CSR special shift")

    def test_sync_schedule_management_command(self):
        t0 = timezone.make_aware(datetime(2026, 6, 1, 0, 0, 0))
        t1 = timezone.make_aware(datetime(2026, 6, 1, 8, 0, 0))
        DummyScheduleProvider.modes_to_return = [
            ExternalModeData(
                mode_code="D",
                start=t0,
                end=t1,
                source_id="CMD-MODE-1",
            )
        ]
        out = StringIO()
        with override_settings(
            BASICLIVE_SCHEDULE={
                "SCHEDULE_PROVIDER": "basiclive.core.schedule.tests.test_schedule_providers.DummyScheduleProvider"
            }
        ):
            call_command(
                "sync_schedule",
                "--start",
                "2026-06-01",
                "--end",
                "2026-06-08",
                "--types",
                "modes",
                "--force",
                stdout=out,
            )

        self.assertTrue(
            FacilityMode.objects.filter(
                source_id="CMD-MODE-1", mode__code="development"
            ).exists()
        )
        self.assertIn("modes: 1", out.getvalue())

    def test_calendar_view_renders_db_modes_and_degrades_gracefully_on_api_failure(self):
        # ISO 2026-W23 starts Monday 2026-06-01
        t0 = timezone.make_aware(datetime(2026, 6, 1, 0, 0, 0))
        t1 = timezone.make_aware(datetime(2026, 6, 1, 16, 0, 0))
        DummyScheduleProvider.modes_to_return = [
            ExternalModeData(
                mode_code="N",
                start=t0,
                end=t1,
                source_id="CAL-MODE-1",
            )
        ]

        with override_settings(
            BASICLIVE_SCHEDULE={
                "SCHEDULE_PROVIDER": "basiclive.core.schedule.tests.test_schedule_providers.DummyScheduleProvider"
            }
        ):
            info = calendar_view(2026, 23)
            day_modes = info["week"]["2026-06-01"]["modes"]
            self.assertEqual(day_modes["00"]["kind"], "normal")
            self.assertEqual(day_modes["00"]["css_class"], "mode-normal")
            self.assertEqual(day_modes["08"]["css_class"], "mode-normal")
            self.assertEqual(day_modes["16"], {})

            # Clear cache and simulate upstream network failure: existing DB modes still render
            cache.clear()
            with patch.object(
                DummyScheduleProvider,
                "fetch_modes",
                side_effect=httpx2.ConnectError("upstream down"),
            ):
                with self.assertWarns(UserWarning):
                    fallback_info = calendar_view(2026, 23)
                self.assertEqual(
                    fallback_info["week"]["2026-06-01"]["modes"]["00"]["css_class"],
                    "mode-normal",
                )

    def test_calendar_week_template_renders_mode_css_classes(self):
        normal_type = FacilityModeType.objects.get(code="normal")
        t0 = timezone.make_aware(datetime(2026, 6, 1, 0, 0, 0))
        t1 = timezone.make_aware(datetime(2026, 6, 1, 8, 0, 0))
        FacilityMode.objects.create(mode=normal_type, start=t0, end=t1, source_id="TPL-1")

        resp = self.client.get(reverse("any-week", kwargs={"year": 2026, "week": 23}))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn(".mode-normal", html)
        self.assertIn(".mode-maintenance", html)
        self.assertIn('class="mode mode-normal', html)


class DummyBeamtimeProvider(BaseScheduleProvider):
    beamtime_to_return: list[ExternalBeamtimeData] = []

    def fetch_beamtime(self, start: date, end: date):
        return list(self.beamtime_to_return)


class ScheduleBeamtimeSyncTests(TestCase):
    def setUp(self):
        cache.clear()
        self.beamline = Beamline.objects.create(
            name="08ID-1", acronym="08ID-1", active=True, simulated=False
        )
        self.sim_beamline = Beamline.objects.create(
            name="08ID-SIM", acronym="08ID-SIM", active=True, simulated=True
        )
        self.pi = User.objects.create_user(
            username="pi_user", email="pi@example.org", last_name="Curie"
        )
        self.project_by_source = Project.objects.create(
            name="PRJ-001", source_id="PROP-100", pi=self.pi, contact_email="pi@example.org"
        )
        self.project_by_name = Project.objects.create(
            name="PRJ-002", source_id=None, pi=self.pi, contact_email="pi@example.org"
        )
        self.regular_access = AccessType.objects.create(
            name="Regular",
            color="#228833",
            email_subject="Beamtime on {beamline} for {name}",
            email_body="Starts {start_date} at {start_time}",
        )
        self.remote_access = AccessType.objects.create(
            name="Remote",
            color="#336699",
            email_subject="Remote Beamtime on {beamline}",
            email_body="Remote shift on {start_date}",
            remote=True,
        )

    def tearDown(self):
        cache.clear()

    def test_sync_beamtime_reconciles_window_creates_future_notifications_and_preserves_local(self):
        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        win_start = (now - timedelta(days=2)).date()
        win_end = (now + timedelta(days=10)).date()

        past_start = now - timedelta(days=1)
        past_end = past_start + timedelta(hours=8)

        future_start = now + timedelta(days=3)
        future_end = future_start + timedelta(hours=8)

        future_start_2 = now + timedelta(days=4)
        future_end_2 = future_start_2 + timedelta(hours=8)

        # Local beamtime (source_id=None) inside window -> must be preserved
        local_bt = Beamtime.objects.create(
            project=self.project_by_name,
            beamline=self.sim_beamline,
            access=self.regular_access,
            start=future_start,
            end=future_end,
            comments="Local simulated shift",
            source_id=None,
        )

        # Stale external beamtime inside window -> must be pruned
        stale_bt = Beamtime.objects.create(
            project=self.project_by_source,
            beamline=self.beamline,
            access=self.regular_access,
            start=past_start,
            end=past_end,
            source_id="BT-STALE-99",
        )

        # External beamtime outside window -> must not be pruned
        outside_bt = Beamtime.objects.create(
            project=self.project_by_source,
            beamline=self.beamline,
            access=self.regular_access,
            start=now + timedelta(days=20),
            end=now + timedelta(days=20, hours=8),
            source_id="BT-OUTSIDE-1",
        )

        DummyBeamtimeProvider.beamtime_to_return = [
            # Past beamtime -> should NOT create EmailNotification
            ExternalBeamtimeData(
                beamline_acronym="08ID-1",
                start=past_start,
                end=past_end,
                project_source_id="PROP-100",
                access_type="Regular",
                comments="Past shift",
                source_id="BT-PAST-1",
            ),
            # Future beamtime matched by project_source_id -> SHOULD create EmailNotification
            ExternalBeamtimeData(
                beamline_acronym="08id-1",
                start=future_start,
                end=future_end,
                project_source_id="PROP-100",
                access_type="Remote",
                comments="Future remote shift",
                source_id="BT-FUT-1",
            ),
            # Future beamtime matched by project_name without explicit source_id
            ExternalBeamtimeData(
                beamline_acronym="08ID-1",
                start=future_start_2,
                end=future_end_2,
                project_name="prj-002",
                access_type="Regular",
                comments="Composite source id shift",
                source_id=None,
            ),
        ]

        provider = DummyBeamtimeProvider(cache_ttl=900)
        stats = provider.sync(win_start, win_end, types=["beamtime"])
        self.assertEqual(stats["beamtime"], 3)

        # Stale deleted, local & outside preserved
        self.assertFalse(Beamtime.objects.filter(pk=stale_bt.pk).exists())
        self.assertTrue(Beamtime.objects.filter(pk=local_bt.pk).exists())
        self.assertTrue(Beamtime.objects.filter(pk=outside_bt.pk).exists())

        bt_past = Beamtime.objects.get(source_id="BT-PAST-1")
        self.assertEqual(bt_past.project, self.project_by_source)
        self.assertEqual(bt_past.access, self.regular_access)
        self.assertEqual(EmailNotification.objects.filter(beamtime=bt_past).count(), 0)

        bt_fut1 = Beamtime.objects.get(source_id="BT-FUT-1")
        self.assertEqual(bt_fut1.project, self.project_by_source)
        self.assertEqual(bt_fut1.access, self.remote_access)
        self.assertEqual(bt_fut1.comments, "Future remote shift")
        self.assertEqual(EmailNotification.objects.filter(beamtime=bt_fut1).count(), 1)
        notif = EmailNotification.objects.get(beamtime=bt_fut1)
        self.assertIn("08ID-1", notif.email_subject)

        bt_fut2 = Beamtime.objects.get(
            beamline=self.beamline, start=future_start_2, end=future_end_2
        )
        self.assertEqual(bt_fut2.project, self.project_by_name)
        self.assertIsNotNone(bt_fut2.source_id)
        self.assertEqual(EmailNotification.objects.filter(beamtime=bt_fut2).count(), 1)

        # Re-syncing existing future beamtime updates fields without duplicating EmailNotification
        DummyBeamtimeProvider.beamtime_to_return[1] = ExternalBeamtimeData(
            beamline_acronym="08ID-1",
            start=future_start,
            end=future_end,
            project_source_id="PROP-100",
            access_type="Remote",
            comments="Updated future remote shift",
            source_id="BT-FUT-1",
        )
        provider.sync(win_start, win_end, types=["beamtime"], force=True)
        bt_fut1.refresh_from_db()
        self.assertEqual(bt_fut1.comments, "Updated future remote shift")
        self.assertEqual(EmailNotification.objects.filter(beamtime=bt_fut1).count(), 1)

    @patch("basiclive.core.schedule.providers.httpx2.get")
    def test_http_schedule_provider_fetch_beamtime(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "beamtime": [
                {
                    "id": "BT-700",
                    "beamline": "08ID-1",
                    "project": "PRJ-001",
                    "project_source_id": "PROP-100",
                    "access_type": "Remote",
                    "start": "2026-06-02T08:00:00-06:00",
                    "end": "2026-06-02T16:00:00-06:00",
                    "cancelled": False,
                    "comments": "Scheduled via API",
                }
            ]
        }
        mock_get.return_value = mock_resp

        provider = HttpScheduleProvider(
            base_url="https://schedule.facility.example.org/api",
            endpoints={"beamtime": "/beamtime?start={start}&end={end}"},
        )
        self.assertTrue(provider.supports("beamtime"))
        self.assertFalse(provider.supports("modes"))

        items = list(provider.fetch_beamtime(date(2026, 6, 1), date(2026, 6, 8)))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_id, "BT-700")
        self.assertEqual(items[0].beamline_acronym, "08ID-1")
        self.assertEqual(items[0].project_name, "PRJ-001")
        self.assertEqual(items[0].project_source_id, "PROP-100")
        self.assertEqual(items[0].access_type, "Remote")
        self.assertIs(items[0].cancelled, False)
        self.assertEqual(items[0].comments, "Scheduled via API")


class DummyBeamtimeAndDowntimeProvider(BaseScheduleProvider):
    beamtime_to_return: list[ExternalBeamtimeData] = []
    downtime_to_return: list[ExternalDowntimeData] = []

    def fetch_beamtime(self, start: date, end: date):
        return list(self.beamtime_to_return)

    def fetch_downtime(self, start: date, end: date):
        return list(self.downtime_to_return)


class ScheduleDowntimeSyncTests(TestCase):
    def setUp(self):
        cache.clear()
        self.bl1 = Beamline.objects.create(
            name="08ID-1", acronym="08ID-1", active=True, simulated=False
        )
        self.bl2 = Beamline.objects.create(
            name="08BM-1", acronym="08BM-1", active=True, simulated=False
        )
        self.sim_bl = Beamline.objects.create(
            name="08ID-SIM", acronym="08ID-SIM", active=True, simulated=True
        )
        self.inactive_bl = Beamline.objects.create(
            name="08ID-OLD", acronym="08ID-OLD", active=False, simulated=False
        )
        self.project = Project.objects.create(name="PRJ-DT", source_id="PROP-DT")
        self.access = AccessType.objects.create(
            name="Regular",
            email_subject="Beamtime on {beamline}",
            email_body="Body",
        )

    def tearDown(self):
        cache.clear()

    def test_sync_downtime_expands_facility_downtime_cancels_overlapping_beamtime_and_preserves_local(self):
        win_start = date(2026, 6, 1)
        win_end = date(2026, 6, 8)
        t0 = timezone.make_aware(datetime(2026, 6, 2, 0, 0, 0))
        t1 = timezone.make_aware(datetime(2026, 6, 2, 8, 0, 0))
        t2 = timezone.make_aware(datetime(2026, 6, 2, 16, 0, 0))
        t3 = timezone.make_aware(datetime(2026, 6, 3, 8, 0, 0))
        t4 = timezone.make_aware(datetime(2026, 6, 3, 16, 0, 0))

        # Local downtime (source_id=None) -> must be preserved
        local_dt = Downtime.objects.create(
            beamline=self.bl1,
            scope=Downtime.SCOPE_CHOICES.BEAMLINE,
            start=t3,
            end=t4,
            comments="Local cryocooler service",
            source_id=None,
        )

        # Stale external downtime -> must be pruned
        stale_dt = Downtime.objects.create(
            beamline=self.bl1,
            scope=Downtime.SCOPE_CHOICES.BEAMLINE,
            start=t0,
            end=t1,
            comments="Stale external downtime",
            source_id="DT-STALE-1",
        )

        # Beamtimes in [t0, t2] and [t3, t4]
        DummyBeamtimeAndDowntimeProvider.beamtime_to_return = [
            # Overlaps facility downtime [t0, t1] on bl1 with cancelled=None -> must become cancelled=True
            ExternalBeamtimeData(
                beamline_acronym="08ID-1",
                start=t0,
                end=t1,
                project_source_id="PROP-DT",
                cancelled=None,
                source_id="BT-BL1-FAC-DT",
            ),
            # Overlaps facility downtime [t0, t1] on bl2 with explicit cancelled=False -> respects explicit False
            ExternalBeamtimeData(
                beamline_acronym="08BM-1",
                start=t0,
                end=t1,
                project_source_id="PROP-DT",
                cancelled=False,
                source_id="BT-BL2-EXPLICIT-FALSE",
            ),
            # Overlaps beamline downtime [t1, t2] on bl2 with cancelled=None -> must become cancelled=True
            ExternalBeamtimeData(
                beamline_acronym="08BM-1",
                start=t1,
                end=t2,
                project_source_id="PROP-DT",
                cancelled=None,
                source_id="BT-BL2-BL-DT",
            ),
            # Non-overlapping beamtime on bl1 [t1, t2] -> remains cancelled=False
            ExternalBeamtimeData(
                beamline_acronym="08ID-1",
                start=t1,
                end=t2,
                project_source_id="PROP-DT",
                cancelled=None,
                source_id="BT-BL1-CLEAR",
            ),
        ]

        DummyBeamtimeAndDowntimeProvider.downtime_to_return = [
            # Facility-wide downtime (beamline_acronym=None) -> expands to bl1 and bl2 (not simulated or inactive)
            ExternalDowntimeData(
                start=t0,
                end=t1,
                scope=Downtime.SCOPE_CHOICES.FACILITY,
                beamline_acronym=None,
                comments="Linac RF trip",
                source_id="DT-FAC-100",
            ),
            # Beamline-specific downtime on 08BM-1
            ExternalDowntimeData(
                start=t1,
                end=t2,
                scope=Downtime.SCOPE_CHOICES.BEAMLINE,
                beamline_acronym="08BM-1",
                comments="Monochromator alignment",
                source_id="DT-BL2-200",
            ),
        ]

        provider = DummyBeamtimeAndDowntimeProvider(cache_ttl=900)
        stats = provider.sync(win_start, win_end, types=["beamtime", "downtime"])
        self.assertEqual(stats["beamtime"], 4)
        self.assertEqual(stats["downtime"], 3)  # 2 from facility expansion + 1 beamline-specific

        # Stale deleted, local preserved
        self.assertFalse(Downtime.objects.filter(pk=stale_dt.pk).exists())
        self.assertTrue(Downtime.objects.filter(pk=local_dt.pk).exists())

        # Facility downtime created on active production beamlines (bl1, bl2), NOT on sim_bl or inactive_bl
        self.assertTrue(
            Downtime.objects.filter(
                beamline=self.bl1,
                start=t0,
                end=t1,
                scope=Downtime.SCOPE_CHOICES.FACILITY,
                comments="Linac RF trip",
            ).exists()
        )
        self.assertTrue(
            Downtime.objects.filter(
                beamline=self.bl2,
                start=t0,
                end=t1,
                scope=Downtime.SCOPE_CHOICES.FACILITY,
                comments="Linac RF trip",
            ).exists()
        )
        self.assertFalse(Downtime.objects.filter(beamline=self.sim_bl).exists())
        self.assertFalse(Downtime.objects.filter(beamline=self.inactive_bl).exists())

        # Beamline downtime created on bl2
        self.assertTrue(
            Downtime.objects.filter(
                source_id="DT-BL2-200",
                beamline=self.bl2,
                scope=Downtime.SCOPE_CHOICES.BEAMLINE,
            ).exists()
        )

        # Verify cancellation side-effects on Beamtime
        self.assertTrue(Beamtime.objects.get(source_id="BT-BL1-FAC-DT").cancelled)
        self.assertFalse(Beamtime.objects.get(source_id="BT-BL2-EXPLICIT-FALSE").cancelled)
        self.assertTrue(Beamtime.objects.get(source_id="BT-BL2-BL-DT").cancelled)
        self.assertFalse(Beamtime.objects.get(source_id="BT-BL1-CLEAR").cancelled)

    def test_sync_downtime_removal_uncancels_beamtime_and_respects_explicit_cancelled_across_separate_calls(self):
        win_start = date(2026, 6, 1)
        win_end = date(2026, 6, 8)
        t0 = timezone.make_aware(datetime(2026, 6, 2, 0, 0, 0))
        t1 = timezone.make_aware(datetime(2026, 6, 2, 8, 0, 0))

        provider = DummyBeamtimeAndDowntimeProvider(cache_ttl=900)

        # 1. Separate call: sync beamtime first with explicit cancelled=False on bl2 and default cancelled=None on bl1
        DummyBeamtimeAndDowntimeProvider.beamtime_to_return = [
            ExternalBeamtimeData(
                beamline_acronym="08ID-1",
                start=t0,
                end=t1,
                project_source_id="PROP-DT",
                cancelled=None,
                source_id="BT-SEP-DEFAULT",
            ),
            ExternalBeamtimeData(
                beamline_acronym="08BM-1",
                start=t0,
                end=t1,
                project_source_id="PROP-DT",
                cancelled=False,
                source_id="BT-SEP-EXPLICIT-FALSE",
            ),
        ]
        provider.sync(win_start, win_end, types=["beamtime"], force=True)

        # 2. Separate call: sync facility downtime covering [t0, t1]
        DummyBeamtimeAndDowntimeProvider.downtime_to_return = [
            ExternalDowntimeData(
                start=t0,
                end=t1,
                scope=Downtime.SCOPE_CHOICES.FACILITY,
                beamline_acronym=None,
                source_id="DT-SEP-FAC",
            )
        ]
        provider.sync(win_start, win_end, types=["downtime"], force=True)

        # BT-SEP-DEFAULT was cancelled by downtime; BT-SEP-EXPLICIT-FALSE remained False even in a separate sync call
        self.assertTrue(Beamtime.objects.get(source_id="BT-SEP-DEFAULT").cancelled)
        self.assertFalse(Beamtime.objects.get(source_id="BT-SEP-EXPLICIT-FALSE").cancelled)

        # 3. Upstream removes the downtime; syncing ["beamtime", "downtime"] must not leave BT-SEP-DEFAULT cancelled
        DummyBeamtimeAndDowntimeProvider.downtime_to_return = []
        provider.sync(win_start, win_end, types=["beamtime", "downtime"], force=True)
        self.assertFalse(Beamtime.objects.get(source_id="BT-SEP-DEFAULT").cancelled)

    @patch("basiclive.core.schedule.providers.httpx2.get")
    def test_http_schedule_provider_fetch_downtime(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "downtime": [
                {
                    "id": "DT-901",
                    "start": "2026-06-02T00:00:00-06:00",
                    "end": "2026-06-02T08:00:00-06:00",
                    "scope": "FACILITY",
                    "comments": "Storage ring dump",
                },
                {
                    "id": "DT-902",
                    "beamline": "08BM-1",
                    "start": "2026-06-02T08:00:00-06:00",
                    "end": "2026-06-02T16:00:00-06:00",
                    "scope": "BEAMLINE",
                    "comments": "Shutter repair",
                },
            ]
        }
        mock_get.return_value = mock_resp

        provider = HttpScheduleProvider(
            base_url="https://schedule.facility.example.org/api",
            endpoints={"downtime": "/downtime?start={start}&end={end}"},
        )
        self.assertTrue(provider.supports("downtime"))

        items = list(provider.fetch_downtime(date(2026, 6, 1), date(2026, 6, 8)))
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].source_id, "DT-901")
        self.assertIsNone(items[0].beamline_acronym)
        self.assertEqual(items[0].scope, Downtime.SCOPE_CHOICES.FACILITY)
        self.assertEqual(items[0].comments, "Storage ring dump")

        self.assertEqual(items[1].source_id, "DT-902")
        self.assertEqual(items[1].beamline_acronym, "08BM-1")
        self.assertEqual(items[1].scope, Downtime.SCOPE_CHOICES.BEAMLINE)
        self.assertEqual(items[1].comments, "Shutter repair")


class DummySupportProvider(BaseScheduleProvider):
    support_to_return: list[ExternalSupportData] = []

    def fetch_support(self, start: date, end: date):
        return list(self.support_to_return)


class ScheduleSupportSyncTests(TestCase):
    def setUp(self):
        cache.clear()
        self.staff1 = User.objects.create_user(
            username="jdoe",
            email="jdoe@facility.example.org",
            first_name="Jane",
            last_name="Doe",
            is_staff=True,
        )
        self.staff2 = User.objects.create_user(
            username="rsmith",
            email="rsmith@facility.example.org",
            first_name="Robert",
            last_name="Smith",
            is_staff=True,
        )

    def tearDown(self):
        cache.clear()

    def test_sync_support_matches_username_or_email_warns_on_unknown_and_preserves_local(self):
        win_start = date(2026, 6, 1)
        win_end = date(2026, 6, 8)

        # Local support entry (source_id=None) -> must be preserved
        local_sup = BeamlineSupport.objects.create(
            staff=self.staff1,
            date=date(2026, 6, 1),
            source_id=None,
        )

        # Stale external support entry in window -> must be pruned
        stale_sup = BeamlineSupport.objects.create(
            staff=self.staff2,
            date=date(2026, 6, 2),
            source_id="SUP-STALE-1",
        )

        # External support entry outside window -> must not be pruned
        outside_sup = BeamlineSupport.objects.create(
            staff=self.staff1,
            date=date(2026, 7, 1),
            source_id="SUP-OUTSIDE-1",
        )

        DummySupportProvider.support_to_return = [
            # Matched by username (case-insensitive)
            ExternalSupportData(
                date=date(2026, 6, 3),
                staff_username="JDOE",
                source_id="SUP-101",
            ),
            # Matched by email (case-insensitive), composite source_id
            ExternalSupportData(
                date=date(2026, 6, 4),
                staff_email="RSMITH@FACILITY.EXAMPLE.ORG",
                source_id=None,
            ),
            # Unknown staff -> must log/emit warning and NOT auto-create user
            ExternalSupportData(
                date=date(2026, 6, 5),
                staff_username="unknown_staff",
                staff_email="unknown@facility.example.org",
                source_id="SUP-UNKNOWN-1",
            ),
        ]

        initial_user_count = User.objects.count()
        provider = DummySupportProvider(cache_ttl=900)
        with self.assertLogs("basiclive.core.schedule.providers", level="WARNING") as cm:
            stats = provider.sync(win_start, win_end, types=["support"])

        self.assertEqual(stats["support"], 2)
        self.assertTrue(any("unknown_staff" in msg for msg in cm.output))
        self.assertEqual(User.objects.count(), initial_user_count)

        # Stale deleted, local & outside preserved
        self.assertFalse(BeamlineSupport.objects.filter(pk=stale_sup.pk).exists())
        self.assertTrue(BeamlineSupport.objects.filter(pk=local_sup.pk).exists())
        self.assertTrue(BeamlineSupport.objects.filter(pk=outside_sup.pk).exists())

        sup1 = BeamlineSupport.objects.get(source_id="SUP-101")
        self.assertEqual(sup1.staff, self.staff1)
        self.assertEqual(sup1.date, date(2026, 6, 3))

        sup2 = BeamlineSupport.objects.get(date=date(2026, 6, 4))
        self.assertEqual(sup2.staff, self.staff2)
        self.assertIsNotNone(sup2.source_id)

        self.assertFalse(BeamlineSupport.objects.filter(date=date(2026, 6, 5)).exists())

    @patch("basiclive.core.schedule.providers.httpx2.get")
    def test_http_schedule_provider_fetch_support_and_calendar_view_lazy_sync(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "support": [
                {
                    "id": "SUP-801",
                    "date": "2026-06-03",
                    "username": "jdoe",
                    "email": "jdoe@facility.example.org",
                }
            ]
        }
        mock_get.return_value = mock_resp

        provider = HttpScheduleProvider(
            base_url="https://schedule.facility.example.org/api",
            endpoints={"support": "/support?start={start}&end={end}"},
        )
        self.assertTrue(provider.supports("support"))
        items = list(provider.fetch_support(date(2026, 6, 1), date(2026, 6, 8)))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_id, "SUP-801")
        self.assertEqual(items[0].date, date(2026, 6, 3))
        self.assertEqual(items[0].staff_username, "jdoe")

        # Verify calendar_view lazy sync populates week[date]['support']
        DummySupportProvider.support_to_return = items
        with override_settings(
            BASICLIVE_SCHEDULE={
                "SCHEDULE_PROVIDER": "basiclive.core.schedule.tests.test_schedule_providers.DummySupportProvider"
            }
        ):
            info = calendar_view(2026, 23)
            self.assertEqual(info["week"]["2026-06-03"]["support"].staff, self.staff1)


class ScheduleHybridUIGuardTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="sched_admin", email="admin@example.org", password="secret"
        )
        self.beamline = Beamline.objects.create(
            name="08ID-1", acronym="08ID-1", active=True, simulated=False
        )
        self.project = Project.objects.create(name="PRJ-GUARD")
        self.access = AccessType.objects.create(
            name="Regular",
            email_subject="Beamtime on {beamline}",
            email_body="Body",
        )
        self.start = timezone.make_aware(datetime(2026, 6, 4, 8, 0, 0))
        self.end = self.start + timedelta(hours=8)

        self.local_bt = Beamtime.objects.create(
            project=self.project,
            beamline=self.beamline,
            access=self.access,
            start=self.start,
            end=self.end,
            comments="Local shift",
            source_id=None,
        )
        self.ext_bt = Beamtime.objects.create(
            project=self.project,
            beamline=self.beamline,
            access=self.access,
            start=self.start + timedelta(days=1),
            end=self.end + timedelta(days=1),
            comments="External shift",
            source_id="EXT-BT-55",
        )

        self.local_dt = Downtime.objects.create(
            beamline=self.beamline,
            scope=Downtime.SCOPE_CHOICES.BEAMLINE,
            start=self.start,
            end=self.end,
            comments="Local downtime",
            source_id=None,
        )
        self.ext_dt = Downtime.objects.create(
            beamline=self.beamline,
            scope=Downtime.SCOPE_CHOICES.FACILITY,
            start=self.start + timedelta(days=1),
            end=self.end + timedelta(days=1),
            comments="External downtime",
            source_id="EXT-DT-55",
        )
        self.client.force_login(self.admin)

    def test_beamtime_edit_and_delete_guard_external_records_and_allow_local(self):
        # External Beamtime -> 403 on edit GET/POST and delete GET/POST
        ext_edit_get = self.client.get(reverse("beamtime-edit", kwargs={"pk": self.ext_bt.pk}))
        self.assertEqual(ext_edit_get.status_code, 403)
        ext_edit_post = self.client.post(
            reverse("beamtime-edit", kwargs={"pk": self.ext_bt.pk}),
            data={"comments": "Attempted overwrite"},
        )
        self.assertEqual(ext_edit_post.status_code, 403)
        self.ext_bt.refresh_from_db()
        self.assertEqual(self.ext_bt.comments, "External shift")

        ext_del_get = self.client.get(reverse("beamtime-delete", kwargs={"pk": self.ext_bt.pk}))
        self.assertEqual(ext_del_get.status_code, 403)
        ext_del_post = self.client.post(reverse("beamtime-delete", kwargs={"pk": self.ext_bt.pk}))
        self.assertEqual(ext_del_post.status_code, 403)
        self.assertTrue(Beamtime.objects.filter(pk=self.ext_bt.pk).exists())

        # Local Beamtime -> 200 on edit GET, editable and deletable
        loc_edit_get = self.client.get(reverse("beamtime-edit", kwargs={"pk": self.local_bt.pk}))
        self.assertEqual(loc_edit_get.status_code, 200)
        loc_del_get = self.client.get(reverse("beamtime-delete", kwargs={"pk": self.local_bt.pk}))
        self.assertEqual(loc_del_get.status_code, 200)
        loc_del_post = self.client.post(reverse("beamtime-delete", kwargs={"pk": self.local_bt.pk}))
        self.assertIn(loc_del_post.status_code, (200, 302))
        self.assertFalse(Beamtime.objects.filter(pk=self.local_bt.pk).exists())

    def test_downtime_edit_guards_external_records_and_allows_local(self):
        # External Downtime -> 403 on edit GET/POST
        ext_dt_get = self.client.get(reverse("downtime-edit", kwargs={"pk": self.ext_dt.pk}))
        self.assertEqual(ext_dt_get.status_code, 403)
        ext_dt_post = self.client.post(
            reverse("downtime-edit", kwargs={"pk": self.ext_dt.pk}),
            data={"submit": "Delete"},
        )
        self.assertEqual(ext_dt_post.status_code, 403)
        self.assertTrue(Downtime.objects.filter(pk=self.ext_dt.pk).exists())

        # Local Downtime -> 200 on edit GET
        loc_dt_get = self.client.get(reverse("downtime-edit", kwargs={"pk": self.local_dt.pk}))
        self.assertEqual(loc_dt_get.status_code, 200)

    def test_local_beamtime_and_downtime_creation_do_not_truncate_delete_or_split_external_beamtime(self):
        ext_start = self.start + timedelta(days=2)
        ext_end = ext_start + timedelta(hours=24)
        ext_bt = Beamtime.objects.create(
            project=self.project,
            beamline=self.beamline,
            access=self.access,
            start=ext_start,
            end=ext_end,
            comments="Protected external beamtime",
            source_id="EXT-PROTECTED-1",
        )
        local_overlap_bt = Beamtime.objects.create(
            project=self.project,
            beamline=self.beamline,
            access=self.access,
            start=ext_start,
            end=ext_end,
            comments="Local beamtime to be split/trimmed",
            source_id=None,
        )

        # Creating a local beamtime inside [ext_start, ext_end] must NOT delete or truncate ext_bt
        mid_start = ext_start + timedelta(hours=8)
        mid_end = ext_start + timedelta(hours=16)
        create_bt_resp = self.client.post(
            reverse("new-beamtime"),
            data={
                "project": self.project.pk,
                "beamline": self.beamline.pk,
                "access": self.access.pk,
                "start": timezone.localtime(mid_start).strftime("%Y-%m-%d %H:%M"),
                "end": timezone.localtime(mid_end).strftime("%Y-%m-%d %H:%M"),
                "comments": "New local shift",
                "notify": False,
            },
        )
        self.assertIn(create_bt_resp.status_code, (200, 302))
        ext_bt.refresh_from_db()
        self.assertEqual(ext_bt.start, ext_start)
        self.assertEqual(ext_bt.end, ext_end)
        self.assertEqual(Beamtime.objects.filter(source_id="EXT-PROTECTED-1").count(), 1)

        # Creating a local downtime inside [ext_start, ext_end] must NOT split ext_bt or duplicate its source_id
        dt_start = ext_start + timedelta(hours=8)
        dt_end = ext_start + timedelta(hours=16)
        create_dt_resp = self.client.post(
            reverse("new-downtime"),
            data={
                "beamline": self.beamline.pk,
                "scope": Downtime.SCOPE_CHOICES.BEAMLINE,
                "start": timezone.localtime(dt_start).strftime("%Y-%m-%d %H:%M"),
                "end": timezone.localtime(dt_end).strftime("%Y-%m-%d %H:%M"),
                "comments": "Local maintenance window",
            },
        )
        self.assertIn(create_dt_resp.status_code, (200, 302))
        ext_bt.refresh_from_db()
        self.assertEqual(ext_bt.start, ext_start)
        self.assertEqual(ext_bt.end, ext_end)
        self.assertEqual(Beamtime.objects.filter(source_id="EXT-PROTECTED-1").count(), 1)







