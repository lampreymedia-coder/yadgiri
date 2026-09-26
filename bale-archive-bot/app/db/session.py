"""Async MySQL engine for the existing ``Bale_Archive`` database.

This module only connects. It never creates, alters or drops anything:
the bot's MySQL user is limited to SELECT/INSERT/UPDATE/DELETE on purpose.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine


def ensure_utf8mb4(url: str) -> str:
    """Add ``charset=utf8mb4`` when the URL does not name a charset."""
    parsed = make_url(url)
    if "charset" in parsed.query:
        return url
    return parsed.update_query_dict({"charset": "utf8mb4"}).render_as_string(hide_password=False)


def database_name(url: str) -> str:
    return make_url(url).database or ""


class Database:
    """Owns the connection pool. ``tx()`` is one transaction: all or nothing."""

    def __init__(self, url: str, pool_size: int = 5, max_overflow: int = 5) -> None:
        self.url = ensure_utf8mb4(url)
        self.engine: AsyncEngine = create_async_engine(
            self.url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,
            pool_recycle=1800,
        )

    @asynccontextmanager
    async def tx(self) -> AsyncIterator[AsyncConnection]:
        """Commit on success, roll back on any exception."""
        async with self.engine.begin() as conn:
            yield conn

    async def dispose(self) -> None:
        await self.engine.dispose()
