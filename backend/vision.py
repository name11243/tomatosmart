"""Local YOLO inference; unavailable weights never produce substitute results."""
import hashlib
import json
import logging
import os
from pathlib import Path
from threading import RLock


class ModelUnavailable(RuntimeError):
    pass


class VisionService:
    def __init__(self):
        self._lock = RLock()
        self._model = None
        self._state = 'not_configured'
        self._error = None
        self._metadata = {}

    def status(self):
        return {'configured': bool(os.getenv('YOLO_MODEL_PATH')), 'ready': self._model is not None,
                'state': self._state, 'error': self._error, **self._metadata}

    def load(self):
        with self._lock:
            if self._model is not None:
                return self._model
            configured = os.getenv('YOLO_MODEL_PATH')
            if not configured:
                self._state = 'not_configured'
                raise ModelUnavailable('尚未配置识别模型，请联系管理员配置后端模型权重')
            self._state = 'loading'
            try:
                path = Path(configured).expanduser()
                if not path.is_absolute():
                    path = Path(__file__).resolve().parents[1] / path
                if not path.is_file():
                    raise FileNotFoundError('Configured local model file is missing')
                from ultralytics import YOLO
                model = YOLO(str(path), task='detect')
                if model.task != 'detect':
                    raise ValueError('A detection model is required')
                names = {int(k): str(v) for k, v in model.names.items()}
                translations = {'Unripe': '未成熟', 'Half-ripe': '半成熟', 'Ripe': '成熟'}
                labels = {str(k): translations.get(v, v) for k, v in names.items()}
                with path.open('rb') as weights:
                    digest = hashlib.file_digest(weights, 'sha256').hexdigest()
                # Real-photo checks confirmed reversed ripe/unripe names in this
                # specific best(3).pt; other weights keep their original mapping.
                if digest == 'd850966ea298360f50aa9da8340e8296619c38088ec4376936bdd5adc10f9719':
                    labels.update({'0': '成熟', '2': '未成熟'})
                override = os.getenv('YOLO_CLASS_MAP')
                if override:
                    labels = json.loads(override)
                    if not isinstance(labels, dict) or set(labels) != {str(k) for k in names} or not all(isinstance(v, str) and v for v in labels.values()):
                        raise ValueError('YOLO_CLASS_MAP must match every model class')
                self._labels = labels
                self._metadata = {'name': path.name, 'sha256': digest, 'task': 'detect',
                                  'device': os.getenv('YOLO_DEVICE', 'cpu'),
                                  'classes': [{'id': k, 'name': v, 'label': labels[str(k)]} for k, v in names.items()]}
                self._model = model
                self._state, self._error = 'ready', None
                return model
            except Exception as exc:
                logging.getLogger(__name__).exception('Failed to load local YOLO model')
                self._state, self._error = 'error', '识别模型加载失败，请检查后端权重与运行依赖'
                raise ModelUnavailable(self._error) from exc

    def predict(self, source, confidence_threshold=0.65):
        with self._lock:
            model = self.load()
            try:
                result = model.predict(source=source, device=self._metadata['device'], imgsz=640,
                                       conf=confidence_threshold, verbose=False, save=False)[0]
                detections = []
                for box in result.boxes:
                    confidence = float(box.conf[0])
                    if confidence < confidence_threshold:
                        continue
                    class_id = int(box.cls[0])
                    detections.append({'class_id': class_id, 'class_name': str(result.names[class_id]),
                                       'label': self._labels[str(class_id)],
                                       'confidence': round(confidence, 3),
                                       'box': [int(x) for x in box.xyxy[0].tolist()]})
                return detections, {**self._metadata, 'confidence_threshold': confidence_threshold, 'image_size': 640}
            except Exception as exc:
                logging.getLogger(__name__).exception('YOLO inference failed')
                raise ModelUnavailable('模型推理失败，请检查权重与运行依赖') from exc


vision = VisionService()
