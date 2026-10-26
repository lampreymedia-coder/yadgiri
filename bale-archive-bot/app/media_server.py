"""Public file server: signed view links and the manual upload page for big files.

    GET/HEAD /m/<media_id>/<sig>   view/download (Range + streaming)
    GET      /u/<media_id>/<sig>   upload form for a 'bale:' row
    POST     /u/<media_id>/<sig>   upload (raw file body, streamed to the media folder)

Only rows of PostMedia are read; an upload updates existing PostMedia columns
of that one row. Files are served only from inside <DATA_DIR>/media. The
signature is never logged. 60 requests per minute per IP.
"""

from __future__ import annotations

import asyncio
import html
import mimetypes
import os
import time
import uuid
from collections import deque
from collections.abc import AsyncIterator
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, unquote

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse

from app.db import repo
from app.i18n import fa
from app.mapping import MEDIA_AUDIO, MEDIA_DOCUMENT, MEDIA_IMAGE, MEDIA_VIDEO
from app.media_links import UPLOAD, VIEW, parse_bale_ref, verify
from app.observability.logging import get_logger
from app.timeutil import tehran_now

logger = get_logger(__name__)

CHUNK = 64 * 1024
INLINE_TYPES = ("video/", "audio/", "image/")

# Exact types for what the bot stores (mimetypes alone differs between systems).
_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".doc": "application/msword",
    ".xls": "application/vnd.ms-excel",
    ".zip": "application/zip",
    ".rar": "application/vnd.rar",
    ".txt": "text/plain; charset=utf-8",
}
_DEFAULT_UPLOAD_EXT = {MEDIA_IMAGE: ".jpg", MEDIA_VIDEO: ".mp4", MEDIA_AUDIO: ".m4a", MEDIA_DOCUMENT: ".bin"}


def content_type_for(path: Path, fallback: str | None = None) -> str:
    suffix = path.suffix.lower()
    if suffix in _TYPES:
        return _TYPES[suffix]
    guessed = mimetypes.guess_type(path.name)[0]
    return guessed or fallback or "application/octet-stream"


def is_inline(content_type: str) -> bool:
    return content_type.startswith(INLINE_TYPES) or content_type == "application/pdf"


def content_disposition(content_type: str, row: repo.MediaRow, path: Path) -> str:
    ext = path.suffix.lower()
    ascii_name = f"post{row.post_id}{ext}"
    if row.file_name:
        stem = PurePosixPath(row.file_name).stem or ascii_name
        # Keep the original name, but with the extension of the file actually served.
        name = f"{stem}{ext}" if is_inline(content_type) else row.file_name
    else:
        name = ascii_name
    kind = "inline" if is_inline(content_type) else "attachment"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name, safe='')}"


def parse_range(header: str | None, size: int) -> tuple[int, int] | None | str:
    """(start, end) inclusive; None = no/ignored range; 'bad' = unsatisfiable."""
    if not header or not header.startswith("bytes="):
        return None
    first = header[6:].split(",")[0].strip()
    start_s, _, end_s = first.partition("-")
    try:
        if start_s == "":
            length = int(end_s)
            if length <= 0:
                return "bad"
            start, end = max(0, size - length), size - 1
        else:
            start = int(start_s)
            end = int(end_s) if end_s else size - 1
    except ValueError:
        return None
    if start >= size or start > end:
        return "bad"
    return start, min(end, size - 1)


