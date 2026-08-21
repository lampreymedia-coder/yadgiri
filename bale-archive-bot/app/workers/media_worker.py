"""Media worker: drains the media_files backlog asynchronously.

Downloads (≤20MB), hashes, deduplicates by sha256 and writes through Storage.
Oversized files stay archived in the archive chat only.
"""

from __future__ import annotations

from pathlib import Path

from app.config import StorageBackend
from app.core.context import BotContext
from app.db.models import StorageStatus
from app.db.repositories.misc import MediaRepository
from app.domain.media import LocalStorage, S3Storage, Storage, process_media_file
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


async def run_media_once(ctx: BotContext, storage: Storage | None) -> int:
    if not ctx.settings.media_download_enabled:
        return 0
    handled = 0
    async with ctx.db.session() as session:
        repo = MediaRepository(session)
        backlog = await repo.backlog(limit=5)
        for media in backlog:
            await repo.update_status(media.id, StorageStatus.DOWNLOADING, increment_attempts=False)
            result = await process_media_file(
                ctx.api,
                storage,
                media,
                max_download_bytes=ctx.settings.max_download_bytes,
            )
            if result.sha256 is not None and result.status is StorageStatus.STORED:
                existing = await repo.find_by_sha(result.sha256)
                if existing is not None and existing.id != media.id:
                    await repo.update_status(
                        media.id,
                        StorageStatus.DUPLICATE,
                        sha256=result.sha256,
                        storage_bucket=existing.storage_bucket,
                        storage_key=existing.storage_key,
                    )
                    handled += 1
                    continue
            bucket = None
            if result.storage_key and ctx.settings.storage_backend is StorageBackend.S3:
                bucket = ctx.settings.s3_bucket_media
            await repo.update_status(
                media.id,
                result.status,
                sha256=result.sha256,
                storage_bucket=bucket,
                storage_key=result.storage_key,
                error=result.error,
            )
            handled += 1
    return handled
