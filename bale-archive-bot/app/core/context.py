"""Process-wide runtime context shared by all handlers and workers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.bale.capabilities import Capabilities
from app.bale.methods import BaleAPI
from app.config import Settings
from app.core.fsm import PostgresStateStore
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
    error_throttle: dict[str, float] = field(default_factory=dict)
    archive_chat_id: int | None = None
    admin_notify_chat_id: int | None = None
    runtime_admin_ids: set[int] = field(default_factory=set)
    webhook_pending: int | None = None
    last_webhook_at: float = 0.0
    last_poll_at: float = 0.0
    safety_polling: bool = False

    def __post_init__(self) -> None:
        self.spam_guard = InboundSpamGuard(self.settings.max_submissions_per_user_per_hour)
        if self.archive_chat_id is None:
            self.archive_chat_id = self.settings.archive_chat_id
        if self.admin_notify_chat_id is None:
            self.admin_notify_chat_id = self.settings.admin_chat_id
        self.runtime_admin_ids.update(self.settings.admin_user_ids)

    def state_store(self, session: AsyncSession) -> PostgresStateStore:
        return PostgresStateStore(session)

    def is_runtime_admin(self, bale_user_id: int) -> bool:
        return bale_user_id in self.runtime_admin_ids or self.settings.is_admin_user(bale_user_id)

    def submission_service(self, session: AsyncSession) -> Any:
        from app.domain.submission import SubmissionService

        return SubmissionService(
            session,
            self.api,
            self.settings,
            archive_chat_id=self.archive_chat_id,
            admin_chat_id=self.admin_notify_chat_id,
            extra_admin_ids=set(self.runtime_admin_ids),
        )
