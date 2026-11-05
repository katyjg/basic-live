import unittest

from django.test import SimpleTestCase, override_settings

from basiclive.auth.cas.conf import settings as cas_settings


class CasConfTests(SimpleTestCase):
    def test_default_settings(self):
        self.assertEqual(cas_settings.SERVER_URL, "https://cas-test.clsi.ca/")
        self.assertEqual(cas_settings.SERVICE_DESCRIPTION, "LIVE")
        self.assertIs(cas_settings.LOGOUT_COMPLETELY, True)
        self.assertIs(cas_settings.CREATE_USER, True)
        self.assertEqual(cas_settings.REDIRECT_URL, "login")
        self.assertEqual(cas_settings.LOGIN_URL_NAME, "login")
        self.assertEqual(cas_settings.LOGOUT_URL_NAME, "logout")

    def test_prefixed_and_unprefixed_attribute_access(self):
        self.assertEqual(cas_settings.SERVER_URL, "https://cas-test.clsi.ca/")
        self.assertEqual(cas_settings.CAS_SERVER_URL, "https://cas-test.clsi.ca/")
        self.assertIs(cas_settings.CREATE_USER, True)
        self.assertIs(cas_settings.CAS_CREATE_USER, True)

    def test_override_via_basiclive_cas(self):
        with override_settings(
            BASICLIVE_CAS={
                "SERVER_URL": "https://cas.facility.ca/",
                "CREATE_USER": False,
                "SERVICE_DESCRIPTION": "MySynchrotron",
            }
        ):
            self.assertEqual(cas_settings.SERVER_URL, "https://cas.facility.ca/")
            self.assertEqual(cas_settings.CAS_SERVER_URL, "https://cas.facility.ca/")
            self.assertIs(cas_settings.CREATE_USER, False)
            self.assertIs(cas_settings.CAS_CREATE_USER, False)
            self.assertEqual(cas_settings.SERVICE_DESCRIPTION, "MySynchrotron")

        # Restored
        self.assertEqual(cas_settings.SERVER_URL, "https://cas-test.clsi.ca/")
        self.assertIs(cas_settings.CREATE_USER, True)

    def test_override_via_fallback_namespace(self):
        with override_settings(BASICLIVE_AUTH_CAS={"SERVER_URL": "https://auth-cas.org/"}):
            self.assertEqual(cas_settings.SERVER_URL, "https://auth-cas.org/")

        self.assertEqual(cas_settings.SERVER_URL, "https://cas-test.clsi.ca/")


if __name__ == "__main__":
    unittest.main()