async def _stream(path: Path, start: int, length: int) -> AsyncIterator[bytes]:
    handle = await asyncio.to_thread(open, path, "rb")
    try:
        await asyncio.to_thread(handle.seek, start)
        remaining = length
        while remaining > 0:
            chunk = await asyncio.to_thread(handle.read, min(CHUNK, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
    finally:
        await asyncio.to_thread(handle.close)


def page(title: str, body: str, status: int = 200) -> HTMLResponse:
    document = (
        "<!doctype html><html lang='fa' dir='rtl'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{html.escape(title)}</title>"
        "<style>body{font-family:Tahoma,Vazirmatn,sans-serif;max-width:640px;margin:2em auto;"
        "padding:0 16px;line-height:1.9;background:#fafafa;color:#222}"
        ".box{background:#fff;border:1px solid #ddd;border-radius:10px;padding:1em 1.4em}"
        "button{font:inherit;padding:.4em 1.4em}</style></head><body><div class='box'>"
        f"<h3>{html.escape(title)}</h3>{body}</div></body></html>"
    )
    return HTMLResponse(document, status_code=status)


def not_found() -> HTMLResponse:
    return page("پیدا نشد", "<p>این پیوند معتبر نیست یا فایل آن دیگر وجود ندارد.</p>", 404)


class RateLimiter:
    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= self.per_minute:
            return False
        hits.append(now)
        if len(self._hits) > 10_000:
            self._hits = {k: v for k, v in self._hits.items() if v}
        return True


def _inside(root: Path, raw: str) -> Path | None:
    real_root = os.path.realpath(root)
    real = os.path.realpath(raw)
    if not real.startswith(real_root + os.sep) or not os.path.isfile(real):
        return None
    return Path(real)


def create_media_app(ctx: Any) -> FastAPI:
    """``ctx`` is the bot context (settings, db, compression queue, spawn)."""
    settings = ctx.settings
    limiter = RateLimiter(settings.media_requests_per_minute)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    def client_ip(request: Request) -> str:
        return request.client.host if request.client else "?"

    def log(kind: str, media_id: int, status: int, request: Request, **extra: object) -> None:
        logger.info("media_request", kind=kind, media_id=media_id, status=status, ip=client_ip(request), **extra)

    async def load(kind: str, media_id: int, sig: str) -> repo.MediaRow | None:
        if not verify(kind, media_id, sig, settings.media_link_secret):
            return None
        async with ctx.db.tx() as conn:
            return await repo.get_media(conn, media_id)

    @app.api_route("/m/{media_id}/{sig}", methods=["GET", "HEAD"])
    async def view(media_id: int, sig: str, request: Request) -> Response:
        if not limiter.allow(client_ip(request)):
            log(VIEW, media_id, 429, request)
            return page("درخواست زیاد", "<p>کمی بعد دوباره امتحان کنید.</p>", 429)
        row = await load(VIEW, media_id, sig)
        if row is None:
            log(VIEW, media_id, 404, request)
            return not_found()
        ref = parse_bale_ref(row.storage_path)
        if ref is not None:
            log(VIEW, media_id, 404, request, pending=True)
            return page("فایل هنوز روی سرور نیست", "<p>" + html.escape(fa.big_file_not_uploaded(ref[1])) + "</p>", 404)
        path = _inside(settings.media_root, row.storage_path)
        if path is None:
            log(VIEW, media_id, 404, request, outside=True)
            return not_found()
        size = (await asyncio.to_thread(path.stat)).st_size
        content_type = content_type_for(path, row.mime_type)
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Disposition": content_disposition(content_type, row, path),
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        }
        wanted = parse_range(request.headers.get("range"), size)
        if wanted == "bad":
            log(VIEW, media_id, 416, request)
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        if wanted is None:
            start, end, status = 0, size - 1, 200
        else:
            start, end = wanted  # type: ignore[misc]
            status = 206
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        length = max(0, end - start + 1)
        headers["Content-Length"] = str(length)
        log(VIEW, media_id, status, request)
        if request.method == "HEAD":
            return Response(status_code=status, headers=headers, media_type=content_type)
        return StreamingResponse(
            _stream(path, start, length), status_code=status, headers=headers, media_type=content_type
        )

    @app.get("/u/{media_id}/{sig}")
    async def upload_form(media_id: int, sig: str, request: Request) -> Response:
        if not limiter.allow(client_ip(request)):
            log(UPLOAD, media_id, 429, request)
            return page("درخواست زیاد", "<p>کمی بعد دوباره امتحان کنید.</p>", 429)
        row = await load(UPLOAD, media_id, sig)
        if row is None or parse_bale_ref(row.storage_path) is None:
            log(UPLOAD, media_id, 404, request)
            return not_found()
        log(UPLOAD, media_id, 200, request)
        ref = parse_bale_ref(row.storage_path)
        info = fa.upload_form_info(row.post_id, row.media_type, row.file_size, ref[1] if ref else None)
        body = (
            "<p>" + html.escape(info).replace("\n", "<br>") + "</p>"
            f"<p>حداکثر حجم: {fa.fa_digits(settings.max_upload_mb)} مگابایت</p>"
            "<input type='file' id='f'> <button id='b'>بارگذاری</button>"
            "<p id='s'></p>"
            "<script>document.getElementById('b').onclick=async function(){"
            "var f=document.getElementById('f').files[0];if(!f){return;}"
            "document.getElementById('s').textContent='در حال بارگذاری…';"
            "var r=await fetch(location.href,{method:'POST',body:f,headers:{"
            "'X-File-Name':encodeURIComponent(f.name),'Content-Type':'application/octet-stream'}});"
            "var t=await r.text();document.open();document.write(t);document.close();};</script>"
        )
        return page("بارگذاری فایل بزرگ", body)

    @app.post("/u/{media_id}/{sig}")
    async def upload(media_id: int, sig: str, request: Request) -> Response:
        if not limiter.allow(client_ip(request)):
            log(UPLOAD, media_id, 429, request)
            return page("درخواست زیاد", "<p>کمی بعد دوباره امتحان کنید.</p>", 429)
        row = await load(UPLOAD, media_id, sig)
        if row is None or parse_bale_ref(row.storage_path) is None:
            log(UPLOAD, media_id, 404, request)
            return not_found()
        limit = settings.max_upload_mb * 1024 * 1024
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            log(UPLOAD, media_id, 413, request)
            return page("فایل خیلی بزرگ است", f"<p>حداکثر {fa.fa_digits(settings.max_upload_mb)} مگابایت.</p>", 413)
        name = unquote(request.headers.get("x-file-name", ""))
        suffix = PurePosixPath(name).suffix.lower()
        if not (1 < len(suffix) <= 10 and suffix[1:].isalnum()):
            suffix = _DEFAULT_UPLOAD_EXT.get(row.media_type, ".bin")
        media_root = settings.media_root
        await asyncio.to_thread(media_root.mkdir, parents=True, exist_ok=True)
        tmp = media_root / f"upload-{uuid.uuid4().hex}{suffix}.part"
        received = 0
        handle = await asyncio.to_thread(open, tmp, "wb")
        too_big = False
        try:
            async for chunk in request.stream():
                received += len(chunk)
                if received > limit:
                    too_big = True
                    break
                await asyncio.to_thread(handle.write, chunk)
        finally:
            await asyncio.to_thread(handle.close)
        if too_big or received == 0:
            await asyncio.to_thread(tmp.unlink, missing_ok=True)
            status = 413 if too_big else 400
            log(UPLOAD, media_id, status, request)
            if too_big:
                return page("فایل خیلی بزرگ است", f"<p>حداکثر {fa.fa_digits(settings.max_upload_mb)} مگابایت.</p>", 413)
            return page("فایلی نرسید", "<p>دوباره امتحان کنید.</p>", 400)

        meta = await _check_type(tmp, row.media_type)
        if meta is None:
            await asyncio.to_thread(tmp.unlink, missing_ok=True)
            log(UPLOAD, media_id, 415, request)
            return page("نوع فایل نمی‌خواند", "<p>" + html.escape(fa.upload_wrong_type(row.media_type)) + "</p>", 415)
        width, height, duration = meta

        now = tehran_now()
        final = media_root / f"{now.year:04d}" / f"{now.month:02d}" / f"{uuid.uuid4().hex}{suffix}"
        await asyncio.to_thread(final.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(os.replace, tmp, final)
        mime = content_type_for(final).split(";")[0]
        async with ctx.db.tx() as conn:
            updated = await repo.set_media_uploaded(
                conn, media_id, str(final), received, mime, width, height, duration
            )
        if not updated:
            await asyncio.to_thread(final.unlink, missing_ok=True)
            log(UPLOAD, media_id, 404, request, race=True)
            return not_found()
        warning = ""
        if row.file_size and abs(received - row.file_size) / row.file_size > 0.05:
            warning = fa.upload_size_warning(received, row.file_size)
        log(UPLOAD, media_id, 200, request, size=received, size_warning=bool(warning))
        from app.domain.media_store import compress_stored

        ctx.spawn(compress_stored(ctx, media_id, final, row.media_type))
        body = "<p>" + html.escape(fa.UPLOAD_DONE) + "</p>"
        if warning:
            body += "<p>⚠️ " + html.escape(warning) + "</p>"
        return page("بارگذاری انجام شد", body)

    @app.api_route("/{rest:path}", methods=["GET", "HEAD", "POST"])
    async def fallback(rest: str) -> Response:
        return not_found()

    return app


async def _check_type(path: Path, media_type: int) -> tuple[int | None, int | None, int | None] | None:
    """(width, height, duration) when the file matches media_type, else None."""
    from app.domain.video_compress import probe

    if media_type == MEDIA_DOCUMENT:
        return None, None, None
    if media_type == MEDIA_IMAGE:

        def read_image() -> tuple[int, int] | None:
            from PIL import Image

            try:
                with Image.open(path) as image:
                    image.verify()
                with Image.open(path) as image:
                    return image.size
            except Exception:  # noqa: BLE001 — anything Pillow cannot read is not a picture
                return None

        size = await asyncio.to_thread(read_image)
        return (size[0], size[1], None) if size else None
    info = await probe(path)
    if info is None:
        return None
    duration = int(info.duration) if info.duration else None
    if media_type == MEDIA_VIDEO and info.has_video:
        return info.width, info.height, duration
    if media_type == MEDIA_AUDIO and info.has_audio and not info.has_video:
        return None, None, duration
    return None
