import importlib
import json
import unittest
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from unittest.mock import patch


from basiclive.utils.testing import (
    create_user,
    create_project,
    create_project_membership,
    create_project_with_team,
    generate_jwt_token,
)
from basiclive.core.lims.models import (
    User,
    Project,
    ProjectMembership,
    Shipment,
    Container,
    ContainerType,
    ContainerLocation,
    Automounter,
    Group,
    Sample,
    Session,
    Stretch,
    Beamline,
    DataType,
    Data,
    AnalysisReport,
    SSHKey,
)
from basiclive.core.lims.middleware import ProjectContextMiddleware
from basiclive.core.lims.views import (
    SwitchProjectView,
    ShipmentList,
    ShipmentDetail,
    ShipmentEdit,
    ProjectProfile,
    ProjectEdit,
)
from basiclive.core.api.middleware import APIAuthenticationMiddleware
from basiclive.core.api.views import (
    ProjectSamples,
    LaunchSession,
    CloseSession,
    AddData,
    AddReport,
)
from basiclive.core.acl.models import AccessList
from basiclive.core.schedule.models import Beamtime, AccessType


class MultiUserRolesAndBoundariesTestCase(TestCase):
    """
    Validates role-based access permissions, team hierarchies (PI, Co-Investigator, Member),
    and project boundaries.
    """

    def setUp(self):
        # Create Project Alpha with full team hierarchy
        self.pi_alpha = create_user(username="pi_alpha", name="Alpha PI")
        self.proj_alpha, self.team_alpha = create_project_with_team(
            name="proj-alpha",
            pi=self.pi_alpha,
            co_invs=[create_user(username="coinv_alpha", name="Alpha CoInv")],
            members=[create_user(username="member_alpha", name="Alpha Member")],
        )
        self.coinv_alpha = self.team_alpha["co_invs"][0]
        self.member_alpha = self.team_alpha["members"][0]

        # Create Project Beta
        self.pi_beta = create_user(username="pi_beta", name="Beta PI")
        self.proj_beta, self.team_beta = create_project_with_team(
            name="proj-beta",
            pi=self.pi_beta,
            members=[create_user(username="member_beta", name="Beta Member")],
        )
        self.member_beta = self.team_beta["members"][0]

        # User belonging to both Project Alpha and Project Beta
        self.dual_user = create_user(username="dual_user", name="Dual User")
        create_project_membership(self.dual_user, self.proj_alpha, role=ProjectMembership.Role.MEMBER)
        create_project_membership(self.dual_user, self.proj_beta, role=ProjectMembership.Role.CO_INVESTIGATOR)

        # Unaffiliated outsider
        self.outsider = create_user(username="outsider", name="Outsider")

        # Superuser
        self.admin = create_user(username="admin", is_superuser=True, name="Admin")

    def test_pi_has_full_access_to_owned_project(self):
        self.assertTrue(self.pi_alpha.can_access_project(self.proj_alpha))
        self.assertFalse(self.pi_alpha.can_access_project(self.proj_beta))

    def test_co_investigator_and_member_access(self):
        self.assertTrue(self.coinv_alpha.can_access_project(self.proj_alpha))
        self.assertFalse(self.coinv_alpha.can_access_project(self.proj_beta))

        self.assertTrue(self.member_alpha.can_access_project(self.proj_alpha))
        self.assertFalse(self.member_alpha.can_access_project(self.proj_beta))

    def test_dual_project_user_access(self):
        self.assertTrue(self.dual_user.can_access_project(self.proj_alpha))
        self.assertTrue(self.dual_user.can_access_project(self.proj_beta))

    def test_unaffiliated_user_cannot_access_any_project(self):
        self.assertFalse(self.outsider.can_access_project(self.proj_alpha))
        self.assertFalse(self.outsider.can_access_project(self.proj_beta))

    def test_superuser_can_access_all_projects(self):
        self.assertTrue(self.admin.can_access_project(self.proj_alpha))
        self.assertTrue(self.admin.can_access_project(self.proj_beta))

    def test_anonymous_user_cannot_access_project(self):
        anon = AnonymousUser()
        can_access = getattr(anon, "can_access_project", lambda p: False)(self.proj_alpha)
        self.assertFalse(can_access)

    def test_user_get_projects_filtering(self):
        alpha_projects = list(self.pi_alpha.get_projects())
        self.assertEqual(alpha_projects, [self.proj_alpha])

        dual_projects = list(self.dual_user.get_projects())
        self.assertEqual(set(dual_projects), {self.proj_alpha, self.proj_beta})

        outsider_projects = list(self.outsider.get_projects())
        self.assertEqual(outsider_projects, [])


