"""Read the camera service's latest photo without changing device settings.

The backend runs inside a Docker container, so every failure has to say whether the
address was refused by a reachable host, unreachable from the container's network, or
answered something that is not a photo. The photo endpoint path is detected as well:
the ESP32-P4 firmware answers `/image`, other camera services answer `/snapshot`.
"""
import asyncio
import base64
import hashlib
import io
import ipaddress
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import httpx
from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
from . import camera_config, store

MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 24_000_000
# Known photo endpoints, tried in order after the address the page asked for.
PHOTO_PATHS = ('/snapshot', '/image', '/download')
# Another path on the same host only helps when this host answered at all.
RETRY_FAILURES = ('empty', 'status', 'not_image', 'redirect')
CONNECT_TIMEOUT = 3.0
READ_TIMEOUT = 5.0
TOTAL_TIMEOUT = 8.0
HEADERS = {'Accept': 'image/jpeg,image/*', 'Cache-Control': 'no-cache'}
EXAMPLE = 'http://设备IPv4:端口/snapshot'
REASONS = {
    'refused': '该地址可达，但没有服务监听这个端口（连接被拒绝）',
    'timeout': '连接超时：该地址不可达，或端口未开放',
    'unreachable': '网络不可达：后端所在的网络没有到该地址的路由',
    'dns': '主机名无法解析：地址请填写 IPv4 或可直接解析的主机名',
    'connect': '无法建立连接',
    'http': 'HTTP 请求失败',
    'empty': '对方返回 404：设备端暂时没有可用照片',
    'status': '对方返回的 HTTP 状态不是 200',
    'not_image': '该地址返回的不是有效图片（JPEG/PNG）',
    'too_large': '照片超过后端允许的大小或像素限制',
    'redirect': '该地址返回重定向，后端不跟随跳转',
}


class CameraFrameRequest(BaseModel):
    url: str = Field(default_factory=lambda: default_url(), min_length=1, max_length=512)


def default_url():
    """The address configured in backend/config/camera.yaml; the page may replace it."""
    return camera_config.read()['url']


def refresh_seconds():
    return camera_config.read()['refresh_seconds']


def in_docker():
    return Path('/.dockerenv').exists()


def example_url():
    configured = default_url()
    return configured or EXAMPLE


def camera_url(value):
    """Validate an address and complete a bare host:port with the configured endpoint path."""
    try:
        value = str(value).strip()
        if not value:
            raise ValueError()
        configured = urlsplit(default_url() or '')
        parsed = urlsplit(value if '://' in value else 'http://' + value)
        if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password or parsed.fragment:
            raise ValueError()
        address = ipaddress.ip_address(parsed.hostname or '')
        if address.version != 4 or address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified or address.is_reserved:
            raise ValueError()
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError()
        # A bare host:port reuses the configured endpoint path instead of a hard-coded one.
        configured_path = configured.path if configured and configured.path not in ('', '/') else '/snapshot'
        path = parsed.path if parsed.path not in ('', '/') else configured_path
        return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ''))
    except ValueError:
        raise HTTPException(422, f'请填写摄像头的 HTTP/HTTPS IPv4 地址，例如 {example_url()}')


def candidate_urls(value):
    """The address the page asked for first, then the other known photo endpoints on the same host."""
    requested = camera_url(value)
    parsed = urlsplit(requested)
    candidates = [requested]
    for path in PHOTO_PATHS:
        alternative = urlunsplit((parsed.scheme, parsed.netloc, path, '', ''))
        if alternative not in candidates:
            candidates.append(alternative)
    return candidates


def _causes(exc):
    """The exception plus its cause chain: httpx hides 'connection refused' in the cause."""
    seen, current = [], exc
    while current is not None and current not in seen:
        seen.append(current)
        current = current.__cause__ or current.__context__
    return seen


