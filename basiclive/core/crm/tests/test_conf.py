import unittest

from django.test import SimpleTestCase, override_settings

from basiclive.core.crm.conf import settings as crm_settings
from basiclive.core.lims.conf import settings as lims_settings


class CrmConfTests(SimpleTestCase):
    def test_default_settings(self):
        self.assertEqual(dict(crm_settings), {})

    def test_crm_views_use_schedule_resolution(self):
        # Default in lims_settings is True
        self.assertIs(lims_settings.USE_SCHEDULE, True)

        with override_settings(BASICLIVE_LIMS={"USE_SCHEDULE": False}):
            self.assertIs(lims_settings.USE_SCHEDULE, False)

        self.assertIs(lims_settings.USE_SCHEDULE, True)


if __name__ == "__main__":
    unittest.main()
