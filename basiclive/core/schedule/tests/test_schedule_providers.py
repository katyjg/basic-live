from datetime import date, datetime, timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

import httpx2
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from basiclive.core.schedule.models import FacilityMode, FacilityModeType
from basiclive.core.schedule.providers import (
    BaseScheduleProvider,
    ExternalModeData,
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


