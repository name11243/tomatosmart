"""Isolated ingress checks; synthetic fixtures never enter real camera or album data."""
import asyncio
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

scratch = tempfile.TemporaryDirectory(prefix='camera-receiver-test-')
os.environ.update(HYDRO_DATA_DIR=scratch.name, HYDRO_REAL_ONLY='1', HYDRO_DEMO='1', YOLO_MODEL_PATH='',
                  HYDRO_CAMERA_CONFIG=str(Path(scratch.name) / 'camera.yaml'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from fastapi.testclient import TestClient
from PIL import Image
from backend import main, camera_receiver as receiver, remote_camera, store


def fixture(color, kind='JPEG'):
    out = io.BytesIO()
    Image.new('RGB', (160, 120), color).save(out, format=kind)
    return out.getvalue()


JPEG, PNG = fixture('#238174'), fixture('#877451', 'PNG')


class ReceiverChecks(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)
        with store.db() as db:
            db.execute('DELETE FROM camera_snapshot')

    def post(self, content=JPEG, content_type='image/jpeg'):
        return self.client.post('/snapshot', content=content, headers={'Content-Type': content_type})

    def test_empty_service_has_no_placeholder_and_private_status_requires_login(self):
        response = self.client.get('/snapshot')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers['x-camera-receiver'], 'tomatosmart')
        self.assertIn('尚未收到', response.json()['detail'])
        self.assertEqual(self.client.get('/api/camera/receiver').status_code, 401)
        self.client.post('/api/session', json={'role': 'teacher'})
        self.assertFalse(self.client.get('/api/camera/receiver').json()['has_photo'])

    def test_raw_firmware_upload_uses_no_login_and_returns_original_bytes(self):
        for kind in ('photos', 'records', 'recognitions'):
            self.assertEqual(store.allof(kind), [])
        uploaded = self.post()
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        self.assertTrue(uploaded.json()['ok'])
        self.assertIsNone(uploaded.json()['captured_at'])
        self.assertEqual(uploaded.json()['bytes'], len(JPEG))
        response = self.client.get('/snapshot')
        self.assertEqual(response.content, JPEG)
        self.assertEqual(response.headers['content-type'], 'image/jpeg')
        self.assertEqual(response.headers['x-camera-sha256'], hashlib.sha256(JPEG).hexdigest())
        self.assertEqual(response.headers['x-camera-received-at'], uploaded.json()['received_at'])
        self.assertIn('no-store', response.headers['cache-control'])
        self.assertEqual(response.headers['x-camera-stale'], 'false')
        head = self.client.head('/snapshot')
        self.assertEqual(head.content, b'')
        self.assertEqual(int(head.headers['content-length']), len(JPEG))
        for kind in ('photos', 'records', 'recognitions'):
            self.assertEqual(store.allof(kind), [])

    def test_multipart_and_octet_stream_replace_the_latest_image(self):
        self.post()
        response = self.client.post('/snapshot', files={'image': ('camera.png', PNG, 'image/png')}, data={'camera': 'p4'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get('/snapshot').content, PNG)
        self.assertEqual(self.post(JPEG, 'application/octet-stream').status_code, 200)
        self.assertEqual(self.client.get('/snapshot').content, JPEG)
        with store.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM camera_snapshot').fetchone()[0], 1)

    def test_invalid_and_incomplete_uploads_do_not_destroy_last_photo(self):
        self.post()
        for body in (b'', b'not an image', JPEG[:100]):
            self.assertEqual(self.post(body).status_code, 422)
            self.assertEqual(self.client.get('/snapshot').content, JPEG)
        self.assertEqual(self.post(b'{}', 'application/json').status_code, 415)
        self.assertEqual(self.client.post('/snapshot', content=JPEG,
            headers={'Content-Type': 'image/jpeg', 'Content-Length': str(len(JPEG)+10)}).status_code, 400)
        self.assertEqual(self.client.post('/snapshot', content=b'bad',
            headers={'Content-Type': 'multipart/form-data'}).status_code, 422)
        self.assertEqual(self.client.post('/snapshot', files=[('file', ('a.jpg', JPEG)),
            ('file', ('b.jpg', JPEG))]).status_code, 422)
        self.assertEqual(self.client.get('/snapshot').content, JPEG)

    def test_size_and_pixel_limits_keep_the_previous_image(self):
        self.post()
        with patch.object(receiver, 'MAX_BYTES', 100):
            self.assertEqual(self.post().status_code, 413)
            self.assertEqual(self.client.post('/snapshot', files={'file': ('a.jpg', JPEG)}).status_code, 413)
        with patch.object(receiver, 'MAX_PIXELS', 100):
            self.assertEqual(self.post().status_code, 413)
        self.assertEqual(self.client.get('/snapshot').content, JPEG)

    def test_latest_photo_survives_a_separate_backend_process_and_marks_stale(self):
        self.post()
        script = 'import json; from backend.camera_receiver import latest,metadata; print(json.dumps(metadata(latest())))'
        result = subprocess.run([sys.executable, '-c', script], text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout)['sha256'], hashlib.sha256(JPEG).hexdigest())
        with store.db() as db:
            db.execute("UPDATE camera_snapshot SET received_at='2020-01-01T00:00:00+00:00'")
        response = self.client.get('/snapshot')
        self.assertEqual(response.content, JPEG)
        self.assertEqual(response.headers['x-camera-stale'], 'true')

    def test_browser_fetch_waits_then_receives_real_ingress_bytes(self):
        # Route the existing fetcher to the isolated receiver app over ASGI transport.
        original = httpx.AsyncClient
        def client_factory(**kwargs):
            return original(transport=httpx.ASGITransport(app=main.app), base_url='http://10.0.0.2:500')
        with patch.object(remote_camera.httpx, 'AsyncClient', client_factory):
            waiting = asyncio.run(remote_camera.fetch_frame('http://10.0.0.2:500/snapshot'))
            self.assertTrue(waiting['receiver_waiting'])
            self.assertIsNone(waiting['image'])
            self.post()
            frame = asyncio.run(remote_camera.fetch_frame('http://10.0.0.2:500/snapshot'))
            self.assertFalse(frame['receiver_waiting'])
            self.assertIsNotNone(frame['received_at'])
            self.assertIsNone(frame['captured_at'])
            Image.open(io.BytesIO(base64.b64decode(frame['image'].split(',')[1]))).verify()
            self.assertFalse(frame['stale'])


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        scratch.cleanup()