class ProjectSwitchingAndPersistenceTestCase(TestCase):
    """
    Validates project switching via SwitchProjectView, session tracking,
    open-redirect protection, and default_project persistence across logins.
    """

    def setUp(self):
        self.rf = RequestFactory()
        SessionStore = importlib.import_module(settings.SESSION_ENGINE).SessionStore
        self.SessionStore = SessionStore

        self.user = create_user(username="switcher_user")
        self.proj_1 = create_project(name="proj-1", pi=self.user)
        self.proj_2 = create_project(name="proj-2")
        create_project_membership(self.user, self.proj_2, role=ProjectMembership.Role.MEMBER)

        self.proj_forbidden = create_project(name="proj-forbidden")

    def _make_request(self, path="/", user=None, session_data=None):
        request = self.rf.get(path)
        session = self.SessionStore()
        if session_data:
            session.update(session_data)
        request.session = session
        request.user = user or self.user
        return request

    def test_switch_project_view_updates_session_and_redirects(self):
        url = reverse('switch-project-form')
        request = self._make_request(path=url, user=self.user)
        view = SwitchProjectView.as_view()
        response = view(request, pk=self.proj_2.pk)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(request.session.get("active_project_id"), self.proj_2.pk)

    def test_switch_to_unauthorized_project_forbidden(self):
        url = reverse('switch-project', kwargs={'pk': self.proj_2.pk})
        request = self._make_request(path=url, user=self.user)
        view = SwitchProjectView.as_view()

        with self.assertRaises(PermissionDenied):
            view(request, pk=self.proj_forbidden.pk)

    def test_switch_to_nonexistent_project_returns_404(self):
        url = reverse('switch-project', kwargs={'pk': 99999})
        request = self._make_request(path=url, user=self.user)
        view = SwitchProjectView.as_view()

        with self.assertRaises(Http404):
            view(request, pk=99999)

    def test_cross_login_default_project_persistence(self):
        # Set default_project to proj_2
        self.user.default_project = self.proj_2
        self.user.save()

        # Simulate fresh login on a new device (session has no active_project_id)
        middleware = ProjectContextMiddleware(get_response=lambda req: HttpResponse("OK"))
        request = self._make_request(path="/", user=self.user, session_data={})

        middleware(request)

        # request.project should resolve to default_project (proj_2)
        self.assertEqual(request.project, self.proj_2)
        self.assertEqual(request.session.get("active_project_id"), self.proj_2.pk)

    def test_default_project_fallback_when_removed_from_project(self):
        # User had default_project = proj_forbidden, but lost access
        self.user.default_project = self.proj_forbidden
        self.user.save()

        middleware = ProjectContextMiddleware(get_response=lambda req: HttpResponse("OK"))
        request = self._make_request(path="/", user=self.user, session_data={})

        middleware(request)

        # Middleware must NOT give access to proj_forbidden; clears invalid default_project
        self.assertNotEqual(request.project, self.proj_forbidden)
        self.assertEqual(request.project, None)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.default_project)


