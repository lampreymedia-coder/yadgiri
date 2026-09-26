"""Unit tests: receive-loop stall watchdog."""

from __future__ import annotations

import time

from app.core.watchdog import StallWatchdog


def test_fresh_beat_is_not_stalled() -> None:
    dog = StallWatchdog(max_stall_seconds=90, exit_process=False)
    dog.beat()
    assert dog.stalled() is False


def test_wall_clock_jump_after_host_sleep_is_stalled() -> None:
    dog = StallWatchdog(max_stall_seconds=90, exit_process=False)
    dog.beat()
    # VM sleep advances wall clock but often not monotonic.
    dog._last_wall = time.time() - 12 * 3600
    dog._last_mono = time.monotonic()
    assert dog.stalled() is True
    assert dog.age_seconds > 90
