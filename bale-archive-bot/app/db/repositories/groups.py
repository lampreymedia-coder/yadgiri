"""Group persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Group


class GroupRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_bale_id(self, bale_chat_id: int) -> Group | None:
        result = await self._session.execute(
            select(Group).where(Group.bale_chat_id == bale_chat_id)
        )
        return result.scalar_one_or_none()

    async def upsert(self, bale_chat_id: int, title: str | None, chat_type: str) -> Group:
        values: dict[str, Any] = {
            "bale_chat_id": bale_chat_id,
            "title": title,
            "chat_type": chat_type,
            "is_active": True,
            "bot_can_delete": False,
            "settings": {},
            "joined_at": datetime.now(UTC),
        }
        dialect = self._session.get_bind().dialect.name
        insert = pg_insert if dialect == "postgresql" else sqlite_insert
        stmt = insert(Group).values(**values)
        # Concurrent group messages share one chat_id; ignore the losing insert.
        stmt = stmt.on_conflict_do_update(
            index_elements=["bale_chat_id"],
            set_={"title": title} if title else {"chat_type": chat_type},
        )
        await self._session.execute(stmt)
        group = await self.get_by_bale_id(bale_chat_id)
        if group is None:
            msg = f"group upsert failed for {bale_chat_id}"
            raise RuntimeError(msg)
        return group

    async def list_active(self) -> list[Group]:
        result = await self._session.execute(select(Group).where(Group.is_active.is_(True)))
        return list(result.scalars().all())

    async def set_can_delete(self, group_id: int, can_delete: bool) -> None:
        await self._session.execute(
            update(Group).where(Group.id == group_id).values(bot_can_delete=can_delete)
        )

    async def set_active(self, group_id: int, is_active: bool) -> None:
        await self._session.execute(
            update(Group).where(Group.id == group_id).values(is_active=is_active)
        )

    async def archive_chat_id_for_slug(self, slug: str) -> int | None:
        """Find the private archive group bound to a hashtag slug."""
        result = await self._session.execute(select(Group).where(Group.is_active.is_(True)))
        for group in result.scalars().all():
            settings = group.settings if isinstance(group.settings, dict) else {}
            if settings.get("role") == "archive" and settings.get("tag_slug") == slug:
                return group.bale_chat_id
        return None
