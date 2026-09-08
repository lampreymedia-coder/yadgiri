"""Group persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dialect import dialect_name, supports_on_conflict
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
        if supports_on_conflict(self._session):
            return await self._upsert_on_conflict(bale_chat_id, title, chat_type)
        return await self._upsert_portable(bale_chat_id, title, chat_type)

    async def _upsert_on_conflict(
        self, bale_chat_id: int, title: str | None, chat_type: str
    ) -> Group:
        values: dict[str, Any] = {
            "bale_chat_id": bale_chat_id,
            "title": title,
            "chat_type": chat_type,
            "is_active": True,
            "bot_can_delete": False,
            "settings": {},
            "joined_at": datetime.now(UTC),
        }
        insert = pg_insert if dialect_name(self._session) == "postgresql" else sqlite_insert
        stmt = insert(Group).values(**values)
        # Concurrent group messages share one chat_id; ignore the losing insert.
        stmt = stmt.on_conflict_do_update(
            index_elements=["bale_chat_id"],
            set_={"title": title} if title else {"chat_type": chat_type},
        )
        await self._session.execute(stmt)
        return await self._require_group(bale_chat_id)

    async def _upsert_portable(self, bale_chat_id: int, title: str | None, chat_type: str) -> Group:
        """SELECT + UPDATE/INSERT for engines without ON CONFLICT (SQL Server)."""
        existing = await self.get_by_bale_id(bale_chat_id)
        if existing is not None:
            if title:
                existing.title = title
            existing.chat_type = chat_type
            existing.is_active = True
            await self._session.flush()
            return existing
        group = Group(
            bale_chat_id=bale_chat_id,
            title=title,
            chat_type=chat_type,
            is_active=True,
            bot_can_delete=False,
            settings={},
            joined_at=datetime.now(UTC),
        )
        try:
            async with self._session.begin_nested():
                self._session.add(group)
                await self._session.flush()
        except IntegrityError:
            existing = await self.get_by_bale_id(bale_chat_id)
            if existing is None:
                raise
            if title:
                existing.title = title
            existing.chat_type = chat_type
            existing.is_active = True
            return existing
        return group

    async def _require_group(self, bale_chat_id: int) -> Group:
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
