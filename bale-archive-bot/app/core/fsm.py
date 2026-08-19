"""Wizard finite-state machine with a back-stack.

State is never kept in process memory: it lives in Redis when available
and falls back to the ``conversation_states`` table automatically, so a
restart mid-wizard loses nothing (spec sections 11-6 and the Redis
fallback requirement).
"""

from __future__ import annotations

import enum
import json
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
        if self.state is not WizardState.IDLE:
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
        if row.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC):
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
        else:
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


class RedisLike(Protocol):
    """Minimal async Redis interface used by :class:`RedisStateStore`."""

    async def get(self, key: str) -> bytes | str | None: ...

    async def set(self, key: str, value: str, ex: int | None = None) -> Any: ...

    async def delete(self, *keys: str) -> Any: ...


class RedisStateStore:
    """Conversation storage in Redis (preferred when configured & reachable)."""

    def __init__(self, redis: RedisLike, prefix: str = "conv") -> None:
        self._redis = redis
        self._prefix = prefix

    def _key(self, chat_id: int, user_id: int) -> str:
        return f"{self._prefix}:{chat_id}:{user_id}"

    async def load(self, chat_id: int, user_id: int) -> Conversation | None:
        raw = await self._redis.get(self._key(chat_id, user_id))
        if raw is None:
            return None
        data = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
        return Conversation(
            chat_id=chat_id,
            user_id=user_id,
            state=WizardState(data["state"]),
            history=list(data.get("history", [])),
            payload=dict(data.get("payload", {})),
        )

    async def save(self, conversation: Conversation, ttl_minutes: int) -> None:
        data = json.dumps(
            {
                "state": conversation.state.value,
                "history": conversation.history,
                "payload": conversation.payload,
            },
            ensure_ascii=False,
        )
        await self._redis.set(
            self._key(conversation.chat_id, conversation.user_id),
            data,
            ex=ttl_minutes * 60,
        )

    async def clear(self, chat_id: int, user_id: int) -> None:
        await self._redis.delete(self._key(chat_id, user_id))


class FallbackStateStore:
    """Try Redis first; on any Redis failure fall back to Postgres transparently."""

    def __init__(self, redis_store: RedisStateStore | None, pg_store: PostgresStateStore) -> None:
        self._redis = redis_store
        self._pg = pg_store

    async def load(self, chat_id: int, user_id: int) -> Conversation | None:
        if self._redis is not None:
            try:
                loaded = await self._redis.load(chat_id, user_id)
            except (ConnectionError, OSError, TimeoutError) as exc:
                logger.warning("redis_load_failed_fallback_pg", error=str(exc))
            else:
                if loaded is not None:
                    return loaded
        return await self._pg.load(chat_id, user_id)

    async def save(self, conversation: Conversation, ttl_minutes: int) -> None:
        if self._redis is not None:
            try:
                await self._redis.save(conversation, ttl_minutes)
            except (ConnectionError, OSError, TimeoutError) as exc:
                logger.warning("redis_save_failed_fallback_pg", error=str(exc))
        # Always persist to Postgres too: survives Redis eviction/restart.
        await self._pg.save(conversation, ttl_minutes)

    async def clear(self, chat_id: int, user_id: int) -> None:
        if self._redis is not None:
            try:
                await self._redis.clear(chat_id, user_id)
            except (ConnectionError, OSError, TimeoutError) as exc:
                logger.warning("redis_clear_failed", error=str(exc))
        await self._pg.clear(chat_id, user_id)
