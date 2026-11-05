import importlib
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.http import HttpResponse, Http404
from django.template import Context, Template
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils.functional import SimpleLazyObject


from basiclive.core.lims.models import User, Project, ProjectMembership
from basiclive.core.lims.middleware import ProjectContextMiddleware
from basiclive.core.lims.views import SwitchProjectView


class ProjectContextMiddlewareTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        call_command('migrate', verbosity=0)
        super().setUpClass()

    def setUp(self):
        self.rf = RequestFactory()
        SessionStore = importlib.import_module(settings.SESSION_ENGINE).SessionStore
        self.SessionStore = SessionStore

        # Create test users
        self.user_single = User.objects.create_user(username="single_user", email="single@example.org")
        self.user_multi = User.objects.create_user(username="multi_user", email="multi@example.org")
        self.user_none = User.objects.create_user(username="none_user", email="none@example.org")
        self.superuser = User.objects.create_superuser(username="admin_user", email="admin@example.org", password="adminpassword")

        # Create test projects
        self.proj_alpha = Project.objects.create(name="alpha", pi=self.user_single)
        self.proj_beta = Project.objects.create(name="beta", pi=self.user_multi)
        self.proj_gamma = Project.objects.create(name="gamma")
        ProjectMembership.objects.create(user=self.user_multi, project=self.proj_gamma, role=ProjectMembership.Role.MEMBER)

    def _get_request(self, user=None, session_data=None):
        request = self.rf.get('/')
        session = self.SessionStore()
        if session_data:
            session.update(session_data)
        request.session = session
        request.user = user if user is not None else AnonymousUser()
        return request

    def test_anonymous_user_project_is_none(self):
        middleware = ProjectContextMiddleware(get_response=lambda req: HttpResponse("OK"))
        request = self._get_request(user=AnonymousUser())
        middleware(request)
        self.assertIsNone(request.project)

    def test_user_with_no_projects(self):
        middleware = ProjectContextMiddleware(get_response=lambda req: HttpResponse("OK"))
        request = self._get_request(user=self.user_none)
        middleware(request)
        self.assertEqual(request.project, None)
        self.assertFalse(bool(request.project))

    def test_single_project_auto_selection_and_persisted(self):
        middleware = ProjectContextMiddleware(get_response=lambda req: HttpResponse("OK"))
        request = self._get_request(user=self.user_single)
        middleware(request)

        # request.project should resolve to proj_alpha
        self.assertEqual(request.project, self.proj_alpha)
        # Should be stored in session
        self.assertEqual(request.session.get('active_project_id'), self.proj_alpha.id)
        # Should be persisted in user.default_project in database
        self.user_single.refresh_from_db()
        self.assertEqual(self.user_single.default_project, self.proj_alpha)

    def test_multi_project_initial_state_none(self):
        middleware = ProjectContextMiddleware(get_response=lambda req: HttpResponse("OK"))
        request = self._get_request(user=self.user_multi)
        middleware(request)

        # With 2 projects and no prior choice, project should be None
        self.assertEqual(request.project, None)
        self.assertFalse(bool(request.project))
        self.assertNotIn('active_project_id', request.session)

    def test_multi_project_restores_from_default_project(self):
        # Set user's default_project in database
        self.user_multi.default_project = self.proj_gamma
        self.user_multi.save(update_fields=['default_project'])

        middleware = ProjectContextMiddleware(get_response=lambda req: HttpResponse("OK"))
        request = self._get_request(user=self.user_multi)
        middleware(request)

        # Should restore from default_project
        self.assertEqual(request.project, self.proj_gamma)
        self.assertEqual(request.session.get('active_project_id'), self.proj_gamma.id)

    def test_session_precedence_over_default_project(self):
        self.user_multi.default_project = self.proj_gamma
        self.user_multi.save(update_fields=['default_project'])

        middleware = ProjectContextMiddleware(get_response=lambda req: HttpResponse("OK"))
        # Session has proj_beta active
        request = self._get_request(user=self.user_multi, session_data={'active_project_id': self.proj_beta.id})
        middleware(request)

        # Session takes precedence
        self.assertEqual(request.project, self.proj_beta)

    def test_unauthorized_project_in_session_purged(self):
        middleware = ProjectContextMiddleware(get_response=lambda req: HttpResponse("OK"))
        # user_single only has access to alpha, but session has beta
        request = self._get_request(user=self.user_single, session_data={'active_project_id': self.proj_beta.id})
        middleware(request)

        # Invalid session project should be purged and fallback to auto-selection of alpha
        self.assertEqual(request.project, self.proj_alpha)
        self.assertEqual(request.session.get('active_project_id'), self.proj_alpha.id)

    def test_superuser_can_access_any_project(self):
        middleware = ProjectContextMiddleware(get_response=lambda req: HttpResponse("OK"))
        # superuser selects alpha without explicit membership
        request = self._get_request(user=self.superuser, session_data={'active_project_id': self.proj_alpha.id})
        middleware(request)

        self.assertEqual(request.project, self.proj_alpha)

    def test_lazy_evaluation(self):
        middleware = ProjectContextMiddleware(get_response=lambda req: HttpResponse("OK"))
        request = self._get_request(user=self.user_single)
        middleware(request)

        # request.project should be a SimpleLazyObject
        self.assertIsInstance(request.project, SimpleLazyObject)


class SwitchProjectViewTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        call_command('migrate', verbosity=0)
        super().setUpClass()

    def setUp(self):
        self.rf = RequestFactory()
        SessionStore = importlib.import_module(settings.SESSION_ENGINE).SessionStore
        self.SessionStore = SessionStore

        self.user = User.objects.create_user(username="researcher", email="r@example.org")
        self.other_user = User.objects.create_user(username="other", email="o@example.org")
        self.superuser = User.objects.create_superuser(username="admin", email="a@example.org", password="pw")

        self.proj_1 = Project.objects.create(name="proj1", pi=self.user)
        self.proj_2 = Project.objects.create(name="proj2")
        ProjectMembership.objects.create(user=self.user, project=self.proj_2, role=ProjectMembership.Role.MEMBER)
        self.proj_other = Project.objects.create(name="proj_other", pi=self.other_user)

    def _get_request(self, path, user, data=None, method='GET'):
        if method == 'POST':
            request = self.rf.post(path, data=data or {})
        else:
            request = self.rf.get(path, data=data or {})
        session = self.SessionStore()
        request.session = session
        request.user = user
        return request

    def test_switch_project_get_success(self):
        view = SwitchProjectView.as_view()
        request = self._get_request(reverse('switch-project', kwargs={'pk': 1}), user=self.user)
        response = view(request, pk=self.proj_2.pk)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')
        self.assertEqual(request.session['active_project_id'], self.proj_2.pk)

        self.user.refresh_from_db()
        self.assertEqual(self.user.default_project, self.proj_2)

    def test_switch_project_post_success(self):
        view = SwitchProjectView.as_view()
        request = self._get_request(
            reverse('switch-project-form'), user=self.user, data={'project_id': self.proj_1.pk}, method='POST'
        )
        response = view(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')
        self.assertEqual(request.session['active_project_id'], self.proj_1.pk)

        self.user.refresh_from_db()
        self.assertEqual(self.user.default_project, self.proj_1)

    def test_switch_project_unauthorized_forbidden(self):
        view = SwitchProjectView.as_view()
        request = self._get_request(reverse('switch-project', kwargs={'pk': self.proj_other.pk}), user=self.user)
        with self.assertRaises(PermissionDenied):
            view(request, pk=self.proj_other.pk)

    def test_superuser_can_switch_to_any_project(self):
        view = SwitchProjectView.as_view()
        request = self._get_request(f'/projects/switch/{self.proj_other.pk}/', user=self.superuser)
        response = view(request, pk=self.proj_other.pk)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(request.session['active_project_id'], self.proj_other.pk)

    def test_switch_project_nonexistent_404(self):
        view = SwitchProjectView.as_view()
        request = self._get_request('/projects/switch/99999/', user=self.user)
        with self.assertRaises(Http404):
            view(request, pk=99999)

    def test_open_redirect_protection(self):
        view = SwitchProjectView.as_view()
        request = self._get_request(f'/projects/switch/{self.proj_1.pk}/?next=https://malicious.evil.com/steal', user=self.user)
        response = view(request, pk=self.proj_1.pk)

        self.assertEqual(response.status_code, 302)
        # Should reject external url and fall back to '/'
        self.assertEqual(response.url, '/')


class NavbarProjectSwitcherTemplateTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        call_command('migrate', verbosity=0)
        super().setUpClass()

    def setUp(self):
        self.rf = RequestFactory()
        SessionStore = importlib.import_module(settings.SESSION_ENGINE).SessionStore
        self.SessionStore = SessionStore

        self.user_single = User.objects.create_user(username="single_user", email="single@example.org")
        self.user_multi = User.objects.create_user(username="multi_user", email="multi@example.org")

        self.proj_alpha = Project.objects.create(name="alpha", pi=self.user_single)
        self.proj_beta = Project.objects.create(name="beta", pi=self.user_multi)
        self.proj_gamma = Project.objects.create(name="gamma")
        ProjectMembership.objects.create(user=self.user_multi, project=self.proj_gamma, role=ProjectMembership.Role.MEMBER)

    def _get_request(self, user=None, session_data=None):
        request = self.rf.get('/')
        session = self.SessionStore()
        if session_data:
            session.update(session_data)
        request.session = session
        request.user = user if user is not None else AnonymousUser()
        middleware = ProjectContextMiddleware(get_response=lambda req: HttpResponse("OK"))
        middleware(request)
        return request

    def test_navbar_multi_project_shows_dropdown(self):
        from django.template.loader import render_to_string
        request = self._get_request(user=self.user_multi, session_data={'active_project_id': self.proj_beta.id})
        rendered = render_to_string('lims/navs.html', {'request': request, 'user': self.user_multi}, request=request)

        self.assertIn('id="project-switcher"', rendered)
        self.assertIn('BETA', rendered)
        self.assertIn('GAMMA', rendered)
        self.assertIn(f'/projects/switch/{self.proj_gamma.pk}/', rendered)

    def test_navbar_single_project_shows_display_only(self):
        from django.template.loader import render_to_string
        request = self._get_request(user=self.user_single)
        rendered = render_to_string('lims/navs.html', {'request': request, 'user': self.user_single}, request=request)

        self.assertNotIn('id="project-switcher"', rendered)
        self.assertIn('id="project-display"', rendered)
        self.assertIn('ALPHA', rendered)

    def test_navbar_anonymous_shows_neither(self):
        from django.template.loader import render_to_string
        request = self._get_request(user=AnonymousUser())
        rendered = render_to_string('lims/navs.html', {'request': request, 'user': AnonymousUser()}, request=request)

        self.assertNotIn('id="project-switcher"', rendered)
        self.assertNotIn('id="project-display"', rendered)

