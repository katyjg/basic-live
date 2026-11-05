import unittest
from unittest.mock import MagicMock

from django.test import SimpleTestCase, override_settings

from basiclive.core.publications.conf import settings as pub_settings, default_tag_function
from basiclive.core.publications.utils import get_search_json
from basiclive.core.publications.views import PDBDetail, PDBEntryList


@override_settings(ROOT_URLCONF="vanilla.urls")
class PublicationsConfTests(SimpleTestCase):
    def test_default_settings(self):
        self.assertEqual(pub_settings.PDB_FACILITY_ACRONYM, "CLSI")
        self.assertEqual(pub_settings.CONTACT_EMAIL, "admin@example.com")
        self.assertIsNone(pub_settings.CROSSREF_API_KEY)
        self.assertEqual(pub_settings.CROSSREF_THROTTLE, 1)
        self.assertEqual(pub_settings.CROSSREF_BATCH_SIZE, 10)
        self.assertIsNone(pub_settings.GOOGLE_API_KEY)
        self.assertEqual(pub_settings.PDB_SEARCH_URL, "https://search.rcsb.org/rcsbsearch/v2/query")
        self.assertEqual(pub_settings.PDB_REPORT_URL, "https://data.rcsb.org/graphql")
        self.assertEqual(pub_settings.GOOGLE_BOOKS_API, "https://www.googleapis.com/books/v1/volumes")
        self.assertEqual(pub_settings.SCIMAGO_URL, "https://www.scimagojr.com/journalrank.php")
        self.assertEqual(pub_settings.PDB_URL_TEMPLATE, "https://www.rcsb.org/structure/{}")
        self.assertEqual(pub_settings.PDB_IMAGE_URL_TEMPLATE, "https://cdn.rcsb.org/images/structures/{}_assembly-1.jpeg")
        self.assertEqual(pub_settings.YEAR_FILTER_START, 2005)
        self.assertTrue(pub_settings.LOCAL_DIR)

        # Default tag function behavior
        entry = {"diffrn_source.pdbx_synchrotron_beamline": "Synchrotron 08B1-1"}
        self.assertEqual(default_tag_function(entry), ["08B1-1"])

        # Default search JSON uses PDB_FACILITY_ACRONYM
        search_json = get_search_json()
        self.assertEqual(search_json["query"]["parameters"]["value"], "CLSI")

    def test_override_via_basiclive_publications(self):
        with override_settings(
            BASICLIVE_PUBLICATIONS={
                "PDB_FACILITY_ACRONYM": "ALS",
                "CONTACT_EMAIL": "beamline@lbl.gov",
                "CROSSREF_THROTTLE": 3,
                "CROSSREF_BATCH_SIZE": 50,
                "GOOGLE_API_KEY": "secret-key",
                "PDB_URL_TEMPLATE": "https://custom.rcsb.org/entry/{}",
                "PDB_IMAGE_URL_TEMPLATE": "https://custom.rcsb.org/images/{}.png",
                "YEAR_FILTER_START": 2012,
                "PDB_TAG_FUNCTION": lambda e: ["CUSTOM_TAG"],
            }
        ):
            self.assertEqual(pub_settings.PDB_FACILITY_ACRONYM, "ALS")
            self.assertEqual(pub_settings.CONTACT_EMAIL, "beamline@lbl.gov")
            self.assertEqual(pub_settings.CROSSREF_THROTTLE, 3)
            self.assertEqual(pub_settings.CROSSREF_BATCH_SIZE, 50)
            self.assertEqual(pub_settings.GOOGLE_API_KEY, "secret-key")
            self.assertEqual(pub_settings.PDB_URL_TEMPLATE, "https://custom.rcsb.org/entry/{}")
            self.assertEqual(pub_settings.PDB_IMAGE_URL_TEMPLATE, "https://custom.rcsb.org/images/{}.png")
            self.assertEqual(pub_settings.YEAR_FILTER_START, 2012)

            # Custom tag function
            tag_function = pub_settings.PDB_TAG_FUNCTION
            self.assertEqual(tag_function({}), ["CUSTOM_TAG"])

            # Search json dynamically reflects acronym
            search_json = get_search_json()
            self.assertEqual(search_json["query"]["parameters"]["value"], "ALS")

        # Restores defaults after context exit
        self.assertEqual(pub_settings.PDB_FACILITY_ACRONYM, "CLSI")
        self.assertEqual(pub_settings.CONTACT_EMAIL, "admin@example.com")
        self.assertEqual(pub_settings.CROSSREF_THROTTLE, 1)
        self.assertEqual(pub_settings.CROSSREF_BATCH_SIZE, 10)
        self.assertIsNone(pub_settings.GOOGLE_API_KEY)
        self.assertEqual(pub_settings.PDB_URL_TEMPLATE, "https://www.rcsb.org/structure/{}")
        self.assertEqual(pub_settings.PDB_IMAGE_URL_TEMPLATE, "https://cdn.rcsb.org/images/structures/{}_assembly-1.jpeg")
        self.assertEqual(pub_settings.YEAR_FILTER_START, 2005)

    def test_pdb_entry_list_modal_links(self):
        mock_obj = MagicMock()
        mock_obj.code = "1ABC"
        view = PDBEntryList()

        self.assertEqual(view.link_field, "code")
        self.assertEqual(view.link_attr, "data-modal-url")
        self.assertEqual(str(view.get_link_url(mock_obj)), "/publications/pdbs/1ABC/")
        self.assertEqual(view.get_link_attr(mock_obj), "data-modal-url")

    def test_pdb_detail_view_context_resolution(self):
        mock_obj = MagicMock()
        mock_obj.code = "4HHB"
        view = PDBDetail()
        view.object = mock_obj

        context = view.get_context_data(object=mock_obj)
        self.assertEqual(context["pdb_url"], "https://www.rcsb.org/structure/4HHB")
        self.assertEqual(context["image_url"], "https://cdn.rcsb.org/images/structures/4hhb_assembly-1.jpeg")

        with override_settings(
            BASICLIVE_PUBLICATIONS={
                "PDB_URL_TEMPLATE": "https://custom.rcsb.org/entry/{}",
                "PDB_IMAGE_URL_TEMPLATE": "https://cdn.custom.org/{}_model.png",
            }
        ):
            context = view.get_context_data(object=mock_obj)
            self.assertEqual(context["pdb_url"], "https://custom.rcsb.org/entry/4HHB")
            self.assertEqual(context["image_url"], "https://cdn.custom.org/4hhb_model.png")

        context = view.get_context_data(object=mock_obj)
        self.assertEqual(context["pdb_url"], "https://www.rcsb.org/structure/4HHB")
        self.assertEqual(context["image_url"], "https://cdn.rcsb.org/images/structures/4hhb_assembly-1.jpeg")


if __name__ == "__main__":
    unittest.main()