def _failure_kind(exc):
    chain = _causes(exc)
    text = ' | '.join(str(item).lower() for item in chain)
    if any(isinstance(item, (httpx.TimeoutException, TimeoutError)) for item in chain):
        return 'timeout'
    if any(isinstance(item, ConnectionRefusedError) for item in chain) or 'refused' in text:
        return 'refused'
    if isinstance(exc, (httpx.ConnectError, OSError)):
        if 'unreachable' in text or 'no route' in text:
            return 'unreachable'
        if 'name or service not known' in text or 'nodename nor servname' in text or 'getaddrinfo' in text:
            return 'dns'
        return 'connect'
    return 'http'


def encode_photo(data):
    """Decode one camera payload into the JPEG the page displays; raises HTTPException when unusable."""
    with Image.open(io.BytesIO(data)) as source:
        if source.width * source.height > MAX_PIXELS:
            raise HTTPException(413, '摄像头图片尺寸过大')
        source.load()
        image = source.convert('RGB')
    image.thumbnail((2400, 2400))
    output = io.BytesIO()
    image.save(output, format='JPEG', quality=92)
    return output.getvalue()


async def _attempt(client, url):
    """One GET against one address; never raises for network or content problems."""
    started = time.perf_counter()
    report = {'url': url, 'ok': False, 'status': None, 'content_type': '', 'bytes': 0,
              'elapsed_ms': 0, 'failure': None, 'message': '', 'image': None, 'jpeg': None,
              'receiver_waiting': False, 'received_at': None, 'stale': False}
    try:
        async with asyncio.timeout(TOTAL_TIMEOUT):
            async with client.stream('GET', url, headers=HEADERS) as response:
                report['status'] = response.status_code
                report['content_type'] = (response.headers.get('content-type') or '').split(';')[0].strip().lower()
                receiver = response.headers.get('x-camera-receiver') == 'tomatosmart'
                if receiver:
                    report['received_at'] = response.headers.get('x-camera-received-at')
                    report['stale'] = response.headers.get('x-camera-stale') == 'true'
                if response.status_code == 404:
                    report.update(failure='empty', message=REASONS['empty'])
                    if receiver:
                        report.update(receiver_waiting=True, message='照片接收服务已连通，等待 ESP32-P4 上传照片。')
                    return report
                if 300 <= response.status_code < 400:
                    report.update(failure='redirect', message=f"{REASONS['redirect']}（HTTP {response.status_code}）")
                    return report
                if response.status_code != 200:
                    report.update(failure='status', message=f"{REASONS['status']}（HTTP {response.status_code}）")
                    return report
                data = bytearray()
                async for chunk in response.aiter_bytes(64 * 1024):
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        report.update(failure='too_large', message=REASONS['too_large'])
                        return report
        report['bytes'] = len(data)
        report['image'] = bytes(data)
    except (httpx.HTTPError, TimeoutError) as exc:
        kind = _failure_kind(exc)
        report.update(failure=kind, message=REASONS[kind])
    except OSError as exc:
        report.update(failure='connect', message=f'{REASONS["connect"]}：{exc}')
    finally:
        report['elapsed_ms'] = int((time.perf_counter() - started) * 1000)
    if report['image'] is not None:
        try:
            report['jpeg'] = encode_photo(report['image'])
            report.update(ok=True, failure=None, message='已取到照片')
        except HTTPException as exc:
            report.update(failure='too_large' if exc.status_code == 413 else 'not_image', message=str(exc.detail))
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            report.update(failure='not_image', message=REASONS['not_image'])
        report['image'] = None
    return report


