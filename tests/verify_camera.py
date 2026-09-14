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
os.environ.update(HYDRO_DATA_DIR=scratch.name, HYDRO_REAL_ONLY='1', HYDRO_DEMO='1', YOLO_MODEL_PATH='')
from fastapi.testclient import TestClient
from PIL import Image
from backend import main, sessions, remote_camera

buf = io.BytesIO()
Image.new('RGB', (160, 120), '#718478').save(buf, format='JPEG')
jpeg = buf.getvalue()


class CameraHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.last_headers = dict(self.headers)
        if self.path == '/missing':
            self.send_error(404)
            return
        if self.path == '/redirect':
            self.send_response(302)
            self.send_header('Location', 'http://127.0.0.1/private')
            self.end_headers()
            return
        body = b'<html>configuration page</html>' if self.path == '/html' else jpeg
        self.send_response(200)
        self.send_header('Content-Type', 'image/jpeg')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class CameraChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('0.0.0.0', 0), CameraHandler)
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

    def setUp(self):
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
        self.assertEqual(frame['source_url'], self.url + '/image')
        self.assertEqual(frame['refresh_seconds'], 20)
        self.assertIsNone(frame['captured_at'])
        self.assertEqual(response.headers['cache-control'], 'no-store')
        Image.open(io.BytesIO(base64.b64decode(frame['image'].split(',')[1]))).verify()
        self.assertNotIn('Cookie', self.server.last_headers)
        self.assertEqual(len(main.s.allof('photos')), before)

    def test_offline_empty_invalid_and_oversized_images_fail_explicitly(self):
        for path in ['/missing', '/html', '/redirect']:
            self.assertEqual(self.client.post('/api/camera/frame', json={'url': self.url + path}).status_code, 503)
        with patch.object(remote_camera, 'MAX_BYTES', 100):
            self.assertEqual(self.client.post('/api/camera/frame', json={'url': self.url}).status_code, 413)
        with socket.socket() as sock:
            sock.bind(('0.0.0.0', 0))
            closed_url = f'http://{socket.gethostbyname(socket.gethostname())}:{sock.getsockname()[1]}/image'
        self.assertEqual(self.client.post('/api/camera/frame', json={'url': closed_url}).status_code, 503)

    def test_invalid_addresses_and_roles_cannot_fetch(self):
        for address in ['file:///etc/passwd', 'rtsp://192.168.4.1/live', 'http://127.0.0.1', 'http://169.254.169.254', 'http://user:password@192.168.4.1/image', 'http://192.168.4.1:99999/image']:
            self.assertEqual(self.client.post('/api/camera/frame', json={'url': address}).status_code, 422)
        self.client.post('/api/session', json={'role': 'parent'})
        self.assertEqual(self.client.post('/api/camera/frame', json={'url': self.url}).status_code, 403)
        self.client.delete('/api/session')
        self.assertEqual(self.client.post('/api/camera/frame', json={'url': self.url}).status_code, 401)

    def test_camera_photo_can_be_uploaded_with_authenticated_session(self):
        response = self.client.post('/api/photos', data={'device': 'CAMERA-TEST', 'batch': 'TEST', 'capture_source': 'local_camera'}, files={'file': ('camera.jpg', jpeg, 'image/jpeg')})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['capture_source'], 'local_camera')
        self.assertEqual(self.client.get(response.json()['url']).status_code, 200)


if __name__ == '__main__':
    unittest.main(verbosity=2)
