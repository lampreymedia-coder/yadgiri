"""Outbox worker: retries failed/queued sends every 30 seconds.

Admin notifications are batched: when more than the configured threshold
is pending in the window, one aggregate message replaces the individual
ones so the admin is never spammed.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.bale.errors import BadRequest, BaleAPIError, Forbidden, NetworkError
from app.core.context import BotContext
from app.db.repositories.outbox import OutboxRepository
from app.i18n import fa
from app.observability import metrics
from app.observability.logging import get_logger

logger = get_logger(__name__)

_MAX_ATTEMPTS = 10
_BATCH_WINDOW_MINUTES = 5


@dataclass(frozen=True, slots=True)
class _OutboxJob:
    id: int
    kind: str
    target_chat_id: int
    text: str
    attempts: int


async def run_outbox_once(ctx: BotContext) -> int:
    """Process due outbox rows once; returns how many were handled."""
    async with ctx.db.session() as session:
        repo = OutboxRepository(session)
        items = await repo.due_items(limit=20)
        pending = await repo.pending_count()
        jobs = [
            _OutboxJob(
                id=item.id,
                kind=item.kind,
                target_chat_id=item.target_chat_id,
                text=str(item.payload.get("text", "")),
                attempts=item.attempts,
            )
            for item in items
        ]
    metrics.outbox_pending.set(pending)
    if not jobs:
        return 0

    handled = 0
    admin_notifies = [job for job in jobs if job.kind == "admin_notify"]
    others = [job for job in jobs if job.kind != "admin_notify"]

    if (
        len(admin_notifies) > ctx.settings.admin_notify_batch_threshold
        and ctx.settings.admin_chat_id is not None
    ):
        try:
            await ctx.api.send_message(
                ctx.settings.admin_chat_id,
                fa.admin_batch_submissions(len(admin_notifies), _BATCH_WINDOW_MINUTES),
            )
            async with ctx.db.session() as session:
                repo = OutboxRepository(session)
                for job in admin_notifies:
                    await repo.mark_sent(job.id)
                    handled += 1
        except (BaleAPIError, NetworkError) as exc:
            async with ctx.db.session() as session:
                repo = OutboxRepository(session)
                for job in admin_notifies:
                    await repo.mark_retry(job.id, str(exc), job.attempts + 1, _MAX_ATTEMPTS)
    else:
        others = admin_notifies + others

    for job in others:
        handled += await _send_job(ctx, job)
    return handled


async def _send_job(ctx: BotContext, job: _OutboxJob) -> int:
    try:
        await ctx.api.send_message(job.target_chat_id, job.text)
    except (Forbidden, BadRequest) as exc:
        logger.warning("outbox_permanent_failure", item_id=job.id, error=str(exc))
        async with ctx.db.session() as session:
            await OutboxRepository(session).mark_retry(
                job.id, str(exc), _MAX_ATTEMPTS, _MAX_ATTEMPTS
            )
        return 0
    except (BaleAPIError, NetworkError) as exc:
        async with ctx.db.session() as session:
            await OutboxRepository(session).mark_retry(
                job.id, str(exc), job.attempts + 1, _MAX_ATTEMPTS
            )
        return 0
    async with ctx.db.session() as session:
        await OutboxRepository(session).mark_sent(job.id)
    return 1
