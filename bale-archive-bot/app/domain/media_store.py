"""Where each file of a post lives (PostMedia.storage_path) and the background download.

* Files up to MAX_DOWNLOAD_MB: ``<DATA_DIR>/media/<year>/<month>/<uuid>.<ext>``
  — the row is written first, the download runs afterwards in the background.
* Bigger files (or a failed download): ``bale:<chat_id>/<message_id>`` — a
  reference to the copy in the archive group (or to the original message).

storage_path is never empty.
"""

from __future__ import annotations

import mimetypes
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.bale.errors import BaleAPIError, NetworkError
from app.core.context import BotContext
from app.db import repo
from app.domain.classify import MediaInfo
from app.domain.content import ContentType
from app.mapping import MEDIA_IMAGE, MEDIA_VIDEO
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
            if job.media_type == MEDIA_VIDEO:
                await compress_stored_video(ctx, job.media_id, job.path)
            elif job.media_type == MEDIA_IMAGE:
                await compress_stored_image(ctx, job.media_id, job.path)
        except Exception:  # noqa: BLE001 — the original file is kept
            logger.exception("compress_crashed", media_id=job.media_id)
        return True
    try:
        async with ctx.db.tx() as conn:
            await repo.set_storage_path(conn, job.media_id, job.fallback_ref)
    except Exception as exc:  # noqa: BLE001 — the post itself is already saved
        logger.error("media_fallback_update_failed", media_id=job.media_id, error=str(exc))
    return False


async def download_all(ctx: BotContext, jobs: list[PendingDownload]) -> None:
    for job in jobs:
        await download_one(ctx, job)


async def compress_stored_video(ctx: BotContext, media_id: int, path: Path) -> None:
    """One ffmpeg at a time; updates only storage_path and file_size of this row."""
    from app.domain.video_compress import compress_video

    async with ctx.compress_lock:
        try:
            result = await compress_video(path)
        except OSError as exc:
            logger.warning("video_compress_failed", media_id=media_id, error=str(exc))
            return
    ctx.compression_log.record(media_id, result)
    logger.info(
        "video_compress_done",
        media_id=media_id,
        replaced=result.replaced,
        reason=result.reason,
        saved_pct=result.saved_pct,
    )
    if not result.replaced:
        return
    try:
        async with ctx.db.tx() as conn:
            await repo.set_media_file(conn, media_id, str(result.path), result.new_size)
    except Exception as exc:  # noqa: BLE001 — the post is saved; file already replaced
        logger.error("video_compress_row_update_failed", media_id=media_id, error=str(exc))


async def compress_stored_image(ctx: BotContext, media_id: int, path: Path) -> None:
    """Same one-at-a-time queue as videos; updates only existing PostMedia columns."""
    from app.domain.image_compress import compress_image

    async with ctx.compress_lock:
        result = await compress_image(path)
    ctx.compression_log.record(media_id, result)
    logger.info(
        "image_compress_done",
        media_id=media_id,
        replaced=result.replaced,
        reason=result.reason,
        saved_pct=result.saved_pct,
    )
    if not result.replaced:
        return
    try:
        async with ctx.db.tx() as conn:
            await repo.set_media_image(
                conn,
                media_id,
                str(result.path),
                result.new_size,
                result.width,
                result.height,
                result.mime_type,
            )
    except Exception as exc:  # noqa: BLE001 — the post is saved; file already replaced
        logger.error("image_compress_row_update_failed", media_id=media_id, error=str(exc))
