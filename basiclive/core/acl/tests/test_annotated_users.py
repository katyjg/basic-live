import unittest
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone


from basiclive.core.acl.models import AccessList, AnnotatedUser
from basiclive.core.lims.models import Beamline, Project
from basiclive.core.schedule.models import Beamtime, AccessType


class AnnotatedUsersTests(TestCase):
    @classmethod
    def setUpClass(cls):
        call_command('migrate', verbosity=0)
        super().setUpClass()

    def setUp(self):
        self.beamline = Beamline.objects.create(name="BioXAS", acronym="08B1-1")
        self.remote_access_type = AccessType.objects.create(name="Remote", remote=True)
        self.local_access_type = AccessType.objects.create(name="On-site", remote=False)

        self.user_alice = Project.objects.create(name="alice")
        self.user_bob = Project.objects.create(name="bob")
        self.user_charlie = Project.objects.create(name="charlie")
        self.user_david = Project.objects.create(name="david")

        self.access_list = AccessList.objects.create(
            name="Endstation-A",
            address="192.168.1.100",
            active=True
        )
        self.access_list.beamline.add(self.beamline)

    def test_manual_only(self):
        self.access_list.users.add(self.user_bob, self.user_alice)
        annotated = self.access_list.annotated_projects()

        self.assertEqual(len(annotated), 2)
        self.assertEqual(annotated[0].name, "alice")
        self.assertEqual(annotated[0].source, "manual")
        self.assertEqual(annotated[1].name, "bob")
        self.assertEqual(annotated[1].source, "manual")

    def test_scheduled_only(self):
        now = timezone.localtime()
        Beamtime.objects.create(
            project=self.user_charlie,
            beamline=self.beamline,
            access=self.remote_access_type,
            start=now - timedelta(hours=1),
            end=now + timedelta(hours=7),
            cancelled=False,
        )

        annotated = self.access_list.annotated_projects()
        self.assertEqual(len(annotated), 1)
        self.assertEqual(annotated[0].name, "charlie")
        self.assertEqual(annotated[0].source, "schedule")

    def test_overlap_prioritizes_schedule_and_orders_groups(self):
        # Alice is both manual and scheduled
        self.access_list.users.add(self.user_alice, self.user_bob)

        now = timezone.localtime()
        # Alice has active scheduled remote beamtime
        Beamtime.objects.create(
            project=self.user_alice,
            beamline=self.beamline,
            access=self.remote_access_type,
            start=now - timedelta(hours=1),
            end=now + timedelta(hours=7),
            cancelled=False,
        )
        # Charlie has active scheduled remote beamtime
        Beamtime.objects.create(
            project=self.user_charlie,
            beamline=self.beamline,
            access=self.remote_access_type,
            start=now - timedelta(hours=2),
            end=now + timedelta(hours=6),
            cancelled=False,
        )

        annotated = self.access_list.annotated_projects()

        # Scheduled group comes first (sorted alphabetically: alice, charlie)
        # Manual group comes second (bob; alice is excluded from manual because scheduled takes precedence)
        expected = [
            ("alice", "schedule"),
            ("charlie", "schedule"),
            ("bob", "manual"),
        ]
        self.assertEqual([(u.name, u.source) for u in annotated], expected)

    def test_schedule_disabled(self):
        self.access_list.users.add(self.user_alice)
        now = timezone.localtime()
        Beamtime.objects.create(
            project=self.user_charlie,
            beamline=self.beamline,
            access=self.remote_access_type,
            start=now - timedelta(hours=1),
            end=now + timedelta(hours=7),
            cancelled=False,
        )

        with override_settings(BASICLIVE_LIMS={"USE_SCHEDULE": False}):
            annotated = self.access_list.annotated_projects()
            self.assertEqual([(u.name, u.source) for u in annotated], [("alice", "manual")])

    def test_namedtuple_unpacking(self):
        user = AnnotatedUser(username="testuser", source="schedule")
        u, s = user
        self.assertEqual(u, "testuser")
        self.assertEqual(s, "schedule")

    def test_format_allowed_users_empty(self):
        from basiclive.core.acl.views import format_authorized
        html = format_authorized([], self.access_list)
        self.assertEqual(html, "")

    def test_format_allowed_users_badges(self):
        from basiclive.core.acl.views import format_authorized

        self.access_list.users.add(self.user_bob)
        now = timezone.localtime()
        Beamtime.objects.create(
            project=self.user_alice,
            beamline=self.beamline,
            access=self.remote_access_type,
            start=now - timedelta(hours=1),
            end=now + timedelta(hours=7),
            cancelled=False,
        )

        html = format_authorized(self.access_list.annotated_projects(), self.access_list)
        expected_alice = '<span class="badge text-bg-success badge-md" title="Scheduled Access">ALICE</span>'
        expected_bob = '<span class="badge text-bg-warning badge-md" title="Manual Access">BOB</span>'
        self.assertEqual(html, f"{expected_alice} {expected_bob}")

    def test_access_list_view_configuration(self):
        from basiclive.core.acl.views import AccessListView, format_authorized

        view = AccessListView()
        self.assertEqual(
            view.get_list_columns(),
            ['name', 'description', 'annotated_projects', 'address', 'beamlines']
        )
        self.assertNotIn('current_users', view.get_list_columns())
        self.assertNotIn('scheduled_users', view.get_list_columns())
        self.assertEqual(view.get_list_headers().get('annotated_projects'), 'Authorized Users')
        self.assertIs(view.get_list_transforms().get('annotated_projects'), format_authorized)

        with override_settings(BASICLIVE_LIMS={"USE_SCHEDULE": False}):
            self.assertEqual(
                view.get_list_columns(),
                ['name', 'description', 'annotated_projects', 'address', 'beamlines']
            )

    def test_project_members_authorization_scheduled_and_manual(self):
        from basiclive.core.lims.models import User as LimsUser
        pi_user = LimsUser.objects.create_user(username="pi_grant", email="pi@example.com")
        member_user = LimsUser.objects.create_user(username="student_lee", email="lee@example.com")
        proj_scheduled = Project.objects.create(name="scheduled-lab", pi=pi_user)
        proj_scheduled.members.add(member_user)

        now = timezone.localtime()
        Beamtime.objects.create(
            project=proj_scheduled,
            beamline=self.beamline,
            access=self.remote_access_type,
            start=now - timedelta(hours=1),
            end=now + timedelta(hours=7),
            cancelled=False,
        )

        manual_pi = LimsUser.objects.create_user(username="manual_prof", email="prof@example.com")
        manual_member = LimsUser.objects.create_user(username="manual_postdoc", email="postdoc@example.com")
        proj_manual = Project.objects.create(name="manual-lab", pi=manual_pi)
        proj_manual.members.add(manual_member)
        self.access_list.users.add(proj_manual)

        authorized = self.access_list.authorized_users()
        self.assertIn("pi_grant", authorized)
        self.assertIn("student_lee", authorized)
        self.assertIn("manual_prof", authorized)
        self.assertIn("manual_postdoc", authorized)

        annotated_dict = {u.username: u.source for u in self.access_list.annotated_users()}
        self.assertEqual(annotated_dict["pi_grant"], "schedule")
        self.assertEqual(annotated_dict["student_lee"], "schedule")
        self.assertEqual(annotated_dict["manual_prof"], "manual")
        self.assertEqual(annotated_dict["manual_postdoc"], "manual")


if __name__ == "__main__":
    unittest.main()

