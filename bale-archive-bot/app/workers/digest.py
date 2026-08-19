"""Weekly digest: Thursdays 20:00 Tehran time, sent to the admin chat."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.context import BotContext
from app.db.repositories.outbox import OutboxRepository
from app.domain import reports
from app.i18n import fa
from app.observability.logging import get_logger

logger = get_logger(__name__)


async def run_weekly_digest(ctx: BotContext) -> None:
    """Build the weekly report and enqueue it via the outbox (durable)."""
    if ctx.settings.admin_chat_id is None:
        return
    now = datetime.now(UTC)
    week_ago = now - timedelta(days=7)
    async with ctx.db.session() as session:
        service = reports.ReportService(session)
        overall = await service.overall(week_ago, now)
        tag_stats = await service.top_tags(week_ago, now)
        user_stats = await service.top_users(week_ago, now, limit=5)

        tag_lines = [
            fa.bar_line(t.title_fa, t.items, t.share_pct, reports.text_bar(t.share_pct / 100.0))
            for t in tag_stats
            if t.items > 0
        ]
        user_lines = [
            fa.ranked_user_line(i, u.display_name or u.username or str(u.bale_user_id), u.items)
            for i, u in enumerate(user_stats, start=1)
        ]
        body = fa.stats_report(
            range_text=fa.range_label("week"),
            total=overall.total,
            contributors=overall.contributors,
            total_bytes=overall.total_bytes,
            tag_lines=tag_lines,
            type_line="",
            top_user_lines=user_lines,
        )
        text = f"{fa.DIGEST_HEADER}\n\n{body}"
        outbox = OutboxRepository(session)
        await outbox.enqueue("admin_notify", ctx.settings.admin_chat_id, {"text": text})
        logger.info("weekly_digest_enqueued")
