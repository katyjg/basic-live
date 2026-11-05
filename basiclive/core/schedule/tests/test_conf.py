import unittest
from django.test import SimpleTestCase, override_settings

from basiclive.core.lims.models import get_hours_per_shift
from basiclive.core.schedule.conf import settings as schedule_settings


class ScheduleConfTests(SimpleTestCase):
    def test_default_settings(self):
        self.assertEqual(schedule_settings.HOURS_PER_SHIFT, 8)
        self.assertIsNone(schedule_settings.SCHEDULE_PROVIDER)
        self.assertEqual(schedule_settings.MIN_SUPPORT_HOUR, 0)
        self.assertEqual(schedule_settings.MAX_SUPPORT_HOUR, 24)
        self.assertEqual(schedule_settings.APP_NAME, "basiclive")
        self.assertEqual(schedule_settings.FROM_EMAIL, "sender@no-reply.ca")
        self.assertIs(schedule_settings.USE_PUBLICATIONS, True)

    def test_override_via_basiclive_schedule(self):
        with override_settings(
            BASICLIVE_SCHEDULE={
                "HOURS_PER_SHIFT": 12,
                "SCHEDULE_PROVIDER": "basiclive.core.schedule.providers.HttpScheduleProvider",
                "APP_NAME": "CustomSynchrotron",
                "FROM_EMAIL": "beamline@facility.ca",
            }
        ):
            self.assertEqual(schedule_settings.HOURS_PER_SHIFT, 12)
            self.assertEqual(
                schedule_settings.SCHEDULE_PROVIDER,
                "basiclive.core.schedule.providers.HttpScheduleProvider",
            )
            self.assertEqual(schedule_settings.APP_NAME, "CustomSynchrotron")
            self.assertEqual(schedule_settings.FROM_EMAIL, "beamline@facility.ca")
            # Non-overridden settings keep defaults
            self.assertEqual(schedule_settings.MIN_SUPPORT_HOUR, 0)
            self.assertEqual(schedule_settings.MAX_SUPPORT_HOUR, 24)

        # Restores after context exit
        self.assertEqual(schedule_settings.HOURS_PER_SHIFT, 8)
        self.assertEqual(schedule_settings.APP_NAME, "basiclive")

    def test_cross_app_hours_per_shift_resolution(self):
        # Default resolution in lims.models
        self.assertEqual(get_hours_per_shift(), 8)

        # When overridden in schedule settings
        with override_settings(BASICLIVE_SCHEDULE={"HOURS_PER_SHIFT": 6}):
            self.assertEqual(schedule_settings.HOURS_PER_SHIFT, 6)
            self.assertEqual(get_hours_per_shift(), 6)

        self.assertEqual(get_hours_per_shift(), 8)


if __name__ == "__main__":
    unittest.main()
