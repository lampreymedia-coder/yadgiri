"""Daily report to all admins at 21:00 Tehran, once per day.

The date of the last report is kept in ``<DATA_DIR>/digest_state.json`` so a
restart after 21:00 does not send it twice. The check piggybacks on the
existing 30-second sweeper; no extra loop.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from app.core.context import BotContext
from app.domain.reports import PostFilter, build_report, today_range
from app.i18n import fa
from app.observability.logging import get_logger
from app.timeutil import tehran_now

logger = get_logger(__name__)

DIGEST_HOUR = 21


class DigestState:
    def __init__(self, path: Path) -> None:
        self.path = path

    def last_date(self) -> str | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError, OSError):
            return None
        value = data.get("last_sent_date") if isinstance(data, dict) else None
        return str(value) if value else None

    def mark(self, day: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"last_sent_date": day}), encoding="utf-8")
        os.replace(tmp, self.path)


async def maybe_send_daily_digest(ctx: BotContext, now: datetime | None = None) -> bool:
    now = now or tehran_now()
    if now.hour < DIGEST_HOUR:
        return False
    state = DigestState(ctx.settings.data_path / "digest_state.json")
    day = now.date().isoformat()
    if state.last_date() == day:
        return False
    start, end = today_range(now)
    async with ctx.db.tx() as conn:
        report = await build_report(conn, flt=PostFilter(start=start, end=end))
    # Mark first: a send error must never turn into a repeat every 30 seconds.
    state.mark(day)
    delivered = await ctx.notifier.send_all(fa.daily_digest(now, report))
    logger.info("daily_digest_sent", day=day, delivered=delivered, posts=report.total_posts)
    return True
