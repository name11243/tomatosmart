"""Backend YAML owns the default remote camera address used by the maturity page."""
import os
import tempfile
import threading
from pathlib import Path
import yaml

LOCK = threading.RLock()
DEFAULT_PATH = Path(__file__).parent / 'config' / 'camera.yaml'
# No address is baked in here: backend/config/camera.yaml is the only authority, so a stale
# duplicate default can never silently replace the address the user saved.
FALLBACK = {'url': '', 'refresh_seconds': 20, 'rotate': 0}
ROTATE_CHOICES = (0, 90, 180, 270)


def path():
    return Path(os.getenv('HYDRO_CAMERA_CONFIG', str(DEFAULT_PATH)))


def _camera(data):
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError('摄像头 YAML 必须是对象')
    camera = data.get('camera')
    if camera is None:
        return {}
    if not isinstance(camera, dict):
        raise ValueError('摄像头 YAML 必须包含 camera 对象')
    return camera


def read():
    with LOCK:
        target = path()
        camera = _camera(yaml.safe_load(target.read_text(encoding='utf-8'))) if target.exists() else {}
        url = str(camera.get('url') or '').strip()
        try:
            refresh = int(camera.get('refresh_seconds', FALLBACK['refresh_seconds']))
        except (TypeError, ValueError):
            refresh = FALLBACK['refresh_seconds']
        try:
            rotate = int(camera.get('rotate', FALLBACK['rotate']))
        except (TypeError, ValueError):
            rotate = FALLBACK['rotate']
        if rotate not in ROTATE_CHOICES:
            rotate = FALLBACK['rotate']
        return {'url': url, 'refresh_seconds': min(max(refresh, 5), 600), 'rotate': rotate}


def save(url):
    """Validate the address with the fetcher's rules, then persist it as the new default."""
    from .remote_camera import camera_url
    value = camera_url(url)
    with LOCK:
        target = path()
        target.parent.mkdir(parents=True, exist_ok=True)
        camera = {'url': value, 'refresh_seconds': read()['refresh_seconds'], 'rotate': read()['rotate']}
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent, delete=False) as out:
            yaml.safe_dump({'camera': camera}, out, allow_unicode=True, sort_keys=False)
            temp = Path(out.name)
        os.replace(temp, target)
        return camera
