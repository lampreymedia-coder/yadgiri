"""Cross-platform stop-signal registration for asyncio apps."""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Callable


def install_stop_signals(
    loop: asyncio.AbstractEventLoop,
    on_stop: Callable[[], None],
) -> None:
    """Register SIGTERM/SIGINT so they invoke ``on_stop``.

    ``asyncio.loop.add_signal_handler`` raises ``NotImplementedError`` on
    Windows (ProactorEventLoop). Fall back to ``signal.signal`` and schedule
    ``on_stop`` onto the event loop from the signal handler thread.
    """

    def _schedule_stop(*_args: object) -> None:
        loop.call_soon_threadsafe(on_stop)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, on_stop)
        except (NotImplementedError, RuntimeError, AttributeError):
            signal.signal(sig, _schedule_stop)
