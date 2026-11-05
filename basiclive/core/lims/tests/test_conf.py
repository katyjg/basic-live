import unittest
from django.conf import settings as django_settings
from django.template import Context, Template
from django.test import SimpleTestCase, override_settings

from basiclive.core.lims.conf import settings as lims_settings




class LimsConfTests(SimpleTestCase):
    def test_default_settings(self):
        self.assertIs(lims_settings.USE_SCHEDULE, True)
        self.assertIs(lims_settings.USE_ACL, True)
        self.assertIs(lims_settings.USE_CRM, True)
        self.assertIs(lims_settings.USE_PUBLICATIONS, True)
        self.assertEqual(lims_settings.MAX_CONTAINER_DEPTH, 2)
        self.assertIs(lims_settings.RESTRICT_DOWNLOADS, False)
        self.assertEqual(lims_settings.LOADER_SELECT_DURATION, 300)
        self.assertEqual(lims_settings.SIMULATED_SESSION_LIFETIME_DAYS, 30)
        self.assertIsNone(lims_settings.PROJECT_PROVIDER)

    def test_override_via_basiclive_lims(self):
        with override_settings(
            BASICLIVE_LIMS={
                "MAX_CONTAINER_DEPTH": 4,
                "DOWNLOAD_PROXY_URL": "https://custom-proxy.example.com",
                "USE_SCHEDULE": False,
                "SIMULATED_SESSION_LIFETIME_DAYS": 14,
            }
        ):
            self.assertEqual(lims_settings.MAX_CONTAINER_DEPTH, 4)
            self.assertEqual(lims_settings.DOWNLOAD_PROXY_URL, "https://custom-proxy.example.com")
            self.assertIs(lims_settings.USE_SCHEDULE, False)
            self.assertEqual(lims_settings.SIMULATED_SESSION_LIFETIME_DAYS, 14)
            # Non-overridden setting keeps default
            self.assertIs(lims_settings.USE_ACL, True)

        # Restores after context exit
        self.assertEqual(lims_settings.MAX_CONTAINER_DEPTH, 2)
        self.assertIs(lims_settings.USE_SCHEDULE, True)
        self.assertEqual(lims_settings.SIMULATED_SESSION_LIFETIME_DAYS, 30)

if __name__ == "__main__":
    unittest.main()
