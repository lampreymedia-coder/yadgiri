"""Media worker: drains the media_files backlog asynchronously.

Downloads (≤20MB), hashes, deduplicates by sha256 and uploads to object
storage. Oversized files stay archived in the archive channel only.
"""

from __future__ import annotations

from app.core.context import BotContext
from app.db.models import StorageStatus
from app.db.repositories.misc import MediaRepository
from app.domain.media import ObjectStorage, S3Storage, process_media_file
from app.observability.logging import get_logger

logger = get_logger(__name__)


def build_storage(ctx: BotContext) -> ObjectStorage | None:
    settings = ctx.settings
    if not settings.media_download_enabled:
        return None
    if not settings.s3_access_key or not settings.s3_secret_key:
        return None
    return S3Storage(settings.s3_endpoint_url, settings.s3_access_key, settings.s3_secret_key)


async def run_media_once(ctx: BotContext, storage: ObjectStorage | None) -> int:
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
                bucket=ctx.settings.s3_bucket_media,
                max_download_bytes=ctx.settings.max_download_bytes,
            )
            # Duplicate detection by content hash.
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
            await repo.update_status(
                media.id,
                result.status,
                sha256=result.sha256,
                storage_bucket=ctx.settings.s3_bucket_media if result.storage_key else None,
                storage_key=result.storage_key,
                error=result.error,
            )
            handled += 1
    return handled
