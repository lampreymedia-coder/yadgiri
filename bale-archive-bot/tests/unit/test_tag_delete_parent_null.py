"""Tag delete clears self-referential parent_id before removing the row."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Tag
from app.db.repositories.tags import TagRepository


@pytest.mark.asyncio
async def test_delete_tag_nulls_child_parent_id() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session, session.begin():
        repo = TagRepository(session)
        parent = await repo.create(slug="parent", title_fa="والد", hashtag="#والد")
        child = await repo.create(slug="child", title_fa="فرزند", hashtag="#فرزند")
        child.parent_id = parent.id
        await session.flush()
        parent_id = parent.id
        child_id = child.id

    async with session_factory() as session, session.begin():
        repo = TagRepository(session)
        await repo.delete(parent_id)

    async with session_factory() as session:
        remaining = (
            await session.execute(select(Tag).where(Tag.id == child_id))
        ).scalar_one()
        assert remaining.parent_id is None
        assert await session.get(Tag, parent_id) is None

    await engine.dispose()
