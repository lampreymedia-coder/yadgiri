"""Wizard finite-state machine with a back-stack.

State is never kept in process memory: it lives in the
``conversation_states`` Postgres table so a restart mid-wizard loses nothing.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ConversationState
from app.observability.logging import get_logger

logger = get_logger(__name__)


class WizardState(enum.StrEnum):
    IDLE = "idle"
    AWAITING_DECISION = "awaiting_decision"
    AWAITING_IMAGE_KEEP = "awaiting_image_keep"
    AWAITING_TAG_COUNT = "awaiting_tag_count"
    AWAITING_TAGS = "awaiting_tags"
    AWAITING_CONFIRM = "awaiting_confirm"
    AWAITING_NOTE = "awaiting_note"
    ADMIN_INPUT = "admin_input"


@dataclass
class Conversation:
    """A user's wizard conversation: current state, back-stack and payload."""

    chat_id: int
    user_id: int
    state: WizardState = WizardState.IDLE
    history: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)

    def transition(self, new_state: WizardState) -> None:
        """Move forward, pushing the current state onto the back-stack."""
        if self.state is WizardState.IDLE:
            self.state = new_state
            return
        self.history.append(self.state.value)
        self.state = new_state

    def go_back(self) -> WizardState | None:
        """Pop the back-stack. Selections in ``payload`` are preserved."""
        if not self.history:
            return None
        self.state = WizardState(self.history.pop())
        return self.state

    @property
    def can_go_back(self) -> bool:
        return bool(self.history)


class StateStore(Protocol):
    """Persistence interface for conversations."""

    async def load(self, chat_id: int, user_id: int) -> Conversation | None: ...

    async def save(self, conversation: Conversation, ttl_minutes: int) -> None: ...

    async def clear(self, chat_id: int, user_id: int) -> None: ...


class PostgresStateStore:
    """Conversation storage in the conversation_states table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load(self, chat_id: int, user_id: int) -> Conversation | None:
        row = await self._session.get(ConversationState, (chat_id, user_id))
        if row is None:
            return None
        expires = row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires <= datetime.now(UTC):
            await self.clear(chat_id, user_id)
            return None
        return Conversation(
            chat_id=chat_id,
            user_id=user_id,
            state=WizardState(row.state),
            history=list(row.history),
            payload=dict(row.payload),
        )

    async def save(self, conversation: Conversation, ttl_minutes: int) -> None:
        expires = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
        row = await self._session.get(
            ConversationState, (conversation.chat_id, conversation.user_id)
        )
        if row is None:
            row = ConversationState(
                chat_id=conversation.chat_id,
                user_id=conversation.user_id,
                state=conversation.state.value,
                history=list(conversation.history),
                payload=dict(conversation.payload),
                expires_at=expires,
            )
            self._session.add(row)
            return
        row.state = conversation.state.value
        row.history = list(conversation.history)
        row.payload = dict(conversation.payload)
        row.expires_at = expires

    async def clear(self, chat_id: int, user_id: int) -> None:
        await self._session.execute(
            delete(ConversationState).where(
                ConversationState.chat_id == chat_id,
                ConversationState.user_id == user_id,
            )
        )