class CrossProjectDataIsolationTestCase(TestCase):
    """
    Validates complete data isolation between projects:
    - ListViewMixin strictly filters objects by request.project.
    - OwnerRequiredMixin rejects viewing/editing objects belonging to other projects.
    - Switching projects dynamically updates visibility.
    """

    def setUp(self):
        self.rf = RequestFactory()
        SessionStore = importlib.import_module(settings.SESSION_ENGINE).SessionStore
        self.SessionStore = SessionStore

        # Project A
        self.user_a = create_user(username="user_a")
        self.proj_a = create_project(name="proj-a", pi=self.user_a)
        self.shipment_a = Shipment.objects.create(name="Shipment Alpha", project=self.proj_a)
        self.container_type = ContainerType.objects.create(name="Puck")
        self.container_a = Container.objects.create(
            name="Puck-A", project=self.proj_a, kind=self.container_type, shipment=self.shipment_a
        )
        self.sample_a = Sample.objects.create(name="Sample-A", project=self.proj_a, container=self.container_a)

        # Project B
        self.user_b = create_user(username="user_b")
        self.proj_b = create_project(name="proj-b", pi=self.user_b)
        self.shipment_b = Shipment.objects.create(name="Shipment Beta", project=self.proj_b)
        self.container_b = Container.objects.create(
            name="Puck-B", project=self.proj_b, kind=self.container_type, shipment=self.shipment_b
        )
        self.sample_b = Sample.objects.create(name="Sample-B", project=self.proj_b, container=self.container_b)

        # Dual Member
        self.dual_user = create_user(username="dual_member")
        create_project_membership(self.dual_user, self.proj_a, role=ProjectMembership.Role.MEMBER)
        create_project_membership(self.dual_user, self.proj_b, role=ProjectMembership.Role.MEMBER)

    def _setup_view_request(self, view_instance, user, active_project):
        request = self.rf.get("/")
        session = self.SessionStore()
        session["active_project_id"] = active_project.pk
        request.session = session
        request.user = user
        request.project = active_project
        view_instance.request = request
        return request

    def test_shipment_list_scoped_to_active_project(self):
        view = ShipmentList()
        self._setup_view_request(view, self.user_a, self.proj_a)
        qs = view.get_queryset()

        self.assertIn(self.shipment_a, qs)
        self.assertNotIn(self.shipment_b, qs)

    def test_shipment_detail_blocks_unauthorized_project_member(self):
        view = ShipmentDetail()
        # user_a attempts to view shipment_b
        request = self._setup_view_request(view, self.user_a, self.proj_a)
        view.kwargs = {"pk": self.shipment_b.pk}

        self.assertFalse(view.test_func())

    def test_shipment_edit_blocks_unauthorized_user(self):
        view = ShipmentEdit()
        # user_a attempts to edit shipment_b
        request = self._setup_view_request(view, self.user_a, self.proj_a)
        view.kwargs = {"pk": self.shipment_b.pk}

        self.assertFalse(view.test_func())

    def test_dual_project_user_sees_scoped_data_per_active_project(self):
        view = ShipmentList()

        # First, active project is proj_a
        self._setup_view_request(view, self.dual_user, self.proj_a)
        qs_a = view.get_queryset()
        self.assertIn(self.shipment_a, qs_a)
        self.assertNotIn(self.shipment_b, qs_a)

        # Switch active project to proj_b
        self._setup_view_request(view, self.dual_user, self.proj_b)
        qs_b = view.get_queryset()
        self.assertNotIn(self.shipment_a, qs_b)
        self.assertIn(self.shipment_b, qs_b)


class MachineAPIScopingWorkflowTestCase(TestCase):
    """
    Validates machine API endpoints (ProjectSamples, LaunchSession, CloseSession)
    with JWT Bearer authentication and X-Project header resolution.
    """

    def setUp(self):
        self.rf = RequestFactory()
        SessionStore = importlib.import_module(settings.SESSION_ENGINE).SessionStore
        self.SessionStore = SessionStore

        self.user_a = create_user(username="api_user_a")
        self.proj_a = create_project(name="api-proj-a", pi=self.user_a)

        self.user_b = create_user(username="api_user_b")
        self.proj_b = create_project(name="api-proj-b", pi=self.user_b)

        self.beamline = Beamline.objects.create(name="BioXAS", acronym="06B1-1")
        self.location = ContainerLocation.objects.create(name="Dewar Location")
        self.container_type = ContainerType.objects.create(name="Puck")
        self.dewar = Container.objects.create(
            name="Dewar1", project=self.proj_a, kind=self.container_type, location=self.location, status=Container.STATES.ON_SITE
        )
        self.automounter = Automounter.objects.create(
            beamline=self.beamline, container=self.dewar, active=True
        )

        self.sample_a = Sample.objects.create(name="Sample-A", project=self.proj_a, container=self.dewar)
        self.sample_b = Sample.objects.create(name="Sample-B", project=self.proj_b, container=self.dewar)

        # JWT tokens
        self.token_a = generate_jwt_token(self.user_a)
        self.token_b = generate_jwt_token(self.user_b)

    def test_api_project_samples_authorized_via_jwt_and_header(self):
        request = self.rf.get(
            f"/api/v3/samples/{self.beamline.acronym}/",
            HTTP_X_ACCESS_TOKEN=f"Bearer {self.token_a}",
            HTTP_X_PROJECT=self.proj_a.name,
        )
        request.session = self.SessionStore()

        # Run through APIAuthenticationMiddleware
        api_auth = APIAuthenticationMiddleware(get_response=lambda req: HttpResponse("OK"))
        api_auth(request)

        self.assertEqual(request.user, self.user_a)

        view = ProjectSamples.as_view()
        response = view(request, beamline=self.beamline.acronym)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        sample_names = [s["name"] for s in data]
        self.assertIn("Sample-A", sample_names)
        self.assertNotIn("Sample-B", sample_names)

    def test_api_project_samples_rejected_when_accessing_other_project(self):
        # user_a attempts to query samples for proj_b
        request = self.rf.get(
            f"/api/v3/samples/{self.beamline.acronym}/",
            HTTP_X_ACCESS_TOKEN=f"Bearer {self.token_a}",
            HTTP_X_PROJECT=self.proj_b.name,
        )
        request.session = self.SessionStore()

        api_auth = APIAuthenticationMiddleware(get_response=lambda req: HttpResponse("OK"))
        api_auth(request)

        view = ProjectSamples.as_view()
        response = view(request, beamline=self.beamline.acronym)

        self.assertEqual(response.status_code, 403)

    @patch('basiclive.core.api.views.make_secure_path', return_value='fake_token_key')
    def test_launch_session_scoped_to_authorized_project(self, mock_make_secure_path):
        # user_a launches session for proj_a
        request = self.rf.post(
            f"/api/v3/session/{self.beamline.acronym}/session-1/start/",
            HTTP_X_ACCESS_TOKEN=f"Bearer {self.token_a}",
            HTTP_X_PROJECT=self.proj_a.name,
        )
        request.session = self.SessionStore()

        api_auth = APIAuthenticationMiddleware(get_response=lambda req: HttpResponse("OK"))
        api_auth(request)

        view = LaunchSession.as_view()
        response = view(request, beamline=self.beamline.acronym, session="session-1")

        self.assertEqual(response.status_code, 200)

        # user_a attempts to launch session for proj_b -> 403 Forbidden
        request_bad = self.rf.post(
            f"/api/v3/session/{self.beamline.acronym}/session-2/start/",
            HTTP_X_ACCESS_TOKEN=f"Bearer {self.token_a}",
            HTTP_X_PROJECT=self.proj_b.name,
        )
        request_bad.session = self.SessionStore()
        api_auth(request_bad)

        response_bad = view(request_bad, beamline=self.beamline.acronym, session="session-2")
        self.assertEqual(response_bad.status_code, 403)


