"""Per-(chat, user) locking.

Two layers:

* In-process ``asyncio.Lock`` map — serialises handler execution for the
  same conversation inside one process (double-click protection).
* Cross-process transaction lock — ``pg_advisory_xact_lock`` on PostgreSQL
  and ``sp_getapplock`` on Microsoft SQL Server. SQLite tests are a no-op.
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
    """Take a transaction-scoped lock for this (chat, user) pair."""
    name = session.get_bind().dialect.name
    key = f"{chat_id}:{user_id}"
    if name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": key})
        return
    if name == "mssql":
        # Resource names are limited to 255 characters. Timeout -1 waits
        # for the lock, matching PostgreSQL advisory-lock blocking.
        await session.execute(
            text(
                "EXEC sp_getapplock @Resource=:key, @LockMode='Exclusive', "
                "@LockOwner='Transaction', @LockTimeout=-1"
            ),
            {"key": key[:255]},
        )
