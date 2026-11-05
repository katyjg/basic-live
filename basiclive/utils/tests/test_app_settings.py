import unittest
from django.conf import settings as django_settings
from django.test import SimpleTestCase, override_settings

from basiclive.utils.conf import AppSettings


class AppSettingsTests(SimpleTestCase):
    def test_prefix_normalization(self):
        conf1 = AppSettings("sample", {"KEY": 1})
        self.assertEqual(conf1.namespace, "BASICLIVE_SAMPLE")

        conf2 = AppSettings("BASICLIVE_SAMPLE", {"KEY": 1})
        self.assertEqual(conf2.namespace, "BASICLIVE_SAMPLE")

    def test_default_values(self):
        defaults = {
            "TIMEOUT": 30,
            "ENABLED": True,
            "ITEMS": [1, 2, 3],
        }
        app_settings = AppSettings("DEFAULTS_TEST", defaults)

        self.assertEqual(app_settings.TIMEOUT, 30)
        self.assertIs(app_settings.ENABLED, True)
        self.assertEqual(app_settings.ITEMS, [1, 2, 3])

    def test_django_settings_override(self):
        defaults = {
            "CUSTOM_OPTION": "default_val",
            "OTHER_OPTION": 42,
        }
        with override_settings(BASICLIVE_TESTAPP={"CUSTOM_OPTION": "overridden"}):
            app_settings = AppSettings("TESTAPP", defaults)
            self.assertEqual(app_settings.CUSTOM_OPTION, "overridden")
            self.assertEqual(app_settings.OTHER_OPTION, 42)

    def test_dynamic_override_settings(self):
        defaults = {"MAX_COUNT": 10}
        app_settings = AppSettings("DYNAMIC_TEST", defaults)

        self.assertEqual(app_settings.MAX_COUNT, 10)

        with override_settings(BASICLIVE_DYNAMIC_TEST={"MAX_COUNT": 99}):
            self.assertEqual(app_settings.MAX_COUNT, 99)

        self.assertEqual(app_settings.MAX_COUNT, 10)

    def test_invalid_setting_raises_attribute_error(self):
        app_settings = AppSettings("ATTR_TEST", {"VALID": "yes"})

        with self.assertRaises(AttributeError) as ctx:
            _ = app_settings.UNKNOWN
        self.assertIn("Invalid setting 'UNKNOWN' for 'BASICLIVE_ATTR_TEST'", str(ctx.exception))

    def test_read_only_protection(self):
        app_settings = AppSettings("MUTATE_TEST", {"READ_ONLY_VAR": 100})

        with self.assertRaises(AttributeError) as ctx:
            app_settings.READ_ONLY_VAR = 200
        self.assertIn("attributes are read-only", str(ctx.exception))

    def test_dict_and_container_interface(self):
        defaults = {
            "FOO": "bar",
            "NUM": 123,
        }
        app_settings = AppSettings("CONTAINER_TEST", defaults)

        # __contains__
        self.assertIn("FOO", app_settings)
        self.assertNotIn("NON_EXISTENT", app_settings)

        # __getitem__
        self.assertEqual(app_settings["FOO"], "bar")
        with self.assertRaises(KeyError):
            _ = app_settings["MISSING"]

        # get()
        self.assertEqual(app_settings.get("FOO"), "bar")
        self.assertIsNone(app_settings.get("MISSING"))
        self.assertEqual(app_settings.get("MISSING", "fallback"), "fallback")

        # dir()
        self.assertIn("FOO", dir(app_settings))
        self.assertIn("NUM", dir(app_settings))

        # iteration and keys
        self.assertEqual(list(app_settings), ["FOO", "NUM"])
        self.assertEqual(list(app_settings.keys()), ["FOO", "NUM"])
        self.assertEqual(dict(app_settings), {"FOO": "bar", "NUM": 123})

        # repr
        self.assertEqual(repr(app_settings), "<AppSettings namespace='BASICLIVE_CONTAINER_TEST'>")


if __name__ == "__main__":
    unittest.main()
