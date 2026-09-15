"""ESP32 photo ingress: one persistent latest image, independent of user albums.

The firmware has no browser session. Its narrowly scoped POST /snapshot endpoint
accepts raw JPEG/PNG or one multipart file. GET returns the original uploaded bytes.
"""
import asyncio
import hashlib
import io
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartParser, MultiPartException
from python_multipart.exceptions import MultipartParseError
from PIL import Image, UnidentifiedImageError

from . import store

router = APIRouter()
MAX_BYTES = 8 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_BYTES + 64 * 1024  # multipart envelope, not extra image data
MAX_PIXELS = 24_000_000
STALE_SECONDS = 60
RECEIVER_HEADERS = {'Cache-Control': 'no-store, max-age=0',
                    'X-Content-Type-Options': 'nosniff',
                    'X-Camera-Receiver': 'tomatosmart'}


def initialize():
    with store.db() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS camera_snapshot (
            id INTEGER PRIMARY KEY CHECK(id=1), image BLOB NOT NULL,
            media_type TEXT NOT NULL, sha256 TEXT NOT NULL, received_at TEXT NOT NULL,
            sender TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL)''')


initialize()


def latest():
    with store.db() as db:
        row = db.execute('SELECT * FROM camera_snapshot WHERE id=1').fetchone()
    return dict(row) if row else None


def metadata(row):
    if not row:
        return {'ready': True, 'has_photo': False, 'captured_at': None,
                'received_at': None, 'message': '接收服务已就绪，等待 ESP32-P4 上传照片。'}
    age = max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(row['received_at'])).total_seconds())
    return {'ready': True, 'has_photo': True, 'captured_at': None,
            'received_at': row['received_at'], 'age_seconds': round(age, 1),
            'stale': age > STALE_SECONDS, 'stale_after_seconds': STALE_SECONDS,
            'bytes': len(row['image']), 'sha256': row['sha256'],
            'content_type': row['media_type'], 'width': row['width'], 'height': row['height'],
            'sender': row['sender'], 'source': 'http_upload',
            'message': '超过 60 秒未收到新推送，保留最后一张照片。' if age > STALE_SECONDS else '已收到设备上传的照片。'}


def save_image(data, sender):
    if not data:
        raise HTTPException(422, '上传内容为空，请发送 JPEG/PNG 图片数据。')
    if len(data) > MAX_BYTES:
        raise HTTPException(413, '上传照片不能超过 8 MB')
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ('JPEG', 'PNG'):
                raise HTTPException(415, '仅接收 JPEG/PNG 图片')
            if image.width * image.height > MAX_PIXELS:
                raise HTTPException(413, '上传照片不能超过 2400 万像素')
            width, height = image.size
            media_type = 'image/jpeg' if image.format == 'JPEG' else 'image/png'
            image.verify()
        # verify() alone does not detect all truncated JPEG payloads.
        with Image.open(io.BytesIO(data)) as image:
            image.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, '上传内容不是完整、有效的 JPEG/PNG 图片，已保留上次照片。') from exc
    row = dict(image=data, media_type=media_type, sha256=hashlib.sha256(data).hexdigest(),
               received_at=store.now(), sender=sender[:100], width=width, height=height)
    # One transaction atomically replaces image and metadata. No accumulating photo files,
    # half-written previews, automatic recognitions, or overwrites of user album records.
    with store.db() as db:
        db.execute('''INSERT OR REPLACE INTO camera_snapshot
            (id,image,media_type,sha256,received_at,sender,width,height)
            VALUES(1,:image,:media_type,:sha256,:received_at,:sender,:width,:height)''', row)
    return {'ok': True, 'status': 'ok', 'message': '照片已接收并保存', **metadata(row)}


async def read_upload(request):
    encoding = request.headers.get('content-encoding', 'identity').lower()
    if encoding != 'identity':
        raise HTTPException(415, '请直接上传图片，不使用压缩的 HTTP 请求体。')
    content_type = request.headers.get('content-type', '').split(';')[0].strip().lower()
    if content_type not in ('', 'image/jpeg', 'image/jpg', 'image/png', 'application/octet-stream', 'multipart/form-data'):
        raise HTTPException(415, '请上传 JPEG/PNG 原始数据或 multipart 文件。')
    limit = MAX_REQUEST_BYTES if content_type == 'multipart/form-data' else MAX_BYTES
    content_length = request.headers.get('content-length')
    if content_length:
        try:
            length = int(content_length)
        except ValueError:
            raise HTTPException(400, 'Content-Length 无效')
        if length < 0:
            raise HTTPException(400, 'Content-Length 无效')
        if length > limit:
            raise HTTPException(413, '上传照片不能超过 8 MB')
    data = bytearray()
    try:
        async with asyncio.timeout(30):
            async for chunk in request.stream():
                if len(data) + len(chunk) > limit:
                    raise HTTPException(413, '上传照片不能超过 8 MB')
                data.extend(chunk)
    except TimeoutError:
        raise HTTPException(408, '照片上传超时，请重新上传完整图片。')
    if content_length and len(data) != length:
        raise HTTPException(400, '照片请求体长度与 Content-Length 不一致')
    if content_type != 'multipart/form-data':
        return bytes(data)

    async def body_stream():
        yield bytes(data)
    try:
        form = await MultiPartParser(request.headers, body_stream(), max_files=1,
                                     max_fields=8, max_part_size=MAX_BYTES).parse()
    except (MultiPartException, MultipartParseError) as exc:
        raise HTTPException(422, 'multipart 上传格式无效，每次只能上传一张照片。') from exc
    try:
        files = [value for _, value in form.multi_items() if isinstance(value, UploadFile)]
        if len(files) != 1:
            raise HTTPException(422, 'multipart 请求必须包含一个图片文件。')
        return await files[0].read(MAX_BYTES + 1)
    finally:
        await form.close()


@router.post('/snapshot')
async def receive_snapshot(request: Request):
    data = await read_upload(request)
    sender = request.headers.get('x-real-ip') or (request.client.host if request.client else 'unknown')
    result = await asyncio.to_thread(save_image, data, sender)
    return JSONResponse(result, headers=RECEIVER_HEADERS)


@router.api_route('/snapshot', methods=['GET', 'HEAD'])
def get_snapshot(request: Request):
    row = latest()
    if not row:
        return JSONResponse({'detail': '接收服务已运行，但尚未收到 ESP32-P4 上传的照片。'},
                            status_code=404, headers=RECEIVER_HEADERS)
    info = metadata(row)
    headers = {**RECEIVER_HEADERS, 'X-Camera-Received-At': row['received_at'],
               'X-Camera-Sha256': row['sha256'], 'X-Camera-Stale': str(info['stale']).lower(),
               'Content-Length': str(len(row['image']))}
    return Response(content=b'' if request.method == 'HEAD' else row['image'],
                    media_type=row['media_type'], headers=headers)
