"""Process-wide runtime context shared by all handlers and workers."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field

from app.bale.methods import BaleAPI
from app.config import Settings
from app.core.admins import AdminStore
from app.core.notify import AdminNotifier
from app.core.ratelimit import InboundSpamGuard
from app.core.wizard_store import WizardStore
from app.db.session import Database
from app.domain.video_compress import CompressionLog


class KeyedLocks:
    """Bounded map of asyncio locks (per user, per chat …)."""

    def __init__(self, max_keys: int = 4096) -> None:
        self._locks: OrderedDict[object, asyncio.Lock] = OrderedDict()
        self._max_keys = max_keys

    def get(self, key: object) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
            if len(self._locks) > self._max_keys:
                for old_key in list(self._locks.keys()):
                    if not self._locks[old_key].locked():
                        del self._locks[old_key]
                        break
        else:
            self._locks.move_to_end(key)
        return lock


@dataclass
class BotContext:
    settings: Settings
    api: BaleAPI
    db: Database
    admins: AdminStore
    wizards: WizardStore = field(default_factory=WizardStore)
    user_locks: KeyedLocks = field(default_factory=KeyedLocks)
    spam_guard: InboundSpamGuard = field(init=False)
    notifier: AdminNotifier = field(init=False)
    compression_log: CompressionLog = field(init=False)
    # Only one ffmpeg job at a time (2 GB RAM server).
    compress_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    bot_username: str = ""
    bot_user_id: int = 0
    background: set[asyncio.Task[None]] = field(default_factory=set)
    # Panel questions waiting for a typed answer: user id → (kind, arg, started).
    pending_input: dict[int, tuple[str, str, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.spam_guard = InboundSpamGuard(self.settings.max_submissions_per_user_per_hour)
        self.notifier = AdminNotifier(self.api, self.admins)
        self.compression_log = CompressionLog(self.settings.data_path / "compression.json")

    @property
    def archive_chat_id(self) -> int | None:
        return self.settings.archive_chat_id

    def is_admin(self, user_id: int) -> bool:
        return self.admins.is_admin(user_id)

    def spawn(self, coro: object) -> asyncio.Task[None]:
        """Run work in the background and keep a reference until it finishes."""
        task: asyncio.Task[None] = asyncio.create_task(coro)  # type: ignore[arg-type]
        self.background.add(task)
        task.add_done_callback(self.background.discard)
        return task
