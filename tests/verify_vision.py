"""Run against deployed weights with an isolated database; no production records."""
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
scratch = tempfile.TemporaryDirectory(prefix='tomato-vision-check-')
os.environ['HYDRO_DATA_DIR'] = scratch.name
os.environ['HYDRO_REAL_ONLY'] = '1'
os.environ['HYDRO_DEMO'] = '1'

from fastapi.testclient import TestClient
from PIL import Image
from backend import main
from backend.vision import VisionService, ModelUnavailable


class DeployedVisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model_path = os.environ['YOLO_MODEL_PATH']
        cls.client = TestClient(main.app)
        cls.client.post('/api/session', json={'role': 'teacher'}).raise_for_status()
        # Test fixture exists only in this temporary database; no MQTT connection.
        main.s.put('devices', {'id': 'TEST-ONLY', 'batch': 'TEST-ONLY', 'source': 'mqtt'})
        buf = io.BytesIO()
        Image.new('RGB', (640, 640), 'black').save(buf, format='JPEG')
        response = cls.client.post('/api/photos', data={'device': 'TEST-ONLY', 'batch': 'TEST-ONLY'},
                                   files={'file': ('blank-control.jpg', buf.getvalue(), 'image/jpeg')})
        response.raise_for_status()
        cls.photo_id = response.json()['id']

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        scratch.cleanup()

    def test_actual_cpu_inference_and_record_provenance(self):
        response = self.client.post('/api/recognitions', json={'photo_id': self.photo_id})
        self.assertEqual(response.status_code, 200, response.text)
        record = response.json()
        self.assertEqual(record['mode'], 'yolo')
        self.assertEqual(record['detections'], [])
        self.assertEqual(record['summary']['fruit_count'], 0)
        self.assertIsNone(record['summary']['average_confidence'])
        digest = hashlib.sha256(Path(self.model_path).read_bytes()).hexdigest()
        self.assertEqual(record['model']['sha256'], digest)
        self.assertEqual(record['model']['device'], 'cpu')
        self.assertEqual(record['model']['confidence_threshold'], 0.65)
        self.assertEqual([c['label'] for c in record['model']['classes']], ['成熟', '半成熟', '未成熟'])
        self.assertEqual(self.client.get(record['annotated']).headers['content-type'], 'image/jpeg')
        exported = self.client.get('/api/export/recognitions?format=json').json()
        self.assertEqual(next(r for r in exported if r['id'] == record['id'])['model'], record['model'])
        health = self.client.get('/api/health').json()
        self.assertTrue(health['real_only'])
        self.assertTrue(health['model']['ready'])
        cached = main.vision.load()
        self.assertIs(main.vision.load(), cached)

    def test_custom_threshold_reaches_model_and_is_saved(self):
        with patch.object(main.vision.load(), 'predict', wraps=main.vision.load().predict) as predict:
            response = self.client.post('/api/recognitions', json={'photo_id': self.photo_id, 'confidence_threshold': 0.8})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(predict.call_args.kwargs['conf'], 0.8)
        record = response.json()
        self.assertEqual(record['model']['confidence_threshold'], 0.8)
        self.assertTrue(all(d['confidence'] >= 0.8 for d in record['detections']))
        self.assertEqual(main.s.get('recognitions', record['id'])['model']['confidence_threshold'], 0.8)

    def test_invalid_thresholds_are_rejected_without_records(self):
        before = len(main.s.allof('recognitions'))
        for value in [-1, 0, 0.099, 0.951, 1, 65, 'invalid', None]:
            with self.subTest(value=value):
                response = self.client.post('/api/recognitions', json={'photo_id': self.photo_id, 'confidence_threshold': value})
                self.assertEqual(response.status_code, 422)
        self.assertEqual(len(main.s.allof('recognitions')), before)

    @unittest.skipUnless(os.getenv('VISION_CHECK_IMAGE'), 'No real-photo fixture supplied')
    def test_real_photo_threshold_removes_low_confidence_boxes(self):
        source = os.environ['VISION_CHECK_IMAGE']
        low, _ = main.vision.predict(source, confidence_threshold=0.25)
        filtered, metadata = main.vision.predict(source)
        self.assertTrue(any(d['confidence'] < 0.65 for d in low))
        self.assertTrue(filtered)
        self.assertLess(len(filtered), len(low))
        self.assertTrue(all(d['confidence'] >= 0.65 for d in filtered))
        self.assertEqual(metadata['confidence_threshold'], 0.65)

    def test_demo_is_forbidden_and_writes_nothing(self):
        before = len(main.s.allof('recognitions'))
        response = self.client.post('/api/recognitions', json={'photo_id': self.photo_id, 'demo': True})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(main.s.allof('recognitions')), before)

    def test_missing_weights_fail_closed(self):
        before = len(main.s.allof('recognitions'))
        missing = VisionService()
        with patch.dict(os.environ, {'YOLO_MODEL_PATH': '/missing/tomato.pt'}), patch.object(main, 'vision', missing):
            response = self.client.post('/api/recognitions', json={'photo_id': self.photo_id})
            self.assertEqual(response.status_code, 503)
            self.assertFalse(self.client.get('/api/health').json()['model']['ready'])
        self.assertEqual(len(main.s.allof('recognitions')), before)

    def test_unconfigured_model_fails_closed(self):
        with patch.dict(os.environ, {'YOLO_MODEL_PATH': ''}), patch.object(main, 'vision', VisionService()):
            self.assertEqual(self.client.post('/api/recognitions', json={'photo_id': self.photo_id}).status_code, 503)

    def test_bad_class_map_is_rejected(self):
        with patch.dict(os.environ, {'YOLO_CLASS_MAP': '{"0":"mislabeled"}'}):
            invalid = VisionService()
            with self.assertRaises(ModelUnavailable):
                invalid.load()
            self.assertFalse(invalid.status()['ready'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
