"""Health endpoint payload builder."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import text

from app.core.context import BotContext
from app.core.receive import poll_receive_stale
from app.observability.logging import get_logger

logger = get_logger(__name__)


async def health_payload(ctx: BotContext) -> tuple[bool, dict[str, Any]]:
    """Return (healthy, payload) for /healthz."""
    db_ok = True
    try:
        async with ctx.db.session() as session:
            await session.execute(text("SELECT 1"))
    except (ConnectionError, OSError, TimeoutError):
        db_ok = False
    except Exception as exc:
        if type(exc).__module__.startswith(("asyncpg", "sqlalchemy", "aiosqlite")):
            db_ok = False
        else:
            raise

    now = time.time()
    poll_age = (now - ctx.last_poll_at) if ctx.last_poll_at else None
    receive_stale = poll_receive_stale(ctx.last_poll_at or None, now)
    degraded = ctx.db.breaker.is_open
    healthy = db_ok and not degraded and not receive_stale
    return healthy, {
        "status": "ok" if healthy else "degraded",
        "database": "up" if db_ok else "down",
        "circuit_breaker": "open" if degraded else "closed",
        "capabilities_probed": ctx.caps.probed,
        "safety_polling": ctx.safety_polling,
        "webhook_pending": ctx.webhook_pending,
        "last_poll_age_seconds": None if poll_age is None else round(poll_age, 1),
        "receive_stale": receive_stale,
    }
