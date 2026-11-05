import unittest

from django.test import RequestFactory, SimpleTestCase, override_settings

from basiclive.utils.conf import settings as utils_settings
from basiclive.utils.functions import get_hours_per_shift
from basiclive.utils.mixins import CACHE_PREFIX, CACHE_TIMEOUT, TEMP_PREFIX
from basiclive.utils.network import get_client_address, get_trusted_proxies


class UtilsConfTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_default_settings(self):
        self.assertEqual(utils_settings.TRUSTED_PROXIES, 2)
        self.assertEqual(utils_settings.PDF_TEMP_PREFIX, "render_pdf-")
        self.assertEqual(utils_settings.PDF_CACHE_PREFIX, "render-pdf")
        self.assertEqual(utils_settings.PDF_CACHE_TIMEOUT, 30)

        # Mixin module-level exports
        self.assertEqual(TEMP_PREFIX, "render_pdf-")
        self.assertEqual(CACHE_PREFIX, "render-pdf")
        self.assertEqual(CACHE_TIMEOUT, 30)

    def test_override_via_basiclive_utils(self):
        with override_settings(
            BASICLIVE_UTILS={
                "TRUSTED_PROXIES": 4,
                "PDF_TEMP_PREFIX": "custom_temp-",
                "PDF_CACHE_PREFIX": "custom_cache",
                "PDF_CACHE_TIMEOUT": 120,
            }
        ):
            self.assertEqual(utils_settings.TRUSTED_PROXIES, 4)
            self.assertEqual(utils_settings.PDF_TEMP_PREFIX, "custom_temp-")
            self.assertEqual(utils_settings.PDF_CACHE_PREFIX, "custom_cache")
            self.assertEqual(utils_settings.PDF_CACHE_TIMEOUT, 120)

        # Restores to defaults
        self.assertEqual(utils_settings.TRUSTED_PROXIES, 2)
        self.assertEqual(utils_settings.PDF_TEMP_PREFIX, "render_pdf-")

    def test_trusted_proxies_resolution_hierarchy(self):
        # Default
        self.assertEqual(get_trusted_proxies(), 2)

        # When set in BASICLIVE_ACL
        with override_settings(BASICLIVE_ACL={"TRUSTED_PROXIES": 5}):
            self.assertEqual(get_trusted_proxies(), 5)

        # Restores
        self.assertEqual(get_trusted_proxies(), 2)

    def test_get_client_address(self):
        # Direct remote address
        req1 = self.factory.get("/", REMOTE_ADDR="198.51.100.1")
        self.assertEqual(get_client_address(req1), "198.51.100.1")

        # Forwarded for header (default depth 2: selects second from right)
        req2 = self.factory.get(
            "/",
            REMOTE_ADDR="10.0.0.1",
            HTTP_X_FORWARDED_FOR="203.0.113.195, 70.41.3.18, 150.172.238.178",
        )
        self.assertEqual(get_client_address(req2), "70.41.3.18")

        # Forwarded for with custom depth via BASICLIVE_ACL
        with override_settings(BASICLIVE_ACL={"TRUSTED_PROXIES": 1}):
            self.assertEqual(get_client_address(req2), "150.172.238.178")

    def test_functions_hours_per_shift_resolution(self):
        # Default
        self.assertEqual(get_hours_per_shift(), 8)

        # Overridden in schedule
        with override_settings(BASICLIVE_SCHEDULE={"HOURS_PER_SHIFT": 12}):
            self.assertEqual(get_hours_per_shift(), 12)

        self.assertEqual(get_hours_per_shift(), 8)


if __name__ == "__main__":
    unittest.main()
