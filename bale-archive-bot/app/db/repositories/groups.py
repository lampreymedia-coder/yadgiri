"""Group persistence."""

from __future__ import annotations

from sqlalchemy import select, update
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
        group = await self.get_by_bale_id(bale_chat_id)
        if group is None:
            group = Group(bale_chat_id=bale_chat_id, title=title, chat_type=chat_type)
            self._session.add(group)
            await self._session.flush()
            return group
        if title:
            group.title = title
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
