"""Process-level stall detector for the receive loop.

The Cloud Agent VM (and any host that suspends) can freeze the asyncio
loop mid-getUpdates. After wall-clock jumps, sockets are dead but the
Python process is still "running". A daemon thread watches wall time so
we exit and let keep_alive start a clean polling loop.
"""

from __future__ import annotations

import os
import threading
import time

from app.observability.logging import get_logger

logger = get_logger(__name__)

DEFAULT_MAX_STALL_SECONDS = 90.0


class StallWatchdog:
    """Kill the process if the receive loop stops beating."""

    def __init__(
        self,
        max_stall_seconds: float = DEFAULT_MAX_STALL_SECONDS,
        check_every: float = 15.0,
        *,
        exit_process: bool = True,
    ) -> None:
        self.max_stall_seconds = max_stall_seconds
        self.check_every = check_every
        self.exit_process = exit_process
        self._last_wall = time.time()
        self._last_mono = time.monotonic()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def beat(self) -> None:
        """Call after each polling cycle that the receive loop completed."""
        self._last_wall = time.time()
        self._last_mono = time.monotonic()

    @property
    def age_seconds(self) -> float:
        """Largest of wall-clock and monotonic age. Wall clock catches VM sleep."""
        return max(time.time() - self._last_wall, time.monotonic() - self._last_mono)

    def stalled(self) -> bool:
        return self.age_seconds > self.max_stall_seconds

    def start(self) -> None:
        self.beat()
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="stall-watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self.check_every):
            if not self.stalled():
                continue
            logger.error("polling_stall_exit", age_seconds=round(self.age_seconds, 1))
            if self.exit_process:
                os._exit(2)
            return
