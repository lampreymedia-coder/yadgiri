"""Process-wide runtime context shared by all handlers and workers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.bale.capabilities import Capabilities
from app.bale.methods import BaleAPI
from app.config import Settings
from app.core.fsm import FallbackStateStore, PostgresStateStore, RedisStateStore
from app.core.locks import ConversationLocks
from app.core.ratelimit import InboundSpamGuard
from app.db.session import Database


@dataclass
class BotContext:
    settings: Settings
    api: BaleAPI
    db: Database
    caps: Capabilities
    locks: ConversationLocks = field(default_factory=ConversationLocks)
    spam_guard: InboundSpamGuard = field(init=False)
    bot_username: str = ""
    bot_user_id: int = 0
    redis: Any | None = None
    error_throttle: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.spam_guard = InboundSpamGuard(self.settings.max_submissions_per_user_per_hour)

    def state_store(self, session: AsyncSession) -> FallbackStateStore:
        redis_store = RedisStateStore(self.redis) if self.redis is not None else None
        return FallbackStateStore(redis_store, PostgresStateStore(session))
