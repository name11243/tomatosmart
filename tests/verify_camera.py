"""Camera and session checks with an isolated database and local HTTP fixture."""
import base64
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
scratch = tempfile.TemporaryDirectory(prefix='camera-check-')
os.environ.update(HYDRO_DATA_DIR=scratch.name, HYDRO_REAL_ONLY='1', HYDRO_DEMO='1', YOLO_MODEL_PATH='',
                  HYDRO_CAMERA_CONFIG=str(Path(scratch.name) / 'camera.yaml'))
from fastapi.testclient import TestClient
from PIL import Image
from backend import camera_config, main, sessions, remote_camera

DEFAULT_URL = 'http://192.168.1.50:500/snapshot'

buf = io.BytesIO()
Image.new('RGB', (160, 120), '#718478').save(buf, format='JPEG')
jpeg = buf.getvalue()
portal = b'<html>configuration page</html>'


class CameraHandler(BaseHTTPRequestHandler):
    """Fixture camera: a photo path plus a configuration page, like the ESP32-P4 firmware."""

    def do_GET(self):
        self.server.last_headers = dict(self.headers)
        self.server.last_path = self.path
        path = self.path.split('?')[0]
        if path == '/redirect':
            self.send_response(302)
            self.send_header('Location', 'http://127.0.0.1/private')
            self.end_headers()
            return
        if path in self.server.photos:
            body, content_type = self.server.photos[path], 'image/jpeg'
        elif path in ('/', '/html'):
            body, content_type = portal, 'text/html'
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class CameraChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('0.0.0.0', 0), CameraHandler)
        cls.server.photos = {'/snapshot': jpeg}
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://{socket.gethostbyname(socket.gethostname())}:{cls.server.server_port}'
        main.s.put('devices', {'id': 'CAMERA-TEST', 'batch': 'TEST', 'source': 'mqtt'})

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        scratch.cleanup()

    def camera(self, photos):
        """Publish the fixture's photo on another path, e.g. the firmware's /image."""
        self.server.photos = photos
        self.addCleanup(setattr, self.server, 'photos', {'/snapshot': jpeg})

    def setUp(self):
        camera_config.save(DEFAULT_URL)
        self.client = TestClient(main.app)
        self.client.post('/api/session', json={'role': 'teacher'}).raise_for_status()
        self.addCleanup(self.client.close)

    def test_session_survives_a_new_backend_process(self):
        token = self.client.cookies.get('hydro_session')
        code = "import sys,json; from backend import main; u=main.sessions.get(json.load(sys.stdin)['token'],True); print(json.dumps({'role':u['role']}))"
        result = subprocess.run([sys.executable, '-c', code], input=json.dumps({'token': token}), text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout), {'role': 'teacher'})
        with main.s.db() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM sessions WHERE token_hash=?', (token,)).fetchone())

    def test_expiry_logout_and_password_rotation_revoke_access(self):
        token = self.client.cookies.get('hydro_session')
        self.assertIsNotNone(sessions.get(token, True))
        self.client.delete('/api/session').raise_for_status()
        self.assertIsNone(sessions.get(token, True))
        token, _ = sessions.create('teacher', 'Teacher', True)
        with main.s.db() as db:
            db.execute('UPDATE sessions SET expires=0 WHERE token_hash=?', (sessions._key(token),))
        self.assertIsNone(sessions.get(token, True))
        with patch.dict(os.environ, {'HYDRO_TEACHER_PASSWORD': 'test-password-a'}):
            token, _ = sessions.create('teacher', 'Teacher', False)
            self.assertIsNotNone(sessions.get(token, False))
            self.assertIsNone(sessions.get(token, True))
        with patch.dict(os.environ, {'HYDRO_TEACHER_PASSWORD': 'test-password-b'}):
            self.assertIsNone(sessions.get(token, False))

    def test_password_login_still_requires_password(self):
        with patch.object(main, 'DEMO', False), patch.dict(os.environ, {'HYDRO_TEACHER_PASSWORD': 'test-password'}):
            self.assertEqual(self.client.post('/api/session', json={'role': 'teacher'}).status_code, 401)
            self.assertEqual(self.client.post('/api/session', json={'role': 'teacher', 'password': 'test-password'}).status_code, 200)

    def test_snapshot_is_decoded_without_business_writes_or_forwarded_cookies(self):
        before = len(main.s.allof('photos'))
        response = self.client.post('/api/camera/frame', json={'url': self.url})
        self.assertEqual(response.status_code, 200, response.text)
        frame = response.json()
        self.assertEqual(frame['source_url'], self.url + '/snapshot')
        self.assertFalse(frame['endpoint_detected'])
        self.assertEqual(frame['refresh_seconds'], 20)
        self.assertIsNone(frame['captured_at'])
        self.assertEqual(response.headers['cache-control'], 'no-store')
        Image.open(io.BytesIO(base64.b64decode(frame['image'].split(',')[1]))).verify()
        self.assertNotIn('Cookie', self.server.last_headers)
        self.assertEqual(len(main.s.allof('photos')), before)

    def test_only_explicit_diagnosis_probes_other_paths(self):
        # Normal connections must use the selected URL, even if another path has a photo.
        self.camera({'/image': jpeg})
        response = self.client.post('/api/camera/frame', json={'url': self.url + '/snapshot'})
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(self.server.last_path, '/snapshot')
        report = self.client.post('/api/camera/probe', json={'url': self.url + '/snapshot'}).json()
        self.assertTrue(report['ok'])
        self.assertTrue(report['endpoint_detected'])
        self.assertEqual(report['source_url'], self.url + '/image')
        self.assertEqual([item['failure'] for item in report['attempts']], ['empty', None])
        self.assertIsNone(report['captured_at'])
        self.assertIn('/image', report['message'])

    def test_defaults_and_changed_address_are_used_exactly(self):
        camera_config.save(self.url + '/snapshot')
        frame = self.client.post('/api/camera/frame', json={}).json()
        self.assertEqual(frame['source_url'], self.url + '/snapshot')
        self.camera({'/custom/photo': jpeg})
        selected = self.url + '/custom/photo?camera=2'
        frame = self.client.post('/api/camera/frame', json={'url': selected}).json()
        self.assertEqual(frame['source_url'], selected)
        self.assertEqual(self.server.last_path, '/custom/photo?camera=2')
        self.assertEqual(camera_config.read()['url'], self.url + '/snapshot')

    def test_probe_explains_every_failed_address(self):
        with socket.socket() as sock:
            sock.bind(('0.0.0.0', 0))
            closed_url = f'http://{socket.gethostbyname(socket.gethostname())}:{sock.getsockname()[1]}'
        report = self.client.post('/api/camera/probe', json={'url': closed_url + '/snapshot'}).json()
        self.assertFalse(report['ok'])
        self.assertEqual(len(report['attempts']), 1)
        self.assertEqual(report['attempts'][0]['failure'], 'refused')
        self.assertEqual(report['attempts'][0]['url'], closed_url + '/snapshot')
        self.assertTrue(any('端口' in line for line in report['advice']))
        self.assertIn(closed_url + '/snapshot', report['message'])
        self.client.post('/api/session', json={'role': 'parent'})
        self.assertEqual(self.client.post('/api/camera/probe', json={'url': closed_url}).status_code, 403)
        self.client.delete('/api/session')
        self.assertEqual(self.client.post('/api/camera/probe', json={'url': closed_url}).status_code, 401)

    def test_offline_empty_invalid_and_oversized_images_fail_explicitly(self):
        # A device that has not published a photo yet answers 404 on every known endpoint.
        self.camera({})
        empty = self.client.post('/api/camera/frame', json={'url': self.url + '/snapshot'})
        self.assertEqual(empty.status_code, 503)
        self.assertIn('404', empty.json()['detail'])
        self.assertEqual([item['failure'] for item in self.client.post('/api/camera/probe', json={'url': self.url + '/snapshot'}).json()['attempts']], ['empty', 'empty', 'empty'])
        # A configuration page is not a photo; redirects are reported instead of followed.
        self.assertEqual(self.client.post('/api/camera/frame', json={'url': self.url + '/html'}).status_code, 503)
        self.assertEqual(self.client.post('/api/camera/frame', json={'url': self.url + '/redirect'}).status_code, 503)
        redirects = self.client.post('/api/camera/probe', json={'url': self.url + '/redirect'}).json()['attempts']
        self.assertEqual(redirects[0]['failure'], 'redirect')
        self.assertEqual(redirects[0]['status'], 302)
        self.camera({'/snapshot': jpeg})
        with patch.object(remote_camera, 'MAX_BYTES', 100):
            self.assertEqual(self.client.post('/api/camera/frame', json={'url': self.url}).status_code, 413)
        with socket.socket() as sock:
            sock.bind(('0.0.0.0', 0))
            closed_url = f'http://{socket.gethostbyname(socket.gethostname())}:{sock.getsockname()[1]}/image'
        self.assertEqual(self.client.post('/api/camera/frame', json={'url': closed_url}).status_code, 503)

    def test_invalid_addresses_and_roles_cannot_fetch(self):
        for address in ['', 'file:///etc/passwd', 'rtsp://192.168.4.1/live', 'http://127.0.0.1', 'http://169.254.169.254', 'http://user:password@192.168.4.1/image', 'http://192.168.4.1:99999/image']:
            self.assertEqual(self.client.post('/api/camera/frame', json={'url': address}).status_code, 422)
        self.client.post('/api/session', json={'role': 'parent'})
        self.assertEqual(self.client.post('/api/camera/frame', json={'url': self.url}).status_code, 403)
        self.client.delete('/api/session')
        self.assertEqual(self.client.post('/api/camera/frame', json={'url': self.url}).status_code, 401)

    def test_no_stale_camera_address_is_baked_into_the_code(self):
        # backend/config/camera.yaml is the only authority; an empty YAML stays empty.
        self.assertEqual(camera_config.FALLBACK['url'], '')
        Path(os.environ['HYDRO_CAMERA_CONFIG']).unlink()
        self.assertEqual(camera_config.read()['url'], '')
        self.assertEqual(remote_camera.default_url(), '')
        self.assertEqual(remote_camera.camera_url('192.168.4.1'), 'http://192.168.4.1/snapshot')
        self.assertEqual(self.client.get('/api/camera/config').json()['url'], '')

    def test_camera_photo_can_be_uploaded_with_authenticated_session(self):
        response = self.client.post('/api/photos', data={'device': 'CAMERA-TEST', 'batch': 'TEST', 'capture_source': 'local_camera'}, files={'file': ('camera.jpg', jpeg, 'image/jpeg')})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['capture_source'], 'local_camera')
        self.assertEqual(self.client.get(response.json()['url']).status_code, 200)

    def test_default_address_comes_from_yaml_and_a_saved_ip_is_used(self):
        self.assertEqual(remote_camera.default_url(), DEFAULT_URL)
        # A bare IP keeps the configured endpoint path instead of a hard-coded /image.
        self.assertEqual(remote_camera.camera_url('192.168.1.50:500'), DEFAULT_URL)
        self.assertEqual(self.client.get('/api/camera/config').json()['url'], DEFAULT_URL)
        self.assertEqual(self.client.put('/api/camera/config', json={'url': DEFAULT_URL}).json()['url'], DEFAULT_URL)
        self.assertTrue(Path(os.environ['HYDRO_CAMERA_CONFIG']).exists())
        saved = self.client.put('/api/camera/config', json={'url': self.url})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()['url'], self.url + '/snapshot')
        self.assertEqual(self.client.get('/api/camera/config').json()['url'], self.url + '/snapshot')
        # Requests follow the saved address: the page only sends the address it shows.
        self.assertEqual(self.client.post('/api/camera/frame', json={'url': self.client.get('/api/camera/config').json()['url']}).json()['source_url'], self.url + '/snapshot')

    def test_address_changes_require_a_valid_url_and_an_editor_session(self):
        for address in ['file:///etc/passwd', 'rtsp://10.0.0.1/live', 'http://127.0.0.1', 'http://user:password@10.0.0.1/snapshot', 'http://10.0.0.1:99999/snapshot', '']:
            self.assertEqual(self.client.put('/api/camera/config', json={'url': address}).status_code, 422)
        self.assertEqual(self.client.get('/api/camera/config').json()['url'], DEFAULT_URL)
        self.client.post('/api/session', json={'role': 'parent'})
        self.assertEqual(self.client.put('/api/camera/config', json={'url': 'http://10.0.0.1/snapshot'}).status_code, 403)
        self.client.delete('/api/session')
        self.assertEqual(self.client.get('/api/camera/config').status_code, 401)
        self.assertEqual(self.client.put('/api/camera/config', json={'url': 'http://10.0.0.1/snapshot'}).status_code, 401)


if __name__ == '__main__':
    unittest.main(verbosity=2)
