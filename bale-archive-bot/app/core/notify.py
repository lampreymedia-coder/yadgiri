"""Private-chat notices to every admin, batched when saves come in bursts.

Up to ``threshold`` saves inside ``window`` seconds are announced one by one;
after that the short lines are collected and sent as one summary when the
window has passed (the existing 30-second sweeper calls :meth:`flush_due`).
A failed send is logged as ``admin_notify_failed`` and never breaks a save.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

from app.bale.errors import BaleAPIError, NetworkError
from app.bale.methods import BaleAPI
from app.core.admins import AdminStore
from app.i18n import fa
from app.observability.logging import get_logger

logger = get_logger(__name__)


class AdminNotifier:
    def __init__(
        self,
        api: BaleAPI,
        admins: AdminStore,
        window_seconds: float = 300.0,
        threshold: int = 5,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.api = api
        self.admins = admins
        self.window = window_seconds
        self.threshold = threshold
        self.clock = clock
        self._saves: deque[float] = deque()
        self._pending: list[str] = []
        self._flush_at: float | None = None

    async def send_all(self, text: str) -> int:
        """Send to every admin; returns how many sends succeeded."""
        delivered = 0
        for admin_id in sorted(self.admins.all):
            try:
                await self.api.send_message(admin_id, text)
                delivered += 1
            except (BaleAPIError, NetworkError) as exc:
                reason = str(exc)
                if "403" in reason or "blocked" in reason.lower() or "not found" in reason.lower():
                    reason += " (مدیر احتمالاً ربات را در پیوی /start نکرده است)"
                logger.warning("admin_notify_failed", admin_id=admin_id, reason=reason)
        return delivered

    async def post_saved(self, full_text: str, short_line: str) -> None:
        now = self.clock()
        while self._saves and now - self._saves[0] > self.window:
            self._saves.popleft()
        self._saves.append(now)
        if len(self._saves) <= self.threshold and not self._pending:
            await self.send_all(full_text)
            return
        if not self._pending:
            self._flush_at = now + self.window
        self._pending.append(short_line)

    async def flush_due(self, force: bool = False) -> None:
        if not self._pending or self._flush_at is None:
            return
        if not force and self.clock() < self._flush_at:
            return
        lines, self._pending, self._flush_at = self._pending, [], None
        await self.send_all(fa.admin_saved_batch(lines))
