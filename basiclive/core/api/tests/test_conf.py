import unittest
from django.test import SimpleTestCase, override_settings

from basiclive.core.api.conf import settings as api_settings
from basiclive.core.api.views import get_hours_per_shift as api_get_hours_per_shift
from basiclive.core.lims.conf import settings as lims_settings


class ApiConfTests(SimpleTestCase):
    def test_default_settings(self):
        self.assertEqual(dict(api_settings), {})

    def test_cross_app_resolution_in_api_views(self):
        self.assertEqual(api_get_hours_per_shift(), 8)
        with override_settings(BASICLIVE_SCHEDULE={"HOURS_PER_SHIFT": 6}):
            self.assertEqual(api_get_hours_per_shift(), 6)
        self.assertEqual(api_get_hours_per_shift(), 8)

        # Cross-app lims settings used in api views
        self.assertIs(lims_settings.USE_SCHEDULE, True)
        self.assertEqual(lims_settings.MAX_CONTAINER_DEPTH, 2)
        with override_settings(
            BASICLIVE_LIMS={
                "MAX_CONTAINER_DEPTH": 4,
                "DOWNLOAD_PROXY_URL": "http://proxy.example.com",
            }
        ):
            self.assertEqual(lims_settings.MAX_CONTAINER_DEPTH, 4)
            self.assertEqual(lims_settings.DOWNLOAD_PROXY_URL, "http://proxy.example.com")
