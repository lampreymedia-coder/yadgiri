"""Token-bucket rate limiting.

Outbound: three levels (global RPS, per-chat per-second, per-group per-minute).
Inbound: per-user submission counter used as anti-spam.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict


class TokenBucket:
    """Classic token bucket; ``acquire`` sleeps until a token is available."""

    def __init__(self, rate_per_second: float, capacity: float | None = None) -> None:
        if rate_per_second <= 0:
            msg = "rate must be positive"
            raise ValueError(msg)
        self.rate = rate_per_second
        self.capacity = capacity if capacity is not None else max(1.0, rate_per_second)
        self._tokens = self.capacity
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        self._tokens = min(self.capacity, self._tokens + (now - self._updated) * self.rate)
        self._updated = now

    def try_acquire(self, tokens: float = 1.0) -> bool:
        """Non-blocking acquire; True when a token was consumed."""
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    async def acquire(self, tokens: float = 1.0) -> None:
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                needed = (tokens - self._tokens) / self.rate
            await asyncio.sleep(min(needed, 1.0))


class _BucketMap:
    """LRU map of per-key buckets to bound memory."""

    def __init__(self, rate: float, capacity: float | None, max_keys: int = 4096) -> None:
        self._rate = rate
        self._capacity = capacity
        self._max_keys = max_keys
        self._buckets: OrderedDict[int, TokenBucket] = OrderedDict()

    def get(self, key: int) -> TokenBucket:
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = TokenBucket(self._rate, self._capacity)
            self._buckets[key] = bucket
            if len(self._buckets) > self._max_keys:
                self._buckets.popitem(last=False)
        else:
            self._buckets.move_to_end(key)
        return bucket


class OutboundRateLimiter:
    """Global + per-chat + per-group token buckets (spec section 11-3)."""

    def __init__(
        self,
        global_rps: float = 20.0,
        per_chat_per_sec: float = 1.0,
        per_group_per_min: float = 20.0,
    ) -> None:
        self._global = TokenBucket(global_rps)
        self._per_chat = _BucketMap(per_chat_per_sec, max(1.0, per_chat_per_sec))
        self._per_group = _BucketMap(per_group_per_min / 60.0, max(1.0, per_group_per_min / 60.0))

    async def acquire(self, chat_id: int | None, is_group: bool) -> None:
        await self._global.acquire()
        if chat_id is not None:
            await self._per_chat.get(chat_id).acquire()
            if is_group:
                await self._per_group.get(chat_id).acquire()


class InboundSpamGuard:
    """Sliding-window counter for submissions per user per hour."""

    def __init__(self, max_per_hour: int = 60) -> None:
        self._max = max_per_hour
        self._events: dict[int, list[float]] = {}

    def allow(self, user_id: int) -> bool:
        now = time.monotonic()
        window_start = now - 3600.0
        events = [t for t in self._events.get(user_id, []) if t >= window_start]
        if len(events) >= self._max:
            self._events[user_id] = events
            return False
        events.append(now)
        self._events[user_id] = events
        return True

    def count(self, user_id: int) -> int:
        now = time.monotonic()
        return len([t for t in self._events.get(user_id, []) if t >= now - 3600.0])
