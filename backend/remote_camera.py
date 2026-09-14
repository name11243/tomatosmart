"""Read the ESP32-P4 firmware's /image snapshot without changing device settings."""
import asyncio
import base64
import hashlib
import io
import ipaddress
from urllib.parse import urlsplit, urlunsplit
import httpx
from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
from . import store

MAX_BYTES = 8 * 1024 * 1024


class CameraFrameRequest(BaseModel):
    url: str = Field(min_length=1, max_length=512)


def camera_url(value):
    try:
        value = value.strip()
        parsed = urlsplit(value if '://' in value else 'http://' + value)
        if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password or parsed.fragment:
            raise ValueError()
        address = ipaddress.ip_address(parsed.hostname or '')
        if address.version != 4 or address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified or address.is_reserved:
            raise ValueError()
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError()
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path if parsed.path not in ('', '/') else '/image', parsed.query, ''))
    except ValueError:
        raise HTTPException(422, '请填写摄像头的 HTTP/HTTPS IPv4 地址，例如 http://192.168.4.1/image')


async def fetch_frame(value):
    url = camera_url(value)
    try:
        async with asyncio.timeout(8):
            async with httpx.AsyncClient(timeout=httpx.Timeout(5, connect=3), follow_redirects=False, trust_env=False) as client:
                async with client.stream('GET', url, headers={'Accept': 'image/jpeg,image/*', 'Cache-Control': 'no-cache'}) as response:
                    if response.status_code == 404:
                        raise HTTPException(503, '设备尚未提供照片。请检查 /image 地址，确认设备已连上 Wi-Fi 且 USB 摄像头就绪，再等待约 20 秒。')
                    if response.status_code != 200:
                        raise HTTPException(503, '摄像头未返回照片，请检查设备地址和连接状态。')
                    data = bytearray()
                    async for chunk in response.aiter_bytes(64 * 1024):
                        data.extend(chunk)
                        if len(data) > MAX_BYTES:
                            raise HTTPException(413, '摄像头图片超过 8 MB 限制')
        with Image.open(io.BytesIO(data)) as source:
            if source.width * source.height > 24_000_000:
                raise HTTPException(413, '摄像头图片尺寸过大')
            source.load()
            image = source.convert('RGB')
        image.thumbnail((2400, 2400))
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=92)
        jpeg = output.getvalue()
        return {'image': 'data:image/jpeg;base64,' + base64.b64encode(jpeg).decode(),
                'source_url': url, 'fetched_at': store.now(), 'captured_at': None,
                'sha256': hashlib.sha256(jpeg).hexdigest(), 'refresh_seconds': 20}
    except (httpx.HTTPError, TimeoutError):
        raise HTTPException(503, '无法获取摄像头照片。请让运行本系统的电脑连接摄像头热点或同一局域网，并检查设备 IP。')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(503, '该地址没有返回有效图片；此固件的照片接口为 /image。')
