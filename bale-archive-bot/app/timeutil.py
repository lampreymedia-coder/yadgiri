"""Tehran wall-clock helpers. The database stores Tehran time, never UTC."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

TEHRAN = ZoneInfo("Asia/Tehran")


def tehran_now() -> datetime:
    """Naive Tehran datetime for DATETIME columns."""
    return datetime.now(TEHRAN).replace(tzinfo=None, microsecond=0)


def tehran_from_unix(timestamp: int | None) -> datetime:
    """Convert a Bale message ``date`` (unix seconds) to naive Tehran time."""
    if not timestamp:
        return tehran_now()
    return datetime.fromtimestamp(timestamp, TEHRAN).replace(tzinfo=None, microsecond=0)
