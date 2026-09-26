"""Outbox persistence: durable queue for notifications and failed sends."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OutboxItem


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(self, kind: str, target_chat_id: int, payload: dict[str, Any]) -> OutboxItem:
        item = OutboxItem(kind=kind, target_chat_id=target_chat_id, payload=payload)
        self._session.add(item)
        await self._session.flush()
        return item

    async def due_items(self, limit: int = 20) -> list[OutboxItem]:
        result = await self._session.execute(
            select(OutboxItem)
            .where(OutboxItem.status == "pending", OutboxItem.next_retry_at <= datetime.now(UTC))
            .order_by(OutboxItem.next_retry_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_sent(self, item_id: int) -> None:
        await self._session.execute(
            update(OutboxItem).where(OutboxItem.id == item_id).values(status="sent")
        )

    async def mark_retry(self, item_id: int, error: str, attempts: int, max_attempts: int) -> None:
        if attempts >= max_attempts:
            await self._session.execute(
                update(OutboxItem)
                .where(OutboxItem.id == item_id)
                .values(status="failed", attempts=attempts, last_error=error[:2000])
            )
            return
        backoff = timedelta(seconds=min(30 * (2 ** (attempts - 1)), 3600))
        await self._session.execute(
            update(OutboxItem)
            .where(OutboxItem.id == item_id)
            .values(
                attempts=attempts,
                last_error=error[:2000],
                next_retry_at=datetime.now(UTC) + backoff,
            )
        )

    async def pending_count(self) -> int:
        result = await self._session.scalar(
            select(func.count()).select_from(OutboxItem).where(OutboxItem.status == "pending")
        )
        return int(result or 0)
