"""Album detection via a time-window buffer.

Bale messages carry no reliable ``media_group_id``, so consecutive media
messages from the same user in the same chat arriving within
``ALBUM_WINDOW_MS`` are treated as one submission. When an undocumented
``media_group_id`` does appear (probed at runtime), it takes priority.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from app.bale.models import Message
from app.observability.logging import get_logger

logger = get_logger(__name__)

FlushCallback = Callable[[list[Message]], Awaitable[None]]


def _has_media(message: Message) -> bool:
    return any(
        (
            message.photo,
            message.video,
            message.animation,
            message.document,
            message.audio,
            message.voice,
        )
    )


class AlbumBuffer:
    """Buffers media messages per (chat, user) and flushes after the window."""

    def __init__(self, flush: FlushCallback, window_ms: int = 2500) -> None:
        self._flush = flush
        self._window = window_ms / 1000.0
        self._pending: dict[tuple[int, int, str], list[Message]] = {}
        self._timers: dict[tuple[int, int, str], asyncio.Task[None]] = {}

    def _key(self, message: Message) -> tuple[int, int, str]:
        user_id = message.from_user.id if message.from_user else 0
        group_key = message.media_group_id or ""
        return (message.chat.id, user_id, group_key)

    async def add(self, message: Message) -> None:
        """Buffer a media message; non-media messages flush immediately."""
        if not _has_media(message):
            await self._flush([message])
            return
        key = self._key(message)
        self._pending.setdefault(key, []).append(message)
        existing = self._timers.get(key)
        if existing is not None:
            existing.cancel()
        self._timers[key] = asyncio.create_task(self._delayed_flush(key))

    async def _delayed_flush(self, key: tuple[int, int, str]) -> None:
        try:
            await asyncio.sleep(self._window)
        except asyncio.CancelledError:
            return
        messages = self._pending.pop(key, [])
        self._timers.pop(key, None)
        if messages:
            try:
                await self._flush(messages)
            except Exception:
                logger.exception("album_flush_failed", count=len(messages))

    async def drain(self) -> None:
        """Flush everything immediately (graceful shutdown)."""
        for timer in list(self._timers.values()):
            timer.cancel()
        self._timers.clear()
        pending = list(self._pending.items())
        self._pending.clear()
        for _, messages in pending:
            if messages:
                try:
                    await self._flush(messages)
                except Exception:
                    logger.exception("album_drain_flush_failed", count=len(messages))
