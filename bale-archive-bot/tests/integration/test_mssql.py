"""SQL Server integration: skipped unless MSSQL_TEST_URL is set.

Point this at a local SQL Server (ODBC Driver 17/18) when you want a
live round-trip. CI does not run this.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.locks import advisory_xact_lock
from app.db.base import Base
from app.db.dialect import is_mssql
from app.db.models import ContentType, SubmissionStatus
from app.db.repositories.groups import GroupRepository
from app.db.repositories.submissions import SubmissionRepository
from app.db.repositories.tags import TagRepository
from app.db.repositories.users import UserRepository
from app.domain.reports import ReportService
from app.i18n.fa import SEED_TAGS

_MSSQL_URL = os.environ.get("MSSQL_TEST_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not _MSSQL_URL, reason="MSSQL_TEST_URL is not set (local SQL Server only)"
)


@pytest.fixture(scope="module")
async def mssql_factory() -> AsyncIterator[async_sessionmaker]:  # type: ignore[type-arg]
    engine = create_async_engine(_MSSQL_URL, pool_pre_ping=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_mssql_reports_and_lock(mssql_factory: async_sessionmaker) -> None:  # type: ignore[type-arg]
    async with mssql_factory() as session, session.begin():
        assert is_mssql(session) is True
        tags_repo = TagRepository(session)
        for slug, title_fa, hashtag in SEED_TAGS:
            if await tags_repo.get_by_slug(slug) is None:
                await tags_repo.create(slug=slug, title_fa=title_fa, hashtag=hashtag)
        users = UserRepository(session)
        user = await users.upsert_from_bale(1, "ali", "علی", "احمدی")
        groups = GroupRepository(session)
        group = await groups.upsert(-100, "پژوهش", "group")
        subs = SubmissionRepository(session)
        submission = await subs.create_draft(
            user_id=user.id,
            group_id=group.id,
            content_type=ContentType.TEXT,
            content_subtype=None,
            text_content="متن آزمایشی درباره‌ی هوش مصنوعی",
            text_normalized="متن ازمایشی درباره ی هوش مصنوعی",
            caption=None,
            urls=[],
            is_forwarded=False,
            forward_source=None,
            original_message_id=None,
            raw_update={"probe": True},
            ttl_minutes=30,
        )
        active = await tags_repo.list_active()
        await subs.set_tags(submission, [active[0].id])
        await subs.set_status(submission, SubmissionStatus.COMPLETED)
        short_id = submission.short_id
        await advisory_xact_lock(session, 1, 2)

    async with mssql_factory() as session, session.begin():
        service = ReportService(session)
        overall = await service.overall()
        assert overall.total >= 1
        top_users = await service.top_users(limit=5)
        assert top_users[0].display_name == "علی احمدی"
        hits = await service.search("هوش", use_trigram=True)
        assert hits and hits[0].short_id == short_id
        health = await service.health()
        assert health.db_size
        export_rows = await service.submissions_for_export()
        assert export_rows
