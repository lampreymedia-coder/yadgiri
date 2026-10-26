"""Where each file of a post lives (PostMedia.storage_path) and the background download.

* Files up to MAX_DOWNLOAD_MB: ``<DATA_DIR>/media/<year>/<month>/<uuid>.<ext>``
  — the row is written first, the download runs afterwards in the background.
* Bigger files (or a failed download): ``bale:<chat_id>/<message_id>`` — a
  reference to the copy in the archive group (or to the original message).

storage_path is never empty.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import mimetypes
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from app.bale.errors import BaleAPIError, NetworkError
from app.core.context import BotContext
from app.db import repo
from app.domain.classify import MediaInfo
from app.domain.content import ContentType
from app.mapping import MEDIA_AUDIO, MEDIA_IMAGE, MEDIA_VIDEO
from app.observability.logging import get_logger
from app.timeutil import tehran_now

logger = get_logger(__name__)

_DEFAULT_EXT = {
    ContentType.IMAGE: ".jpg",
    ContentType.VIDEO: ".mp4",
    ContentType.ANIMATION: ".mp4",
    ContentType.VOICE: ".ogg",
    ContentType.AUDIO: ".mp3",
    ContentType.DOCUMENT: ".bin",
}


def bale_ref(chat_id: int, message_id: int) -> str:
    return f"bale:{chat_id}/{message_id}"


def file_extension(kind: ContentType, info: MediaInfo) -> str:
    if info.file_name:
        suffix = PurePosixPath(info.file_name).suffix.lower()
        if 1 < len(suffix) <= 10 and suffix[1:].isalnum():
            return suffix
    if info.mime_type:
        guessed = mimetypes.guess_extension(info.mime_type.split(";")[0].strip())
        if guessed:
            return guessed
    return _DEFAULT_EXT.get(kind, ".bin")


def local_path(media_root: Path, kind: ContentType, info: MediaInfo) -> Path:
    now = tehran_now()
    return (
        media_root
        / f"{now.year:04d}"
        / f"{now.month:02d}"
        / f"{uuid.uuid4().hex}{file_extension(kind, info)}"
    )


@dataclass(slots=True)
class PendingDownload:
    media_id: int
    file_id: str
    path: Path
    fallback_ref: str
    media_type: int = 0  # PostMedia.media_type code (app.mapping)


async def download_one(ctx: BotContext, job: PendingDownload) -> bool:
    """Fetch one file to ``job.path``. On failure point the row at the Bale copy."""
    try:
        info = await ctx.api.get_file(job.file_id)
        if not info.file_path:
            msg = "getFile returned no file_path"
            raise BaleAPIError("getFile", 400, msg)
        data = await ctx.api.client.download_file(info.file_path, ctx.settings.max_download_bytes)
        job.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = job.path.with_suffix(job.path.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(job.path)
        logger.info("media_stored", media_id=job.media_id, path=str(job.path), size=len(data))
    except (BaleAPIError, NetworkError, OSError) as exc:
        logger.warning("media_download_failed", media_id=job.media_id, error=str(exc))
    else:
        try:
            await compress_stored(ctx, job.media_id, job.path, job.media_type)
        except Exception:  # noqa: BLE001 — the original file is kept
            logger.exception("compress_crashed", media_id=job.media_id)
        return True
    try:
        async with ctx.db.tx() as conn:
            await repo.set_storage_path(conn, job.media_id, job.fallback_ref)
    except Exception as exc:  # noqa: BLE001 — the post itself is already saved
        logger.error("media_fallback_update_failed", media_id=job.media_id, error=str(exc))
        return False
    await notify_pending_uploads(ctx, [job.media_id])
    return False


async def download_all(ctx: BotContext, jobs: list[PendingDownload]) -> None:
    for job in jobs:
        await download_one(ctx, job)


async def notify_pending_uploads(ctx: BotContext, media_ids: list[int]) -> None:
    """Tell the admins (private chat) where to upload files the bot could not download."""
    from app.i18n import fa
    from app.media_links import build_upload_url, parse_bale_ref

    if not media_ids or not ctx.settings.media_link_secret:
        return
    async with ctx.db.tx() as conn:
        rows = await repo.pending_upload_rows(conn, media_ids)
    for row in rows:
        ref = parse_bale_ref(row.storage_path)
        text = fa.pending_upload_notice(
            row.post_id,
            row.media_type,
            row.file_size,
            ref[1] if ref else None,
            build_upload_url(row.id, ctx.settings),
        )
        await ctx.notifier.send_all(text)


@contextlib.asynccontextmanager
async def compression_slot(deps: Any) -> AsyncIterator[None]:
    """One compression job at a time: in this process (asyncio lock) and across
    processes such as scripts/compress_existing.py (a file lock)."""
    lock_path = deps.settings.data_path / "compress.lock"

    def acquire() -> Any:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(lock_path, "a+")  # noqa: SIM115 — closed in release()
        fcntl.flock(handle, fcntl.LOCK_EX)
        return handle

    def release(handle: Any) -> None:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()

    async with deps.compress_lock:
        handle = await asyncio.to_thread(acquire)
        try:
            yield
        finally:
            await asyncio.to_thread(release, handle)


async def compress_stored(deps: Any, media_id: int, path: Path, media_type: int) -> Any:
    """Compress/convert one stored file by its PostMedia.media_type.

    ``deps`` needs ``settings``, ``db``, ``compression_log`` and ``compress_lock``
    (the bot context, or a small stand-in in scripts). Documents are left as is.
    Only existing PostMedia columns are updated.
    """
    from app.domain.image_compress import compress_image
    from app.domain.video_compress import compress_video, convert_audio

    worker = {MEDIA_VIDEO: compress_video, MEDIA_AUDIO: convert_audio, MEDIA_IMAGE: compress_image}.get(
        media_type
    )
    if worker is None:
        return None
    async with compression_slot(deps):
        result = await worker(path)
    deps.compression_log.record(media_id, result)
    logger.info(
        "compress_done",
        media_id=media_id,
        media_type=media_type,
        replaced=result.replaced,
        reason=result.reason,
        saved_pct=result.saved_pct,
    )
    if result.replaced:
        try:
            async with deps.db.tx() as conn:
                await repo.set_media_compressed(
                    conn,
                    media_id,
                    str(result.path),
                    result.new_size,
                    result.mime_type,
                    result.width,
                    result.height,
                )
        except Exception as exc:  # noqa: BLE001 — the post is saved; file already replaced
            logger.error("compress_row_update_failed", media_id=media_id, error=str(exc))
    return result
