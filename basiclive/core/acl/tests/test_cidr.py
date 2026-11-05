import json
import unittest
from django.core.management import call_command
from django.test import RequestFactory, TestCase


from basiclive.core.acl.models import AccessList
from basiclive.core.acl.views import AccessKeys, EndpointList
from basiclive.core.lims.models import Project, User, SSHKey


class AccessListCIDRTests(TestCase):
    @classmethod
    def setUpClass(cls):
        call_command('migrate', verbosity=0)
        super().setUpClass()

    def setUp(self):
        self.rf = RequestFactory()
        self.user_alice = User.objects.create(username="alice", name="Alice Researcher")
        self.user_bob = User.objects.create(username="bob", name="Bob Scientist")
        self.user_charlie = User.objects.create(username="charlie", name="Charlie PI")

        self.project_alice = Project.objects.create(name="proj-alice", pi=self.user_alice)
        self.project_bob = Project.objects.create(name="proj-bob", pi=self.user_bob)
        self.project_charlie = Project.objects.create(name="proj-charlie", pi=self.user_charlie)

        self.key_alice = SSHKey.objects.create(
            name="alice-key",
            key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC0alice alice@lab",
            user=self.user_alice,
        )

        # Diverse AccessList networks
        self.al_single_ipv4 = AccessList.objects.create(
            name="Single-IPv4",
            address="192.168.1.10",
            active=True,
        )
        self.al_single_ipv4.users.add(self.project_alice)

        self.al_cidr_subnet = AccessList.objects.create(
            name="Subnet-IPv4",
            address="192.168.1.0/24",
            active=True,
        )
        self.al_cidr_subnet.users.add(self.project_bob)

        self.al_broad_subnet = AccessList.objects.create(
            name="Broad-IPv4",
            address="10.0.0.0/16",
            active=True,
        )
        self.al_broad_subnet.users.add(self.project_charlie)

        self.al_narrow_subnet = AccessList.objects.create(
            name="Narrow-IPv4",
            address="10.0.5.0/24",
            active=True,
        )
        self.al_narrow_subnet.users.add(self.project_alice)

        self.al_ipv6_cidr = AccessList.objects.create(
            name="IPv6-Subnet",
            address="2001:db8::/64",
            active=True,
        )
        self.al_ipv6_cidr.users.add(self.project_alice)

        self.al_inactive = AccessList.objects.create(
            name="Inactive-Subnet",
            address="172.16.0.0/16",
            active=False,
        )
        self.al_inactive.users.add(self.project_bob)

    def test_model_matches_method(self):
        # Single IPv4 host
        self.assertTrue(self.al_single_ipv4.matches("192.168.1.10"))
        self.assertFalse(self.al_single_ipv4.matches("192.168.1.11"))

        # IPv4 CIDR /24
        self.assertTrue(self.al_cidr_subnet.matches("192.168.1.1"))
        self.assertTrue(self.al_cidr_subnet.matches("192.168.1.254"))
        self.assertFalse(self.al_cidr_subnet.matches("192.168.2.1"))

        # IPv6 CIDR /64
        self.assertTrue(self.al_ipv6_cidr.matches("2001:db8::1"))
        self.assertTrue(self.al_ipv6_cidr.matches("2001:db8::ffff"))
        self.assertFalse(self.al_ipv6_cidr.matches("2001:db9::1"))

        # Invalid IP strings
        self.assertFalse(self.al_cidr_subnet.matches("not-an-ip"))
        self.assertFalse(self.al_cidr_subnet.matches(""))
        self.assertFalse(self.al_cidr_subnet.matches(None))

    def test_active_for_ip_specificity_precedence(self):
        # 192.168.1.10 matches both al_single_ipv4 (/32) and al_cidr_subnet (/24)
        # Most specific (/32) must take precedence
        matched = AccessList.objects.active_for_ip("192.168.1.10")
        self.assertEqual(matched, self.al_single_ipv4)

        # 192.168.1.50 matches only al_cidr_subnet (/24)
        matched = AccessList.objects.active_for_ip("192.168.1.50")
        self.assertEqual(matched, self.al_cidr_subnet)

        # 10.0.5.25 matches both al_narrow_subnet (/24) and al_broad_subnet (/16)
        # Narrower (/24) must take precedence
        matched = AccessList.objects.active_for_ip("10.0.5.25")
        self.assertEqual(matched, self.al_narrow_subnet)

        # 10.0.99.1 matches only al_broad_subnet (/16)
        matched = AccessList.objects.active_for_ip("10.0.99.1")
        self.assertEqual(matched, self.al_broad_subnet)

        # IPv6 CIDR matching
        matched = AccessList.objects.active_for_ip("2001:db8::cafe")
        self.assertEqual(matched, self.al_ipv6_cidr)

        # Inactive lists are ignored even if subnet matches
        matched = AccessList.objects.active_for_ip("172.16.1.1")
        self.assertIsNone(matched)

        # Unknown IP
        matched = AccessList.objects.active_for_ip("8.8.8.8")
        self.assertIsNone(matched)

    def test_endpoint_list_view_get(self):
        # Request from specific single IP -> alice
        request = self.rf.get("/accesslist/", REMOTE_ADDR="192.168.1.10")
        response = EndpointList.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), ["alice"])

        # Request from CIDR subnet (not .10) -> bob
        request = self.rf.get("/accesslist/", REMOTE_ADDR="192.168.1.200")
        response = EndpointList.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), ["bob"])

        # Request from IPv6 CIDR -> alice
        request = self.rf.get("/accesslist/", REMOTE_ADDR="2001:db8::1234")
        response = EndpointList.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), ["alice"])

        # Unmatched IP -> empty list
        request = self.rf.get("/accesslist/", REMOTE_ADDR="172.20.1.1")
        response = EndpointList.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), [])

    def test_access_keys_view_get(self):
        # Authenticated user alice accessing from allowed CIDR subnet (al_narrow_subnet)
        request = self.rf.get("/keys/alice/", REMOTE_ADDR="10.0.5.42")
        request.user = self.user_alice
        response = AccessKeys.as_view()(request, username="alice")
        self.assertEqual(response.status_code, 200)
        self.assertIn("ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC0alice", response.content.decode())

        # Authenticated user alice accessing from outside her allowed subnets (e.g. 192.168.1.200 has bob, not alice)
        request = self.rf.get("/keys/alice/", REMOTE_ADDR="192.168.1.200")
        request.user = self.user_alice
        response = AccessKeys.as_view()(request, username="alice")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")

        # Unauthenticated request -> 403 Forbidden
        request = self.rf.get("/keys/alice/", REMOTE_ADDR="10.0.5.42")
        request.user = type("AnonymousUser", (), {"is_authenticated": False})()
        response = AccessKeys.as_view()(request, username="alice")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
