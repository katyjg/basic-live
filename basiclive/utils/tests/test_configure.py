from pathlib import Path
from django.test import SimpleTestCase

from basiclive.utils import configure, BASICLIVE_APPS, OPTIONAL_APPS, EXTRA_SETTINGS


class ConfigureTests(SimpleTestCase):
    def setUp(self):
        self.base_dir = Path("/mock/base")
        self.project_dir = self.base_dir / "vanilla"

    def _get_base_settings(self):
        return {
            "PROJECT_DIR": self.project_dir,
            "BASE_DIR": self.base_dir,
            "INSTALLED_APPS": [
                "django.contrib.admin",
                "django.contrib.auth",
            ],
            "MIDDLEWARE": [
                "django.middleware.security.SecurityMiddleware",
                "django.contrib.sessions.middleware.SessionMiddleware",
            ],
            "AUTHENTICATION_BACKENDS": [
                "django.contrib.auth.backends.ModelBackend",
            ],
            "BASICLIVE_LIMS": {
                "APP_NAME": "TestLIVE",
            },
        }

    def test_configure_injects_defaults(self):
        settings = self._get_base_settings()
        configure(settings)

        # Extra settings injected
        for key, val in EXTRA_SETTINGS.items():
            self.assertEqual(settings[key], val)

        # Roots configured
        self.assertEqual(settings["STATIC_ROOT"], self.base_dir / "static")
        self.assertEqual(
            settings["STATICFILES_DIRS"],
            [self.project_dir / "static", self.project_dir / "static" / "assets"],
        )
        self.assertEqual(settings["MEDIA_ROOT"], self.base_dir / "local" / "media")

        # Installed apps populated
        for app in BASICLIVE_APPS:
            self.assertIn(app, settings["INSTALLED_APPS"])
        for app in OPTIONAL_APPS.values():
            self.assertIn(app, settings["INSTALLED_APPS"])

        # Middlewares injected in correct positions
        self.assertEqual(
            settings["MIDDLEWARE"][0],
            "basiclive.core.acl.middleware.TrustedAccessMiddleware",
        )
        self.assertEqual(
            settings["MIDDLEWARE"][-2:],
            [
                "basiclive.core.api.middleware.APIAuthenticationMiddleware",
                "basiclive.core.lims.middleware.ProjectContextMiddleware",
            ],
        )

    def test_configure_optional_apps_toggle(self):
        settings = self._get_base_settings()
        settings["BASICLIVE_LIMS"]["USE_CRM"] = False
        settings["BASICLIVE_LIMS"]["USE_SCHEDULE"] = False
        configure(settings)

        self.assertNotIn("basiclive.core.crm", settings["INSTALLED_APPS"])
        self.assertNotIn("basiclive.core.schedule", settings["INSTALLED_APPS"])
        self.assertIn("basiclive.core.notebooks", settings["INSTALLED_APPS"])
        self.assertIn("basiclive.core.publications", settings["INSTALLED_APPS"])

    def test_configure_auth_backends(self):
        settings = self._get_base_settings()
        settings["BASICLIVE_AUTH_PROVIDERS"] = ["ldap", "cas"]
        configure(settings)

        self.assertIn(
            "django_python3_ldap.auth.LDAPBackend",
            settings["AUTHENTICATION_BACKENDS"],
        )
        self.assertIn(
            "django_cas_ng.backends.CASBackend",
            settings["AUTHENTICATION_BACKENDS"],
        )

    def test_configure_tolerates_missing_basiclive_lims(self):
        settings = self._get_base_settings()
        del settings["BASICLIVE_LIMS"]
        configure(settings)

        # All optional apps default to True
        for app in OPTIONAL_APPS.values():
            self.assertIn(app, settings["INSTALLED_APPS"])
