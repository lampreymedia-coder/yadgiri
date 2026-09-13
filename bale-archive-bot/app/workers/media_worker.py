"""Media worker: drains the media_files backlog asynchronously.

Downloads (≤20MB), hashes, deduplicates by sha256 *before* writing,
optionally compresses video with ffmpeg, then stores through Storage.
Oversized files stay archived in the archive chat only.
"""

from __future__ import annotations

from pathlib import Path

from app.config import StorageBackend
from app.core.context import BotContext
from app.db.models import MediaFile, StorageStatus
from app.db.repositories.misc import MediaRepository
from app.domain.media import (
    LocalStorage,
    S3Storage,
    Storage,
    VideoCompressionSettings,
    prepare_media_bytes,
    storage_key_for,
)
from app.domain.submission import image_storage_action
from app.observability.logging import get_logger

logger = get_logger(__name__)


def build_storage(ctx: BotContext) -> Storage | None:
    settings = ctx.settings
    if not settings.media_download_enabled:
        return None
    if settings.storage_backend is StorageBackend.S3:
        if not settings.s3_access_key or not settings.s3_secret_key or not settings.s3_endpoint_url:
            logger.warning("s3_storage_missing_credentials_using_local")
        else:
            return S3Storage(
                settings.s3_endpoint_url,
                settings.s3_access_key,
                settings.s3_secret_key,
                settings.s3_bucket_media,
            )
    root = settings.media_root_path
    if not root.is_absolute():
        root = Path.cwd() / root
    return LocalStorage(root)


def _compression_settings(ctx: BotContext) -> VideoCompressionSettings:
    s = ctx.settings
    return VideoCompressionSettings(
        enabled=s.video_compression_enabled,
        crf=s.video_crf,
        max_height=s.video_max_height,
        audio_bitrate=s.video_audio_bitrate,
        keep_original=s.keep_original_video,
    )


async def run_media_once(ctx: BotContext, storage: Storage | None) -> int:
    if not ctx.settings.media_download_enabled:
        return 0
    handled = 0
    to_download: list[MediaFile] = []
    async with ctx.db.session() as session:
        repo = MediaRepository(session)
        backlog = await repo.backlog(limit=20)
        for media in backlog:
            action = (
                image_storage_action(media.submission)
                if media.submission is not None
                else "download"
            )
            if action == "wait":
                continue
            if action == "skip":
                await repo.update_status(
                    media.id,
                    StorageStatus.SKIPPED_TOO_LARGE,
                    error="user_skipped_image",
                    increment_attempts=False,
                )
                handled += 1
                if handled >= 5:
                    break
                continue
            await repo.update_status(media.id, StorageStatus.DOWNLOADING, increment_attempts=False)
            to_download.append(media)
            if handled + len(to_download) >= 5:
                break

    compression = _compression_settings(ctx)
    for media in to_download:
        if handled >= 5:
            break
        prepared = await prepare_media_bytes(
            ctx.api,
            media,
            max_download_bytes=ctx.settings.max_download_bytes,
            compression=compression,
        )
        async with ctx.db.session() as session:
            repo = MediaRepository(session)
            if prepared.status is not StorageStatus.STORED or prepared.sha256 is None:
                await repo.update_status(
                    media.id,
                    prepared.status,
                    sha256=prepared.sha256,
                    error=prepared.error,
                    original_size_bytes=prepared.original_size_bytes,
                    stored_size_bytes=prepared.stored_size_bytes,
                    is_compressed=prepared.is_compressed,
                )
                handled += 1
                continue

            existing = await repo.find_by_sha(prepared.sha256)
            if existing is not None and existing.id != media.id:
                # Never write the second copy to disk.
                await repo.update_status(
                    media.id,
                    StorageStatus.DUPLICATE,
                    sha256=prepared.sha256,
                    storage_bucket=existing.storage_bucket,
                    storage_key=existing.storage_key,
                    original_size_bytes=prepared.original_size_bytes,
                    stored_size_bytes=0,
                    is_compressed=False,
                )
                logger.info(
                    "media_dedup_hit",
                    media_id=media.id,
                    existing_id=existing.id,
                    sha256=prepared.sha256,
                    saved_bytes=prepared.original_size_bytes,
                )
                handled += 1
                continue

            if storage is None or prepared.payload is None:
                await repo.update_status(
                    media.id,
                    StorageStatus.STORED,
                    sha256=prepared.sha256,
                    original_size_bytes=prepared.original_size_bytes,
                    stored_size_bytes=prepared.stored_size_bytes,
                    is_compressed=prepared.is_compressed,
                )
                handled += 1
                continue

            key = storage_key_for(media)
            try:
                stored = await storage.put(
                    key,
                    prepared.payload,
                    media.mime_type or "application/octet-stream",
                )
            except (ConnectionError, OSError, TimeoutError, ValueError) as exc:
                await repo.update_status(
                    media.id,
                    StorageStatus.FAILED,
                    sha256=prepared.sha256,
                    error=str(exc),
                    original_size_bytes=prepared.original_size_bytes,
                    stored_size_bytes=prepared.stored_size_bytes,
                    is_compressed=prepared.is_compressed,
                )
                handled += 1
                continue
            except Exception as exc:
                if type(exc).__module__.startswith(("botocore", "boto3", "aioboto3", "aiohttp")):
                    await repo.update_status(
                        media.id,
                        StorageStatus.FAILED,
                        sha256=prepared.sha256,
                        error=str(exc),
                        original_size_bytes=prepared.original_size_bytes,
                        stored_size_bytes=prepared.stored_size_bytes,
                        is_compressed=prepared.is_compressed,
                    )
                    handled += 1
                    continue
                raise

            bucket = None
            if ctx.settings.storage_backend is StorageBackend.S3:
                bucket = ctx.settings.s3_bucket_media
            await repo.update_status(
                media.id,
                StorageStatus.STORED,
                sha256=prepared.sha256,
                storage_bucket=bucket,
                storage_key=stored,
                original_size_bytes=prepared.original_size_bytes,
                stored_size_bytes=prepared.stored_size_bytes,
                is_compressed=prepared.is_compressed,
            )
            handled += 1
    return handled
