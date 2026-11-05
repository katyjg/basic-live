import unittest
from django.http import Http404
from django.test import RequestFactory, SimpleTestCase, override_settings

from basiclive.core.acl.conf import settings as acl_settings
from basiclive.core.acl.middleware import TrustedAccessMiddleware
from basiclive.core.acl.models import get_hours_per_shift as acl_get_hours_per_shift


class AclConfTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_default_settings(self):
        self.assertEqual(acl_settings.TRUSTED_IPS, ["127.0.0.1/32"])
        self.assertEqual(acl_settings.TRUSTED_URLS, ['^/json', '^/api'])

    def test_override_via_basiclive_acl(self):
        with override_settings(
            BASICLIVE_ACL={
                "TRUSTED_IPS": ["10.0.0.0/8", "192.168.1.0/24"],
                "TRUSTED_URLS": [r"^/admin/", r"^/restricted/"],
            }
        ):
            self.assertEqual(acl_settings.TRUSTED_IPS, ["10.0.0.0/8", "192.168.1.0/24"])
            self.assertEqual(acl_settings.TRUSTED_URLS, [r"^/admin/", r"^/restricted/"])

        # Restores to defaults after context exit
        self.assertEqual(acl_settings.TRUSTED_IPS, ["127.0.0.1/32"])
        self.assertEqual(acl_settings.TRUSTED_URLS, ['^/json', '^/api'])

    def test_trusted_access_middleware_allowed_unprotected_url(self):
        middleware = TrustedAccessMiddleware(lambda request: None)
        request = self.factory.get("/public/path", REMOTE_ADDR="203.0.113.1")
        # Should not raise any exception for URLs not matching TRUSTED_URLS
        middleware.process_request(request)

    def test_trusted_access_middleware_protected_url(self):
        middleware = TrustedAccessMiddleware(lambda request: None)

        with override_settings(
            BASICLIVE_ACL={
                "TRUSTED_IPS": ["192.168.1.0/24"],
                "TRUSTED_URLS": [r"^/admin/"],
            }
        ):
            # Allowed IP
            req_allowed = self.factory.get("/admin/dashboard", REMOTE_ADDR="192.168.1.42")
            middleware.process_request(req_allowed)

            # Denied IP
            req_denied = self.factory.get("/admin/dashboard", REMOTE_ADDR="10.0.0.1")
            with self.assertRaises(Http404):
                middleware.process_request(req_denied)

    def test_cross_app_hours_per_shift_resolution(self):
        self.assertEqual(acl_get_hours_per_shift(), 8)
        with override_settings(BASICLIVE_SCHEDULE={"HOURS_PER_SHIFT": 12}):
            self.assertEqual(acl_get_hours_per_shift(), 12)
        self.assertEqual(acl_get_hours_per_shift(), 8)
