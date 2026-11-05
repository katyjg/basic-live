import unittest
from django.apps import apps
from django.test import RequestFactory, SimpleTestCase, override_settings


from basiclive.core.context_processors import export_settings
from basiclive.core.lims.conf import settings as lims_settings
from basiclive.core.notebooks.conf import settings as notebook_settings


class NotebooksConfTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_default_settings(self):
        self.assertEqual(notebook_settings.PAGE_SIZE, 10)
        self.assertEqual(notebook_settings.MAX_ENTRY_SIZE, 25 * 1024 * 1024)
        self.assertIs(lims_settings.USE_NOTEBOOKS, True)

    def test_dynamic_override_via_basiclive_notebooks(self):
        with override_settings(
            BASICLIVE_NOTEBOOKS={
                "PAGE_SIZE": 25,
                "MAX_ENTRY_SIZE": 50 * 1024 * 1024,
            }
        ):
            self.assertEqual(notebook_settings.PAGE_SIZE, 25)
            self.assertEqual(notebook_settings.MAX_ENTRY_SIZE, 50 * 1024 * 1024)

        # Restores defaults after context exit
        self.assertEqual(notebook_settings.PAGE_SIZE, 10)
        self.assertEqual(notebook_settings.MAX_ENTRY_SIZE, 25 * 1024 * 1024)

    def test_lims_use_notebooks_override(self):
        self.assertIs(lims_settings.USE_NOTEBOOKS, True)
        with override_settings(BASICLIVE_LIMS={"USE_NOTEBOOKS": False}):
            self.assertIs(lims_settings.USE_NOTEBOOKS, False)
        self.assertIs(lims_settings.USE_NOTEBOOKS, True)

    def test_context_processor_export_settings(self):
        request = self.factory.get("/")
        exported = export_settings(request)
        self.assertIn("USE_NOTEBOOKS", exported)
        self.assertIs(exported["USE_NOTEBOOKS"], True)

        with override_settings(BASICLIVE_LIMS={"USE_NOTEBOOKS": False}):
            exported = export_settings(request)
            self.assertIs(exported["USE_NOTEBOOKS"], False)

    def test_app_config(self):
        app_config = apps.get_app_config("notebooks")
        self.assertEqual(app_config.name, "basiclive.core.notebooks")
        self.assertEqual(app_config.verbose_name, "Electronic Notebooks")


if __name__ == "__main__":
    unittest.main()
