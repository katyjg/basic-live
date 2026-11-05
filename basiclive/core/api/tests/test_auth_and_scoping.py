from unittest.mock import patch, MagicMock

import msgpack
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.views.generic import View
from rest_framework_simplejwt.tokens import RefreshToken

from basiclive.core.api.middleware import APIAuthenticationMiddleware, get_v2_user, get_v3_user
from basiclive.core.api.views import (
    VerificationMixin, LaunchSession, CloseSession, ProjectSamples,
    AddData, AddReport
)
from basiclive.core.lims.middleware import ProjectContextMiddleware
from basiclive.core.lims.models import (
    Project, ProjectMembership, Beamline, DataType, Session,
    Sample, Container, ContainerType, Automounter, ContainerLocation,
    Data, AnalysisReport, SSHKey
)
from basiclive.utils.signing import Signer

User = get_user_model()


def generate_test_keys():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_der = priv.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    pub_ssh = priv.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH
    ).decode('utf-8')
    return priv_der, pub_ssh


class APIAuthenticationMiddlewareTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.middleware = APIAuthenticationMiddleware(lambda req: None)
        self.user = User.objects.create(username='api_alice', email='alice@example.com')
        self.project = Project.objects.create(name='proj_api_1', pi=self.user)
        self.priv_der, self.pub_ssh = generate_test_keys()
        SSHKey.objects.create(name='default', key=self.pub_ssh, user=self.user, project=self.project)

    def test_jwt_authentication_valid_token(self):
        token = str(RefreshToken.for_user(self.user).access_token)
        req = self.rf.get('/api/v3/data/08B1-1/', HTTP_X_ACCESS_TOKEN=f'Bearer {token}')
        user = get_v3_user(req)
        self.assertEqual(user, self.user)

        # Through middleware
        self.middleware.process_request(req)
        self.assertEqual(req.user, self.user)

    def test_jwt_authentication_invalid_token(self):
        req = self.rf.get('/api/v3/data/08B1-1/', HTTP_X_ACCESS_TOKEN='Bearer invalid-token')
        user = get_v3_user(req)
        self.assertIsNone(user)

    def test_v2_signature_authentication_success(self):
        signer = Signer(private=self.priv_der)
        signature = signer.sign('proj_api_1')

        # V2 route with signature kwargs
        url = f'/api/v2/{signature}:proj_api_1/data/08B1-1/'
        req = self.rf.get(url)
        # Mock URL resolution kwargs
        with patch('basiclive.core.api.middleware.resolve') as mock_resolve:
            mock_url_data = MagicMock()
            mock_url_data.kwargs = {'username': 'proj_api_1', 'signature': signature}
            mock_resolve.return_value = mock_url_data

            user = get_v2_user(req)
            self.assertEqual(user, self.user)
            self.assertEqual(req.project, self.project)

            # Test middleware
            self.middleware.process_request(req)
            self.assertEqual(req.user, self.user)

    def test_v2_signature_authentication_invalid_signature(self):
        url = '/api/v2/fake_sig:proj_api_1/data/08B1-1/'
        req = self.rf.get(url)
        with patch('basiclive.core.api.middleware.resolve') as mock_resolve:
            mock_url_data = MagicMock()
            mock_url_data.kwargs = {'username': 'proj_api_1', 'signature': 'fake_sig'}
            mock_resolve.return_value = mock_url_data

            user = get_v2_user(req)
            self.assertIsNone(user)


class VerificationMixinTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.user = User.objects.create(username='verif_alice')
        self.project = Project.objects.create(name='verif_proj', pi=self.user)
        self.priv_der, self.pub_ssh = generate_test_keys()
        SSHKey.objects.create(name='default', key=self.pub_ssh, project=self.project)

    def test_authenticated_user_passes_verification(self):
        class DummyView(VerificationMixin, View):
            def get(self, request, *args, **kwargs):
                from django.http import HttpResponse
                return HttpResponse("OK")

        req = self.rf.get('/test/')
        req.user = self.user
        resp = DummyView.as_view()(req)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"OK")

    def test_unauthenticated_without_signature_forbidden(self):
        class DummyView(VerificationMixin, View):
            def get(self, request, *args, **kwargs):
                from django.http import HttpResponse
                return HttpResponse("OK")

        req = self.rf.get('/test/')
        from django.contrib.auth.models import AnonymousUser
        req.user = AnonymousUser()
        resp = DummyView.as_view()(req)
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_with_valid_v2_signature_passes(self):
        signer = Signer(private=self.priv_der)
        signature = signer.sign('verif_proj')

        class DummyView(VerificationMixin, View):
            def get(self, request, *args, **kwargs):
                from django.http import HttpResponse
                return HttpResponse("OK")

        req = self.rf.get('/test/')
        from django.contrib.auth.models import AnonymousUser
        req.user = AnonymousUser()
        resp = DummyView.as_view()(req, username='verif_proj', signature=signature)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(req.user, self.user)
        self.assertEqual(req.project, self.project)

    def test_unauthenticated_nonexistent_user_or_project_404(self):
        class DummyView(VerificationMixin, View):
            def get(self, request, *args, **kwargs):
                from django.http import HttpResponse
                return HttpResponse("OK")

        req = self.rf.get('/test/')
        from django.contrib.auth.models import AnonymousUser
        req.user = AnonymousUser()
        resp = DummyView.as_view()(req, username='nonexistent_slug', signature='some_sig')
        self.assertEqual(resp.status_code, 404)

    def test_unauthenticated_missing_public_key_400(self):
        other_user = User.objects.create(username='no_key_user')
        no_key_proj = Project.objects.create(name='no_key_proj', pi=other_user)
        class DummyView(VerificationMixin, View):
            def get(self, request, *args, **kwargs):
                from django.http import HttpResponse
                return HttpResponse("OK")

        req = self.rf.get('/test/')
        from django.contrib.auth.models import AnonymousUser
        req.user = AnonymousUser()
        resp = DummyView.as_view()(req, username='no_key_proj', signature='some_sig')
        self.assertEqual(resp.status_code, 400)

    def test_unauthenticated_invalid_signature_403(self):
        class DummyView(VerificationMixin, View):
            def get(self, request, *args, **kwargs):
                from django.http import HttpResponse
                return HttpResponse("OK")

        req = self.rf.get('/test/')
        from django.contrib.auth.models import AnonymousUser
        req.user = AnonymousUser()
        resp = DummyView.as_view()(req, username='verif_proj', signature='bad_sig:verif_proj:123')
        self.assertEqual(resp.status_code, 403)


class ProjectContextMiddlewareAPITests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.user = User.objects.create(username='multi_alice')
        self.proj_a = Project.objects.create(name='proj_alpha', pi=self.user)
        self.proj_b = Project.objects.create(name='proj_beta', pi=self.user)
        self.other_user = User.objects.create(username='other_bob')
        self.proj_c = Project.objects.create(name='proj_gamma', pi=self.other_user)
        self.middleware = ProjectContextMiddleware(lambda req: None)

    def test_x_project_header_selects_accessible_project(self):
        req = self.rf.get('/api/data/08B1-1/', HTTP_X_PROJECT='proj_beta')
        req.user = self.user
        req.session = {}
        self.middleware.process_request(req)
        self.assertEqual(req.project, self.proj_b)

    def test_x_project_header_unauthorized_project_ignored(self):
        req = self.rf.get('/api/data/08B1-1/', HTTP_X_PROJECT='proj_gamma')
        req.user = self.user
        req.session = {}
        self.middleware.process_request(req)
        self.assertNotEqual(req.project, self.proj_c)

    def test_query_param_selects_accessible_project(self):
        req = self.rf.get('/api/data/08B1-1/?project=proj_beta')
        req.user = self.user
        req.session = {}
        self.middleware.process_request(req)
        self.assertEqual(req.project, self.proj_b)

    def test_pre_set_request_project_preserved(self):
        req = self.rf.get('/api/data/08B1-1/')
        req.user = self.user
        req.project = self.proj_b
        req.session = {}
        self.middleware.process_request(req)
        self.assertEqual(req.project, self.proj_b)


class APIEndpointsScopingTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.alice = User.objects.create(username='endpoint_alice')
        self.bob = User.objects.create(username='endpoint_bob')
        self.charlie = User.objects.create(username='endpoint_charlie')

        self.project_a = Project.objects.create(name='project_a', pi=self.alice)
        ProjectMembership.objects.create(
            user=self.bob,
            project=self.project_a,
            role=ProjectMembership.Role.MEMBER
        )

        self.project_b = Project.objects.create(name='project_b', pi=self.charlie)

        self.beamline = Beamline.objects.create(name='Test Beamline', acronym='08B1-1')
        self.datatype = DataType.objects.create(name='MX Diffraction', acronym='MX')

        self.location = ContainerLocation.objects.create(name='Automounter Dewar')
        self.ctype = ContainerType.objects.create(name='Unipuck')
        self.dewar = Container.objects.create(
            name='Dewar1', project=self.project_a, kind=self.ctype, location=self.location, status=Container.STATES.ON_SITE
        )
        self.automounter = Automounter.objects.create(
            beamline=self.beamline, container=self.dewar, active=True
        )

    @patch('basiclive.core.api.views.make_secure_path', return_value='fake_token_key')
    def test_launch_session_authorized_and_unauthorized(self, mock_secure_path):
        # Alice (PI of project_a) launches session
        req = self.rf.post(
            '/api/session/08B1-1/test-sess-1/start/',
            data={'project': 'project_a'}
        )
        req.user = self.alice
        req.project = self.project_a
        view = LaunchSession.as_view()
        resp = view(req, beamline='08B1-1', session='test-sess-1')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Session.objects.filter(project=self.project_a, name='test-sess-1').exists())

        # Charlie (not member of project_a) tries to launch session on project_a -> 403
        req2 = self.rf.post(
            '/api/session/08B1-1/test-sess-2/start/',
            data={'project': 'project_a'}
        )
        req2.user = self.charlie
        resp2 = view(req2, beamline='08B1-1', session='test-sess-2')
        self.assertEqual(resp2.status_code, 403)

    def test_close_session_authorized_and_unauthorized(self):
        sess = Session.objects.create(project=self.project_a, beamline=self.beamline, name='close-sess-1')
        sess.launch()

        # Bob (member of project_a) closes session
        req = self.rf.post('/api/session/08B1-1/close-sess-1/close/')
        req.user = self.bob
        req.project = self.project_a
        view = CloseSession.as_view()
        resp = view(req, beamline='08B1-1', session='close-sess-1')
        self.assertEqual(resp.status_code, 200)

        # Charlie tries to close project_a's session -> 403
        req2 = self.rf.post('/api/session/08B1-1/close-sess-1/close/', data={'project': 'project_a'})
        req2.user = self.charlie
        resp2 = view(req2, beamline='08B1-1', session='close-sess-1')
        self.assertEqual(resp2.status_code, 403)

    def test_project_samples_scoping(self):
        sample_a = Sample.objects.create(
            name='SampleA', project=self.project_a, container=self.dewar, barcode='SMP-001'
        )
        sample_b = Sample.objects.create(
            name='SampleB', project=self.project_b, container=self.dewar, barcode='SMP-002'
        )

        # Alice gets samples for project_a
        req = self.rf.get('/api/samples/08B1-1/', HTTP_X_PROJECT='project_a')
        req.user = self.alice
        req.project = self.project_a
        view = ProjectSamples.as_view()
        resp = view(req, beamline='08B1-1')
        self.assertEqual(resp.status_code, 200)
        import json
        data = json.loads(resp.content)
        sample_names = [s['name'] for s in data]
        self.assertIn('SampleA', sample_names)
        self.assertNotIn('SampleB', sample_names)

        # Charlie accessing project_a -> 403
        req2 = self.rf.get('/api/samples/08B1-1/', HTTP_X_PROJECT='project_a')
        req2.user = self.charlie
        resp2 = view(req2, beamline='08B1-1')
        self.assertEqual(resp2.status_code, 403)

    @patch('basiclive.core.api.views.make_secure_path', return_value='fake_token_key')
    def test_add_data_authorized_and_unauthorized(self, mock_secure_path):
        payload = {
            'project': 'project_a',
            'type': 'MX',
            'directory': '/data/project_a/run1',
            'energy': 12.658,
            'file_name': 'data_0001.cbf',
            'exposure_time': 0.1,
            'attenuation': 0.0,
            'beam_size': 50.0,
            'name': 'Test Dataset'
        }
        body = msgpack.dumps(payload)

        # Bob (member of project_a) adds data
        req = self.rf.post(
            '/api/data/08B1-1/',
            data=body,
            content_type='application/msgpack'
        )
        req.user = self.bob
        view = AddData.as_view()
        resp = view(req, beamline='08B1-1')
        self.assertEqual(resp.status_code, 200)
        import json
        res_data = json.loads(resp.content)
        d_id = res_data['id']
        data_obj = Data.objects.get(pk=d_id)
        self.assertEqual(data_obj.project, self.project_a)

        # Charlie tries adding data to project_a -> 403
        req2 = self.rf.post(
            '/api/data/08B1-1/',
            data=body,
            content_type='application/msgpack'
        )
        req2.user = self.charlie
        resp2 = view(req2, beamline='08B1-1')
        self.assertEqual(resp2.status_code, 403)

    @patch('basiclive.core.api.views.make_secure_path', return_value='fake_token_key')
    def test_add_report_authorized_and_unauthorized(self, mock_secure_path):
        payload = {
            'project': 'project_a',
            'directory': '/reports/project_a/rep1',
            'title': 'Auto-Proc Summary',
            'score': 95.5,
            'kind': 'Data Analysis',
            'details': {'spots': 500}
        }
        body = msgpack.dumps(payload)

        # Alice adds report
        req = self.rf.post('/api/report/08B1-1/', data=body, content_type='application/msgpack')
        req.user = self.alice
        view = AddReport.as_view()
        resp = view(req, beamline='08B1-1')
        self.assertEqual(resp.status_code, 200)
        import json
        rep_id = json.loads(resp.content)['id']
        rep = AnalysisReport.objects.get(pk=rep_id)
        self.assertEqual(rep.project, self.project_a)

        # Charlie tries adding report to project_a -> 403
        req2 = self.rf.post('/api/report/08B1-1/', data=body, content_type='application/msgpack')
        req2.user = self.charlie
        resp2 = view(req2, beamline='08B1-1')
        self.assertEqual(resp2.status_code, 403)

    @patch('basiclive.core.api.views.make_secure_path', return_value='fake_token_key')
    def test_legacy_v2_launch_session(self, mock_secure_path):
        priv_der, pub_ssh = generate_test_keys()
        SSHKey.objects.create(name='default', key=pub_ssh, user=self.alice, project=self.project_a)

        signer = Signer(private=priv_der)
        signature = signer.sign('project_a')

        req = self.rf.post(f'/api/v2/{signature}:project_a/launch/08B1-1/v2-sess/start/')
        from django.contrib.auth.models import AnonymousUser
        req.user = AnonymousUser()

        view = LaunchSession.as_view()
        resp = view(req, username='project_a', signature=signature, beamline='08B1-1', session='v2-sess')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Session.objects.filter(project=self.project_a, name='v2-sess').exists())