class AccessControlMultiUserWorkflowTestCase(TestCase):
    """
    Validates ACL team resolution:
    - AccessList.users retains ManyToMany to Project.
    - manual_users() and scheduled() resolve personal User accounts of all team members.
    - Dynamic updates when users join/leave project teams.
    - Personal SSHKey retrieval per User.
    """

    def setUp(self):
        self.pi = create_user(username="acl_pi", name="ACL PI")
        self.member = create_user(username="acl_member", name="ACL Member")
        self.proj = create_project(name="acl-proj", pi=self.pi)
        create_project_membership(self.member, self.proj, role=ProjectMembership.Role.MEMBER)

        self.beamline = Beamline.objects.create(name="CMCF-BM", acronym="08B1-1")
        self.remote_access = AccessType.objects.create(name="Remote", remote=True)
        self.acl = AccessList.objects.create(name="Station Console", address="192.168.1.0/24", active=True)
        self.acl.beamline.add(self.beamline)
        self.acl.users.add(self.proj)

    def test_access_list_resolves_all_project_team_members(self):
        users = self.acl.manual_users()
        self.assertIn("acl_pi", users)
        self.assertIn("acl_member", users)

    def test_dynamic_roster_updates_on_membership_change(self):
        new_scientist = create_user(username="acl_guest", name="ACL Guest")
        membership = create_project_membership(new_scientist, self.proj, role=ProjectMembership.Role.MEMBER)

        # Immediately reflected in manual_users()
        users = self.acl.manual_users()
        self.assertIn("acl_guest", users)

        # Remove member
        membership.delete()
        users_after = self.acl.manual_users()
        self.assertNotIn("acl_guest", users_after)

    def test_scheduled_beamtime_resolves_team_members(self):
        now = timezone.now()
        beamtime = Beamtime.objects.create(
            beamline=self.beamline,
            project=self.proj,
            access=self.remote_access,
            start=now - timedelta(hours=1),
            end=now + timedelta(hours=7),
        )

        scheduled_users = self.acl.scheduled()
        self.assertIn("acl_pi", scheduled_users)
        self.assertIn("acl_member", scheduled_users)

    def test_personal_ssh_keys_belong_to_users(self):
        key_pi = SSHKey.objects.create(
            user=self.pi,
            name="pi-laptop",
            key="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIG... pi@lab",
        )
        key_member = SSHKey.objects.create(
            user=self.member,
            name="member-workstation",
            key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC... member@lab",
        )

        self.assertEqual(key_pi.user, self.pi)
        self.assertEqual(key_member.user, self.member)
        self.assertNotEqual(key_pi.user, key_member.user)
