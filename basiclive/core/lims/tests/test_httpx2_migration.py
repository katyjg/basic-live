from unittest.mock import patch, MagicMock
import httpx2
from django.test import TestCase, RequestFactory
from django.test.utils import override_settings

from basiclive.core.api.views import make_secure_path
from basiclive.core.lims.views import ProxyView, fetch_archive
from basiclive.core.schedule.templatetags.calendar import calendar_view
from basiclive.core.publications.utils import fetch_journal_metrics


class Httpx2MigrationTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_make_secure_path_success(self):
        with patch('httpx2.post') as mock_post:
            mock_resp = MagicMock(status_code=200)
            mock_resp.json.return_value = {'key': 'token123'}
            mock_post.return_value = mock_resp

            key = make_secure_path('project/session')
            self.assertEqual(key, 'token123')
            mock_post.assert_called_once()

    def test_make_secure_path_http_error(self):
        with patch('httpx2.post', side_effect=httpx2.ConnectError('connection failed')):
            with self.assertRaises(ValueError) as cm:
                make_secure_path('project/session')
            self.assertIn('Unable to create SecurePath', str(cm.exception))

    def test_make_secure_path_non_200(self):
        with patch('httpx2.post') as mock_post:
            mock_post.return_value = MagicMock(status_code=500)
            with self.assertRaises(ValueError) as cm:
                make_secure_path('project/session')
            self.assertIn('Unable to create SecurePath', str(cm.exception))

    def test_proxy_view_streaming(self):
        def handler(request):
            return httpx2.Response(
                200,
                content=b'streamed-data-chunks',
                headers={'Content-Type': 'application/octet-stream', 'Content-Disposition': 'inline'}
            )

        client = httpx2.Client(transport=httpx2.MockTransport(handler))
        with patch('httpx2.Client', return_value=client):
            request = self.factory.get('/raw/data/file.dat')
            view = ProxyView.as_view()
            response = view(request, section='raw', path='data/file.dat')
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.streaming)
            self.assertEqual(b''.join(response.streaming_content), b'streamed-data-chunks')
            self.assertEqual(response['Content-Type'], 'application/octet-stream')
            self.assertEqual(response['Content-Disposition'], 'inline')

    def test_proxy_view_non_200(self):
        def handler(request):
            return httpx2.Response(404, content=b'Not Found', headers={'Content-Type': 'text/plain'})

        client = httpx2.Client(transport=httpx2.MockTransport(handler))
        with patch('httpx2.Client', return_value=client):
            request = self.factory.get('/raw/data/missing.dat')
            view = ProxyView.as_view()
            response = view(request, section='raw', path='data/missing.dat')
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.content, b'Not Found')

    def test_fetch_archive_streaming(self):
        def handler(request):
            return httpx2.Response(200, content=b'fake-tar-gz-bytes')

        client = httpx2.Client(transport=httpx2.MockTransport(handler))
        with patch('httpx2.Client', return_value=client):
            request = self.factory.get('/archive/all')
            response = fetch_archive(request, 'http://proxy/archive/all')
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.streaming)
            self.assertEqual(b''.join(response.streaming_content), b'fake-tar-gz-bytes')
            self.assertEqual(response['Content-Type'], 'application/x-gzip')

    def test_fetch_archive_not_found(self):
        def handler(request):
            return httpx2.Response(404, content=b'Missing')

        client = httpx2.Client(transport=httpx2.MockTransport(handler))
        with patch('httpx2.Client', return_value=client):
            request = self.factory.get('/archive/missing')
            response = fetch_archive(request, 'http://proxy/archive/missing')
            self.assertEqual(response.status_code, 404)

    def test_calendar_view_connection_error_warning(self):
        with override_settings(
            BASICLIVE_SCHEDULE={
                'SCHEDULE_PROVIDER': {
                    'BACKEND': 'basiclive.core.schedule.providers.HttpScheduleProvider',
                    'OPTIONS': {
                        'base_url': 'http://facility.example',
                        'endpoints': {'modes': '/modes?start={start}&end={end}'},
                    },
                }
            }
        ):
            with patch('basiclive.core.schedule.providers.httpx2.get', side_effect=httpx2.ConnectError('offline')):
                with self.assertWarns(UserWarning) as cm:
                    calendar_view(2026, 1)
                self.assertIn("Couldn't fetch", str(cm.warning))

    def test_calendar_view_unsupported_protocol_warning(self):
        with override_settings(
            BASICLIVE_SCHEDULE={
                'SCHEDULE_PROVIDER': {
                    'BACKEND': 'basiclive.core.schedule.providers.HttpScheduleProvider',
                    'OPTIONS': {
                        'endpoints': {'modes': 'invalid-scheme://facility/modes?start={start}&end={end}'},
                    },
                }
            }
        ):
            with patch('basiclive.core.schedule.providers.httpx2.get', side_effect=httpx2.UnsupportedProtocol('unsupported')):
                with self.assertWarns(UserWarning) as cm:
                    calendar_view(2026, 1)
                self.assertIn("must start with", str(cm.warning))

    def test_httpx2_uses_truststore_ssl_context(self):
        import truststore
        client = httpx2.Client()
        self.assertIsInstance(client._transport._pool._ssl_context, truststore.SSLContext)
