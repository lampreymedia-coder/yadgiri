"""Duplicate-update protection built on the ``processed_updates`` table."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.misc import ProcessedUpdateRepository
from app.observability import metrics
from app.observability.logging import get_logger

logger = get_logger(__name__)


async def claim_update(session: AsyncSession, update_id: int) -> bool:
    """Atomically claim an update_id; False when it was already processed."""
    repo = ProcessedUpdateRepository(session)
    claimed = await repo.try_mark(update_id)
    if not claimed:
        metrics.updates_duplicated.inc()
        logger.info("update_duplicate_skipped", update_id=update_id)
    return claimed


async def purge_old_records(session: AsyncSession, days: int = 7) -> int:
    """Nightly cleanup of processed_updates rows older than ``days``."""
    repo = ProcessedUpdateRepository(session)
    removed = await repo.purge_older_than(days)
    if removed:
        logger.info("processed_updates_purged", removed=removed, days=days)
    return removed
