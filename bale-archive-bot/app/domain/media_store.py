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
        return True
    except (BaleAPIError, NetworkError, OSError) as exc:
        logger.warning("media_download_failed", media_id=job.media_id, error=str(exc))
    try:
        async with ctx.db.tx() as conn:
            await repo.set_storage_path(conn, job.media_id, job.fallback_ref)
    except Exception as exc:  # noqa: BLE001 — the post itself is already saved
        logger.error("media_fallback_update_failed", media_id=job.media_id, error=str(exc))
    return False


async def download_all(ctx: BotContext, jobs: list[PendingDownload]) -> None:
    for job in jobs:
        await download_one(ctx, job)
