"""/healthz payload: database reachable and polling alive."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import text

from app.core.context import BotContext


async def health_payload(ctx: BotContext, last_poll_at: float) -> tuple[bool, dict[str, Any]]:
    db_ok = True
    try:
        async with ctx.db.tx() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 — reported, not raised
        db_ok = False
    poll_age = time.time() - last_poll_at if last_poll_at else None
    polling_ok = poll_age is not None and poll_age < 120
    payload = {
        "database": "ok" if db_ok else "down",
        "polling_age_seconds": round(poll_age, 1) if poll_age is not None else None,
        "open_wizards": len(ctx.wizards),
    }
    return db_ok and polling_ok, payload
