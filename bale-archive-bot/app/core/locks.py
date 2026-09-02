"""Per-(chat, user) locking.

Two layers:

* In-process ``asyncio.Lock`` map — serialises handler execution for the
  same conversation inside one process (double-click protection).
* PostgreSQL advisory transaction lock — protects wizard state transitions
  across processes; a no-op on non-Postgres dialects (tests on SQLite).
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ConversationLocks:
    """Bounded map of asyncio locks keyed by (chat_id, user_id)."""

    def __init__(self, max_keys: int = 4096) -> None:
        self._locks: OrderedDict[tuple[int, int], asyncio.Lock] = OrderedDict()
        self._max_keys = max_keys

    def get(self, chat_id: int, user_id: int) -> asyncio.Lock:
        key = (chat_id, user_id)
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
            if len(self._locks) > self._max_keys:
                # Evict the oldest unlocked entry.
                for old_key in list(self._locks.keys()):
                    if not self._locks[old_key].locked():
                        del self._locks[old_key]
                        break
                    if len(self._locks) <= self._max_keys:
                        break
        else:
            self._locks.move_to_end(key)
        return lock


async def advisory_xact_lock(session: AsyncSession, chat_id: int, user_id: int) -> None:
    """Take ``pg_advisory_xact_lock(hashtext(:key))`` inside the current transaction."""
    bind = session.bind
    if bind is None or bind.dialect.name != "postgresql":
        return
    key = f"{chat_id}:{user_id}"
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": key})
