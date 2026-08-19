"""Tag persistence: dynamic hashtags managed entirely from the admin panel."""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Tag


class TagRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self) -> list[Tag]:
        result = await self._session.execute(
            select(Tag).where(Tag.is_active.is_(True)).order_by(Tag.sort_order, Tag.id)
        )
        return list(result.scalars().all())

    async def list_all(self) -> list[Tag]:
        result = await self._session.execute(select(Tag).order_by(Tag.sort_order, Tag.id))
        return list(result.scalars().all())

    async def get(self, tag_id: int) -> Tag | None:
        return await self._session.get(Tag, tag_id)

    async def get_by_slug(self, slug: str) -> Tag | None:
        result = await self._session.execute(select(Tag).where(Tag.slug == slug))
        return result.scalar_one_or_none()

    async def get_by_hashtag(self, hashtag: str) -> Tag | None:
        result = await self._session.execute(select(Tag).where(Tag.hashtag == hashtag))
        return result.scalar_one_or_none()

    async def create(
        self,
        slug: str,
        title_fa: str,
        hashtag: str,
        description: str | None = None,
        emoji: str | None = None,
        created_by: int | None = None,
    ) -> Tag:
        max_order = await self._session.scalar(select(func.coalesce(func.max(Tag.sort_order), 0)))
        tag = Tag(
            slug=slug,
            title_fa=title_fa,
            hashtag=hashtag,
            description=description,
            emoji=emoji,
            sort_order=(max_order or 0) + 1,
            created_by=created_by,
        )
        self._session.add(tag)
        await self._session.flush()
        return tag

    async def set_active(self, tag_id: int, is_active: bool) -> None:
        await self._session.execute(update(Tag).where(Tag.id == tag_id).values(is_active=is_active))

    async def update_fields(
        self,
        tag_id: int,
        title_fa: str | None = None,
        description: str | None = None,
        emoji: str | None = None,
    ) -> None:
        values: dict[str, str] = {}
        if title_fa is not None:
            values["title_fa"] = title_fa
        if description is not None:
            values["description"] = description
        if emoji is not None:
            values["emoji"] = emoji
        if values:
            await self._session.execute(update(Tag).where(Tag.id == tag_id).values(**values))

    async def reorder(self, ordered_slugs: list[str]) -> None:
        for position, slug in enumerate(ordered_slugs, start=1):
            await self._session.execute(
                update(Tag).where(Tag.slug == slug).values(sort_order=position)
            )
