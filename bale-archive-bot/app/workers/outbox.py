"""Outbox worker: retries failed/queued sends every 30 seconds.

Admin notifications are batched: when more than the configured threshold
is pending in the window, one aggregate message replaces the individual
ones so the admin is never spammed.
"""

from __future__ import annotations

from app.bale.errors import BadRequest, BaleAPIError, Forbidden, NetworkError
from app.core.context import BotContext
from app.db.models import OutboxItem
from app.db.repositories.outbox import OutboxRepository
from app.i18n import fa
from app.observability import metrics
from app.observability.logging import get_logger

logger = get_logger(__name__)

_MAX_ATTEMPTS = 10
_BATCH_WINDOW_MINUTES = 5


async def run_outbox_once(ctx: BotContext) -> int:
    """Process due outbox rows once; returns how many were handled."""
    handled = 0
    async with ctx.db.session() as session:
        repo = OutboxRepository(session)
        items = await repo.due_items(limit=20)
        metrics.outbox_pending.set(await repo.pending_count())
        if not items:
            return 0

        admin_notifies = [i for i in items if i.kind == "admin_notify"]
        others = [i for i in items if i.kind != "admin_notify"]

        # Batch admin notifications above the threshold.
        if (
            len(admin_notifies) > ctx.settings.admin_notify_batch_threshold
            and ctx.settings.admin_chat_id is not None
        ):
            try:
                await ctx.api.send_message(
                    ctx.settings.admin_chat_id,
                    fa.admin_batch_submissions(len(admin_notifies), _BATCH_WINDOW_MINUTES),
                )
                for item in admin_notifies:
                    await repo.mark_sent(item.id)
                    handled += 1
            except (BaleAPIError, NetworkError) as exc:
                for item in admin_notifies:
                    await repo.mark_retry(item.id, str(exc), item.attempts + 1, _MAX_ATTEMPTS)
        else:
            others = admin_notifies + others

        for item in others:
            handled += await _send_item(ctx, repo, item)
    return handled


async def _send_item(ctx: BotContext, repo: OutboxRepository, item: OutboxItem) -> int:
    text = str(item.payload.get("text", ""))
    try:
        await ctx.api.send_message(item.target_chat_id, text)
        await repo.mark_sent(item.id)
    except (Forbidden, BadRequest) as exc:
        # Permanent failure: don't retry.
        logger.warning("outbox_permanent_failure", item_id=item.id, error=str(exc))
        await repo.mark_retry(item.id, str(exc), _MAX_ATTEMPTS, _MAX_ATTEMPTS)
        return 0
    except (BaleAPIError, NetworkError) as exc:
        await repo.mark_retry(item.id, str(exc), item.attempts + 1, _MAX_ATTEMPTS)
        return 0
    return 1
