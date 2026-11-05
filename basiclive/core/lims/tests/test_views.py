import json
import unittest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.http import Http404
from django.test import RequestFactory, TestCase


from basiclive.core.lims.models import (
    User,
    Project,
    ProjectMembership,
    Shipment,
    Container,
    ContainerType,
    Group,
    Sample,
    Request,
    RequestType,
    AnalysisReport,
)
from basiclive.core.lims.views import (
    OwnerRequiredMixin,
    ListViewMixin,
    ShipmentList,
    ShipmentDetail,
    ProjectProfile,
    ProjectEdit,
    RequestWizardEdit,
)
from basiclive.core.lims import ajax_views


class UserCanAccessProjectTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        call_command('migrate', verbosity=0)
        super().setUpClass()

    def setUp(self):
        self.pi = User.objects.create_user(username="pi_user", email="pi@example.org")
        self.member = User.objects.create_user(username="member_user", email="member@example.org")
        self.other = User.objects.create_user(username="other_user", email="other@example.org")
        self.superuser = User.objects.create_superuser(username="admin_user", email="admin@example.org", password="pw")

        self.project = Project.objects.create(name="proj-101", pi=self.pi)
        ProjectMembership.objects.create(user=self.member, project=self.project, role=ProjectMembership.Role.MEMBER)

    def test_unauthenticated_cannot_access_project(self):
        anon = AnonymousUser()
        # AnonymousUser won't have the method or should return False
        can_access = getattr(anon, 'can_access_project', lambda p: False)(self.project)
        self.assertFalse(can_access)

    def test_superuser_can_access_any_project(self):
        self.assertTrue(self.superuser.can_access_project(self.project))

    def test_pi_can_access_project(self):
        self.assertTrue(self.pi.can_access_project(self.project))

    def test_member_can_access_project(self):
        self.assertTrue(self.member.can_access_project(self.project))

    def test_non_member_cannot_access_project(self):
        self.assertFalse(self.other.can_access_project(self.project))


class ListViewMixinScopingTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        call_command('migrate', verbosity=0)
        super().setUpClass()

    def setUp(self):
        self.rf = RequestFactory()
        self.user_a = User.objects.create_user(username="usera", email="a@example.org")
        self.user_b = User.objects.create_user(username="userb", email="b@example.org")
        self.superuser = User.objects.create_superuser(username="admin", email="admin@example.org", password="pw")

        self.proj_a = Project.objects.create(name="proj-a", pi=self.user_a)
        self.proj_b = Project.objects.create(name="proj-b", pi=self.user_b)

        self.shipment_a = Shipment.objects.create(name="shipment-a", project=self.proj_a, status=Shipment.STATES.SENT)
        self.shipment_b = Shipment.objects.create(name="shipment-b", project=self.proj_b, status=Shipment.STATES.SENT)

    def test_list_view_filters_by_active_project(self):
        view = ShipmentList()
        request = self.rf.get('/shipments/')
        request.user = self.user_a
        request.project = self.proj_a
        view.request = request

        qs = view.get_queryset()
        self.assertIn(self.shipment_a, qs)
        self.assertNotIn(self.shipment_b, qs)

    def test_list_view_empty_when_no_active_project(self):
        view = ShipmentList()
        request = self.rf.get('/shipments/')
        request.user = self.user_a
        request.project = None
        view.request = request

        qs = view.get_queryset()
        self.assertEqual(qs.count(), 0)

    def test_list_view_superuser_sees_all(self):
        view = ShipmentList()
        request = self.rf.get('/shipments/')
        request.user = self.superuser
        request.project = None
        view.request = request

        qs = view.get_queryset()
        self.assertIn(self.shipment_a, qs)
        self.assertIn(self.shipment_b, qs)


class OwnerRequiredMixinTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        call_command('migrate', verbosity=0)
        super().setUpClass()

    def setUp(self):
        self.rf = RequestFactory()
        self.pi = User.objects.create_user(username="owner_pi", email="pi@example.org")
        self.member = User.objects.create_user(username="owner_member", email="m@example.org")
        self.other = User.objects.create_user(username="stranger", email="s@example.org")
        self.superuser = User.objects.create_superuser(username="admin_owner", email="ao@example.org", password="pw")

        self.project = Project.objects.create(name="owner-proj", pi=self.pi)
        ProjectMembership.objects.create(user=self.member, project=self.project, role=ProjectMembership.Role.MEMBER)
        self.shipment = Shipment.objects.create(name="test-shipment", project=self.project)

    def _test_view(self, user):
        view = ShipmentDetail()
        request = self.rf.get(f'/shipments/{self.shipment.pk}/')
        request.user = user
        view.request = request
        view.kwargs = {'pk': self.shipment.pk}
        return view.test_func()

    def test_allows_pi(self):
        self.assertTrue(self._test_view(self.pi))

    def test_allows_member(self):
        self.assertTrue(self._test_view(self.member))

    def test_denies_non_member(self):
        self.assertFalse(self._test_view(self.other))

    def test_allows_superuser(self):
        self.assertTrue(self._test_view(self.superuser))


class ProjectProfileAndEditViewsTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        call_command('migrate', verbosity=0)
        super().setUpClass()

    def setUp(self):
        self.rf = RequestFactory()
        self.pi = User.objects.create_user(username="lead_pi", email="pi@example.org")
        self.member = User.objects.create_user(username="team_member", email="m@example.org")
        self.outsider = User.objects.create_user(username="outsider", email="out@example.org")
        self.superuser = User.objects.create_superuser(username="super", email="sup@example.org", password="pw")

        self.project = Project.objects.create(name="lab-project", pi=self.pi)
        ProjectMembership.objects.create(user=self.member, project=self.project, role=ProjectMembership.Role.MEMBER)

    def test_project_profile_permissions(self):
        view = ProjectProfile()
        request = self.rf.get(f'/projects/{self.project.name}/')
        view.kwargs = {'name': self.project.name}

        request.user = self.pi
        view.request = request
        self.assertTrue(view.test_func())

        request.user = self.member
        view.request = request
        self.assertTrue(view.test_func())

        request.user = self.outsider
        view.request = request
        self.assertFalse(view.test_func())

        request.user = self.superuser
        view.request = request
        self.assertTrue(view.test_func())

        # Also support backward compatible 'username' kwarg
        view.kwargs = {'username': self.project.name}
        request.user = self.pi
        self.assertTrue(view.test_func())

    def test_project_edit_permissions(self):
        view = ProjectEdit()
        request = self.rf.get(f'/projects/{self.project.name}/edit')
        view.kwargs = {'name': self.project.name}

        request.user = self.pi
        view.request = request
        self.assertTrue(view.test_func())

        request.user = self.member
        view.request = request
        self.assertTrue(view.test_func())

        request.user = self.outsider
        view.request = request
        self.assertFalse(view.test_func())

        # Also support backward compatible 'username' kwarg
        view.kwargs = {'username': self.project.name}
        request.user = self.pi
        self.assertTrue(view.test_func())


class AjaxViewsScopingAndSecurityTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        call_command('migrate', verbosity=0)
        super().setUpClass()

    def setUp(self):
        self.rf = RequestFactory()
        self.pi = User.objects.create_user(username="ajax_pi", email="pi@example.org")
        self.member = User.objects.create_user(username="ajax_member", email="m@example.org")
        self.outsider = User.objects.create_user(username="ajax_outsider", email="out@example.org")

        self.project = Project.objects.create(name="ajax-proj", pi=self.pi)
        ProjectMembership.objects.create(user=self.member, project=self.project, role=ProjectMembership.Role.MEMBER)

        self.shipment = Shipment.objects.create(name="ajax-shipment", project=self.project)
        self.group = Group.objects.create(name="ajax-group", project=self.project, shipment=self.shipment)
        self.report = AnalysisReport.objects.create(name="ajax-report", project=self.project, details="{}")

        self.rtype = RequestType.objects.create(name="Standard MX", spec={})
        self.req = Request.objects.create(name="ajax-req", project=self.project, kind=self.rtype)

    def test_fetch_report_member_vs_outsider(self):
        view = ajax_views.FetchReport.as_view()

        # Member allowed
        req_member = self.rf.get(f'/ajax/report/{self.report.pk}/')
        req_member.user = self.member
        resp = view(req_member, pk=self.report.pk)
        self.assertEqual(resp.status_code, 200)

        # Outsider denied 404
        req_outsider = self.rf.get(f'/ajax/report/{self.report.pk}/')
        req_outsider.user = self.outsider
        with self.assertRaises(Http404):
            view(req_outsider, pk=self.report.pk)

    def test_fetch_request_member_vs_outsider(self):
        view = ajax_views.FetchRequest.as_view()

        req_member = self.rf.get(f'/ajax/request/?pk={self.req.pk}')
        req_member.user = self.member
        resp = view(req_member)
        self.assertEqual(resp.status_code, 200)

        req_outsider = self.rf.get(f'/ajax/request/?pk={self.req.pk}')
        req_outsider.user = self.outsider
        with self.assertRaises(Http404):
            view(req_outsider)

    def test_update_priority_member_vs_outsider(self):
        view = ajax_views.UpdatePriority.as_view()

        req_member = self.rf.post('/ajax/update_priority/', data={'group': self.group.pk, 'samples[]': []})
        req_member.user = self.member
        resp = view(req_member)
        self.assertEqual(resp.status_code, 200)

        req_outsider = self.rf.post('/ajax/update_priority/', data={'group': self.group.pk, 'samples[]': []})
        req_outsider.user = self.outsider
        with self.assertRaises(Http404):
            view(req_outsider)

    def test_bulk_sample_edit_permission_denied_for_outsider(self):
        view = ajax_views.BulkSampleEdit.as_view()
        req_outsider = self.rf.post('/ajax/bulk_edit/', data={'group': self.group.pk})
        req_outsider.user = self.outsider
        resp = view(req_outsider)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(any('permission' in str(err).lower() for err in data))