def advice(attempts):
    """Turn the attempts into the concrete next step for the person at the machine."""
    kinds = {item['failure'] for item in attempts}
    lines = []
    if 'refused' in kinds:
        lines.append('地址可达但端口没有服务：核对摄像头的端口，并确认设备已经启动拍照服务。')
    if 'timeout' in kinds or 'unreachable' in kinds:
        if in_docker():
            lines.append('后端运行在 Docker 容器中：容器只能访问与宿主机路由可达的地址；如果摄像头是设备自带热点（默认 192.168.4.1），请先让运行 Docker 的这台电脑连上该热点，再重新检测。')
        else:
            lines.append('请让运行本系统的电脑与摄像头处于同一局域网，并核对设备 IP。')
    if 'empty' in kinds:
        lines.append('设备还没有上传照片：确认 USB 摄像头已就绪，等待约 20 秒后重新检测。')
    if 'not_image' in kinds or 'redirect' in kinds:
        lines.append('该地址返回的是网页而不是照片：请填写直接返回照片的接口（固件为 /image，其他服务可能是 /snapshot）。')
    if 'dns' in kinds:
        lines.append('请填写 IPv4 地址，或确认后端容器能解析该主机名。')
    return lines


def summary(attempts):
    lines = [f'无法获取摄像头照片；后端已依次请求 {len(attempts)} 个地址：']
    lines += [f"· {item['url']} → {item['message']}" for item in attempts]
    lines += advice(attempts)
    return '\n'.join(lines)


def public_attempts(attempts):
    return [{key: item[key] for key in ('url', 'ok', 'status', 'content_type', 'bytes', 'elapsed_ms', 'failure', 'message')} for item in attempts]


async def probe(value, detect_endpoints=True):
    """Try the requested address and the known photo endpoints; report every attempt honestly."""
    requested = camera_url(value)
    attempts = []
    timeout = httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
        for url in candidate_urls(value) if detect_endpoints else [requested]:
            report = await _attempt(client, url)
            attempts.append(report)
            if report['ok'] or report['receiver_waiting'] or report['failure'] not in RETRY_FAILURES:
                break
    winner = next((item for item in attempts if item['ok']), None)
    detected = bool(winner) and winner['url'] != requested
    return {
        'ok': bool(winner),
        'requested_url': requested,
        'source_url': winner['url'] if winner else None,
        'endpoint_detected': detected,
        'attempts': public_attempts(attempts),
        'message': ('设备照片地址实际为 ' + winner['url'] if detected else (winner['message'] if winner else summary(attempts))),
        'advice': advice(attempts),
        'image': ('data:image/jpeg;base64,' + base64.b64encode(winner['jpeg']).decode()) if winner else None,
        'sha256': hashlib.sha256(winner['jpeg']).hexdigest() if winner else None,
        'captured_at': None,
        'fetched_at': store.now() if winner else None,
        'refresh_seconds': refresh_seconds(),
        'backend': {'in_docker': in_docker()},
        'receiver_waiting': not winner and any(item['receiver_waiting'] for item in attempts),
        'received_at': winner['received_at'] if winner else None,
        'stale': winner['stale'] if winner else False,
    }


async def fetch_frame(value):
    """Return the newest camera photo, reporting which address actually answered."""
    report = await probe(value, detect_endpoints=False)
    if report['receiver_waiting']:
        return {'image': None, 'source_url': report['requested_url'], 'captured_at': None,
                'fetched_at': None, 'received_at': None, 'receiver_waiting': True,
                'refresh_seconds': report['refresh_seconds'],
                'message': '照片接收服务已连通，等待 ESP32-P4 上传；页面将自动刷新。'}
    if not report['ok']:
        oversized = any(item['failure'] == 'too_large' for item in report['attempts'])
        raise HTTPException(413 if oversized else 503, report['message'])
    return {key: report[key] for key in ('image', 'source_url', 'sha256', 'captured_at', 'fetched_at', 'refresh_seconds')} | {
        'requested_url': report['requested_url'],
        'endpoint_detected': report['endpoint_detected'],
        'attempts': report['attempts'],
        'backend': report['backend'],
        'receiver_waiting': False,
        'received_at': report['received_at'],
        'stale': report['stale'],
    }
