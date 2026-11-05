import datetime
import unittest

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase, override_settings

from basiclive.core.publications import models
from basiclive.core.publications.views import PDBDetail, PDBEntryList

User = get_user_model()


@override_settings(ROOT_URLCONF="vanilla.urls")
class PublicationsViewsTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="normaluser", password="password123", name="Normal User"
        )
        self.admin = User.objects.create_superuser(
            username="adminuser", password="password123", name="Admin User"
        )

        self.publication = models.Publication.objects.create(
            code="10.1000/182",
            title="Structural Insights into Hemoglobin",
            author_names="Perutz, M. F.",
            published=datetime.date(2020, 1, 1),
        )

        self.deposition = models.Deposition.objects.create(
            code="4HHB",
            title="The crystal structure of human deoxyhaemoglobin at 1.74 A resolution",
            authors="Fermi, G., Perutz, M.F., Shaanan, B., Fourme, R.",
            doi="10.2210/pdb4hhb/pdb",
            resolution=1.74,
            released=datetime.date(1984, 7, 17),
            deposited=datetime.date(1984, 7, 1),
            collected=None,
            reference=self.publication,
        )

    def test_pdb_detail_admin_required(self):
        req = self.factory.get("/publications/pdbs/4HHB/")
        req.user = self.user

        view = PDBDetail.as_view()
        with self.assertRaises(PermissionDenied):
            view(req, code="4HHB")

    def test_pdb_detail_success_for_admin(self):
        req = self.factory.get("/publications/pdbs/4HHB/")
        req.user = self.admin

        view = PDBDetail.as_view()
        response = view(req, code="4HHB")
        self.assertEqual(response.status_code, 200)

        rendered = response.render().content.decode("utf-8")
        self.assertIn("4HHB", rendered)
        self.assertIn("https://cdn.rcsb.org/images/structures/4hhb_assembly-1.jpeg", rendered)
        self.assertIn("1.74", rendered)
        self.assertIn("Fermi, G., Perutz, M.F.", rendered)
        self.assertIn("Structural Insights into Hemoglobin", rendered)

    def test_pdb_detail_case_insensitive_lookup(self):
        req = self.factory.get("/publications/pdbs/4hhb/")
        req.user = self.admin

        view = PDBDetail.as_view()
        response = view(req, code="4hhb")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context_data["object"].code, "4HHB")

    def test_pdb_entry_list_renders_modal_trigger_link(self):
        req = self.factory.get("/publications/pdbs/")
        req.user = self.admin

        view = PDBEntryList.as_view()
        response = view(req)
        self.assertEqual(response.status_code, 200)

        rendered = response.render().content.decode("utf-8")
        # Should link to modal URL instead of rcsb.org
        self.assertIn('data-modal-url="/publications/pdbs/4HHB/"', rendered)


if __name__ == "__main__":
    unittest.main()
