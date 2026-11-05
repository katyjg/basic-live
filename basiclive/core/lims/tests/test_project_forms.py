import unittest
from django.core.management import call_command
from django.test import TestCase

from django.core.exceptions import ValidationError
from django.urls import reverse

from basiclive.core.lims.forms import NewProjectForm, ProjectForm
from basiclive.core.lims.models import (
    User,
    Project,
    ProjectMembership,
    ProjectType,
    Carrier,
    Country,
    Region,
)


class ProjectFormsTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        call_command('migrate', verbosity=0)
        super().setUpClass()

    def setUp(self):
        self.project_type = ProjectType.objects.create(name="Standard MX")
        self.carrier = Carrier.objects.create(name="FedEx")

        self.pi = User.objects.create_user(
            username="prof_jones",
            email="jones@university.edu",
            name="Prof. Indiana Jones"
        )
        self.co_inv = User.objects.create_user(
            username="dr_marion",
            email="marion@university.edu",
            name="Dr. Marion Ravenwood"
        )
        self.member1 = User.objects.create_user(
            username="sallah",
            email="sallah@cairo.org",
            name="Sallah"
        )
        self.member2 = User.objects.create_user(
            username="shorty",
            email="shorty@club.org",
            name="Short Round"
        )
        self.admin = User.objects.create_superuser(
            username="admin",
            email="admin@example.org",
            password="adminpassword"
        )
        self.country_us = Country.objects.filter(alpha2="US").first() or Country.objects.create(
            name="United States", alpha2="US", alpha3="USA"
        )
        self.region_ct = Region.objects.filter(code="US-CT").first() or Region.objects.create(
            name="Connecticut", code="US-CT", country=self.country_us
        )
        self.country_ca = Country.objects.filter(alpha2="CA").first() or Country.objects.create(
            name="Canada", alpha2="CA", alpha3="CAN"
        )
        self.region_on = Region.objects.filter(code="CA-ON").first() or Region.objects.create(
            name="Ontario", code="CA-ON", country=self.country_ca
        )

    def test_new_project_form_successful_creation(self):
        form_data = {
            'name': 'ark-discovery',
            'kind': self.project_type.pk,
            'pi': self.pi.pk,
            'co_investigator': self.co_inv.pk,
            'members': [self.member1.pk, self.member2.pk],
            'alias': 'ARK-PROJECT',
            'contact_person': 'Marion Ravenwood',
            'contact_email': 'logistics@university.edu',
            'contact_phone': '555-019-2834',
            'carrier': self.carrier.pk,
            'account_number': '12345678',
            'shipping_notes': 'Handle with care',
            'organisation': 'Marshall College',
            'department': 'Archaeology',
            'address': '123 University Ave',
            'city': 'Bedford',
            'region': self.region_ct.pk,
            'country': self.country_us.pk,
            'postal_code': '06807',
        }
        form = NewProjectForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        project = form.save()

        self.assertEqual(project.name, 'ark-discovery')
        self.assertEqual(project.pi, self.pi)
        self.assertEqual(project.kind, self.project_type)
        self.assertEqual(project.contact_person, 'Marion Ravenwood')
        self.assertEqual(project.contact_email, 'logistics@university.edu')
        self.assertEqual(project.carrier, self.carrier)
        self.assertEqual(project.country, self.country_us)
        self.assertEqual(project.region, self.region_ct)
        self.assertEqual(project.region_code, 'CT')

        # Check memberships
        pi_membership = ProjectMembership.objects.get(project=project, user=self.pi)
        self.assertEqual(pi_membership.role, ProjectMembership.Role.PI)

        co_membership = ProjectMembership.objects.get(project=project, user=self.co_inv)
        self.assertEqual(co_membership.role, ProjectMembership.Role.CO_INVESTIGATOR)

        m1_membership = ProjectMembership.objects.get(project=project, user=self.member1)
        self.assertEqual(m1_membership.role, ProjectMembership.Role.MEMBER)

        m2_membership = ProjectMembership.objects.get(project=project, user=self.member2)
        self.assertEqual(m2_membership.role, ProjectMembership.Role.MEMBER)

        self.assertEqual(project.memberships.count(), 4)

    def test_new_project_form_requires_pi(self):
        form_data = {
            'name': 'no-pi-project',
            'kind': self.project_type.pk,
        }
        form = NewProjectForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('pi', form.errors)

    def test_new_project_form_deduplicates_pi_and_co_inv_in_members(self):
        # If PI or Co-Investigator is accidentally included in 'members',
        # their higher role should not be overridden to MEMBER.
        form_data = {
            'name': 'overlap-project',
            'kind': self.project_type.pk,
            'pi': self.pi.pk,
            'co_investigator': self.co_inv.pk,
            'members': [self.pi.pk, self.co_inv.pk, self.member1.pk],
        }
        form = NewProjectForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        project = form.save()

        self.assertEqual(project.memberships.count(), 3)
        self.assertEqual(
            ProjectMembership.objects.get(project=project, user=self.pi).role,
            ProjectMembership.Role.PI
        )
        self.assertEqual(
            ProjectMembership.objects.get(project=project, user=self.co_inv).role,
            ProjectMembership.Role.CO_INVESTIGATOR
        )
        self.assertEqual(
            ProjectMembership.objects.get(project=project, user=self.member1).role,
            ProjectMembership.Role.MEMBER
        )

    def test_project_form_edit_existing_project(self):
        project = Project.objects.create(
            name="existing-project",
            pi=self.pi,
            contact_person="Old Contact",
            city="Old Town"
        )
        edit_data = {
            'contact_person': 'New Contact',
            'contact_email': 'new@contact.org',
            'city': 'New Metropolis',
            'country': self.country_ca.pk,
            'region': self.region_on.pk,
            'kind': self.project_type.pk,
        }
        form = ProjectForm(instance=project, data=edit_data, user=self.admin)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()

        self.assertEqual(saved.contact_person, 'New Contact')
        self.assertEqual(saved.city, 'New Metropolis')
        self.assertEqual(saved.name, 'existing-project')
        self.assertEqual(saved.pi, self.pi)
        self.assertEqual(saved.country, self.country_ca)
        self.assertEqual(saved.region, self.region_on)

    def test_project_clean_auto_populates_country(self):
        project = Project(
            name="auto-country-proj",
            pi=self.pi,
            region=self.region_ct,
        )
        project.clean()
        self.assertEqual(project.country, self.country_us)

    def test_project_clean_mismatched_country_and_region(self):
        project = Project(
            name="mismatch-proj",
            pi=self.pi,
            region=self.region_ct,
            country=self.country_ca,
        )
        with self.assertRaises(ValidationError):
            project.clean()

    def test_form_validation_rejects_cross_country_region(self):
        form_data = {
            'name': 'mismatch-form-proj',
            'kind': self.project_type.pk,
            'pi': self.pi.pk,
            'country': self.country_ca.pk,
            'region': self.region_ct.pk,
        }
        form = NewProjectForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('region', form.errors)

    def test_region_lookup_ajax_endpoint(self):
        self.client.force_login(self.admin)
        url = reverse('region-list-ajax')
        response = self.client.get(url, {'country': self.country_us.pk})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(any(r['id'] == self.region_ct.pk for r in data))

    def test_migration_matching_logic(self):
        import importlib
        from unittest.mock import MagicMock
        mig = importlib.import_module('basiclive.core.lims.migrations.0119_project_country_region_fk')

        mock_project = MagicMock()
        mock_project.legacy_country = "US"
        mock_project.legacy_province = "CT"
        mock_project.country = None
        mock_project.region = None

        mock_apps = MagicMock()
        mock_project_model = MagicMock()
        mock_project_model.objects.all.return_value = [mock_project]

        mock_apps.get_model.side_effect = lambda app, model: {
            'Project': mock_project_model,
            'Country': Country,
            'Region': Region,
        }[model]

        mig.migrate_country_region_data(mock_apps, None)
        self.assertEqual(mock_project.country, self.country_us)
        self.assertEqual(mock_project.region, self.region_ct)
