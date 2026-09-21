"""Regression checks for the verified tomato weights and mapping overrides."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.vision import ModelUnavailable, VisionService


class VisionLabelTests(unittest.TestCase):
    def load_labels(self, digest, override=''):
        model = SimpleNamespace(task='detect', names={0: 'Unripe', 1: 'Half-ripe', 2: 'Ripe'})
        with tempfile.NamedTemporaryFile(suffix='.pt') as weights:
            with patch.dict(os.environ, {'YOLO_MODEL_PATH': weights.name, 'YOLO_CLASS_MAP': override}), \
                 patch.dict(sys.modules, {'ultralytics': SimpleNamespace(YOLO=lambda *a, **kw: model)}), \
                 patch.object(hashlib, 'file_digest', return_value=SimpleNamespace(hexdigest=lambda: digest)):
                service = VisionService()
                service.load()
                return service.status()['classes']

    def test_verified_weights_correct_labels_preserve_raw_classes(self):
        classes = self.load_labels('d850966ea298360f50aa9da8340e8296619c38088ec4376936bdd5adc10f9719')
        self.assertEqual(classes, [
            {'id': 0, 'name': 'Unripe', 'label': '成熟'},
            {'id': 1, 'name': 'Half-ripe', 'label': '半成熟'},
            {'id': 2, 'name': 'Ripe', 'label': '未成熟'},
        ])

    def test_other_weights_keep_original_mapping(self):
        self.assertEqual([c['label'] for c in self.load_labels('different-weights')], ['未成熟', '半成熟', '成熟'])

    def test_explicit_mapping_still_takes_precedence(self):
        classes = self.load_labels('d850966ea298360f50aa9da8340e8296619c38088ec4376936bdd5adc10f9719',
                                   '{"0":"custom-0","1":"custom-1","2":"custom-2"}')
        self.assertEqual([c['label'] for c in classes], ['custom-0', 'custom-1', 'custom-2'])

    def test_invalid_override_still_fails(self):
        with self.assertLogs('backend.vision', level='ERROR'), self.assertRaises(ModelUnavailable):
            self.load_labels('different-weights', '{"0":"incomplete"}')


if __name__ == '__main__':
    unittest.main()
