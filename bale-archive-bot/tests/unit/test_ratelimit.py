"""Unit tests: token bucket and inbound spam guard."""

from __future__ import annotations

import asyncio
import time

from app.core.ratelimit import InboundSpamGuard, OutboundRateLimiter, TokenBucket


def test_token_bucket_capacity() -> None:
    bucket = TokenBucket(rate_per_second=10, capacity=3)
    assert bucket.try_acquire()
    assert bucket.try_acquire()
    assert bucket.try_acquire()
    assert not bucket.try_acquire()


def test_token_bucket_refills() -> None:
    bucket = TokenBucket(rate_per_second=1000, capacity=1)
    assert bucket.try_acquire()
    assert not bucket.try_acquire()
    time.sleep(0.01)
    assert bucket.try_acquire()


async def test_acquire_blocks_until_token() -> None:
    bucket = TokenBucket(rate_per_second=50, capacity=1)
    await bucket.acquire()
    started = time.monotonic()
    await bucket.acquire()
    elapsed = time.monotonic() - started
    assert elapsed >= 0.01


async def test_outbound_limiter_levels() -> None:
    limiter = OutboundRateLimiter(global_rps=1000, per_chat_per_sec=1000, per_group_per_min=60000)
    await asyncio.wait_for(limiter.acquire(chat_id=-1, is_group=True), timeout=1.0)
    await asyncio.wait_for(limiter.acquire(chat_id=5, is_group=False), timeout=1.0)
    await asyncio.wait_for(limiter.acquire(chat_id=None, is_group=False), timeout=1.0)


def test_spam_guard_limits_per_hour() -> None:
    guard = InboundSpamGuard(max_per_hour=3)
    assert guard.allow(1)
    assert guard.allow(1)
    assert guard.allow(1)
    assert not guard.allow(1)
    assert guard.count(1) == 3
    # A different user is unaffected.
    assert guard.allow(2)
