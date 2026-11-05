import unittest
from django.core.management import call_command
from django.test import TestCase, Client
from django.urls import reverse

from basiclive.core.lims.models import (
    User,
    Project,
    ProjectType,
    SSHKey,
)


class UserViewsTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        call_command('migrate', verbosity=0)
        super().setUpClass()

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="alice",
            email="alice@example.org",
            password="alicepassword",
            first_name="Alice",
            last_name="Scientist",
            phone="123-456-7890"
        )
        self.other_user = User.objects.create_user(
            username="bob",
            email="bob@example.org",
            password="bobpassword",
            first_name="Bob",
            last_name="Researcher"
        )
        self.superuser = User.objects.create_superuser(
            username="admin",
            email="admin@example.org",
            password="adminpassword"
        )
        self.kind = ProjectType.objects.create(name="Standard MX")
        self.project = Project.objects.create(name="alice-lab", pi=self.user, kind=self.kind)

    def test_user_detail_view_permissions(self):
        url = reverse('user-detail', kwargs={'username': self.user.username})

        # Anonymous cannot access
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

        # Alice can access her own profile
        self.client.login(username="alice", password="alicepassword")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "alice@example.org")
        self.assertContains(resp, "ALICE-LAB")

        # Bob cannot access Alice's profile
        self.client.logout()
        self.client.login(username="bob", password="bobpassword")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403)

        # Superuser can access Alice's profile
        self.client.logout()
        self.client.login(username="admin", password="adminpassword")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_user_edit_view_updates_profile(self):
        url = reverse('user-edit', kwargs={'username': self.user.username})

        self.client.login(username="alice", password="alicepassword")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        # POST update (Modal forms return 200 with JSON redirect url)
        post_data = {
            'first_name': 'Alicia',
            'last_name': 'Scientist-Updated',
            'email': 'alicia@example.org',
            'phone': '555-987-6543',
            'default_project': self.project.pk,
        }
        resp = self.client.post(url, data=post_data)
        self.assertEqual(resp.status_code, 200)
        json_data = resp.json()
        self.assertEqual(json_data.get('url'), reverse('user-detail', kwargs={'username': 'alice'}))

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Alicia')
        self.assertEqual(self.user.last_name, 'Scientist-Updated')
        self.assertEqual(self.user.email, 'alicia@example.org')
        self.assertEqual(self.user.phone, '555-987-6543')
        self.assertEqual(self.user.default_project, self.project)

    def test_sshkey_create_and_delete_under_user(self):
        create_url = reverse('new-sshkey', kwargs={'username': self.user.username})
        self.client.login(username="alice", password="alicepassword")

        # GET modal
        resp = self.client.get(create_url)
        self.assertEqual(resp.status_code, 200)

        # Create key (Modal form returns 200 with JSON redirect url)
        valid_key = (
            "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIG1234567890abcdef1234567890abcdef12345678 "
            "alice@laptop"
        )
        post_data = {
            'name': 'My Laptop',
            'key': valid_key,
            'user': self.user.pk,
        }
        resp = self.client.post(create_url, data=post_data)
        self.assertEqual(resp.status_code, 200)
        json_data = resp.json()
        self.assertEqual(json_data.get('url'), reverse('user-detail', kwargs={'username': 'alice'}))

        key = SSHKey.objects.get(name='My Laptop')
        self.assertEqual(key.user, self.user)

        # Delete key (ModalDeleteView confirmed post returns 200 JSON or redirect)
        delete_url = reverse('sshkey-delete', kwargs={'pk': key.pk, 'username': 'alice'})
        resp = self.client.post(delete_url)
        self.assertIn(resp.status_code, [200, 302])
        self.assertFalse(SSHKey.objects.filter(name='My Laptop').exists())
