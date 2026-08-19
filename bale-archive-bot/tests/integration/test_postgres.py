"""Real-Postgres integration: migrations up/down/up + all report queries.

Requires Docker (testcontainers); skipped automatically when unavailable.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest

pytest.importorskip("testcontainers.postgres")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import ContentType, SubmissionStatus
from app.db.repositories.submissions import SubmissionRepository
from app.db.repositories.tags import TagRepository
from app.db.repositories.users import UserRepository
from app.domain.reports import ReportService
from app.i18n.fa import SEED_TAGS


def _docker_available() -> bool:
    import shutil
    import subprocess

    if shutil.which("docker") is None:
        return False
    try:
        return (
            subprocess.run(
                ["docker", "info"], capture_output=True, timeout=20, check=False
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(
    not _docker_available(), reason="Docker is not available for testcontainers"
)


@pytest.fixture(scope="module")
def pg_url() -> Iterator[str]:
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:17-alpine") as container:
        url = container.get_connection_url().replace("psycopg2", "asyncpg")
        yield url


@pytest.fixture(scope="module")
def migrated(pg_url: str) -> str:
    from alembic.config import Config

    from alembic import command

    os.environ["DATABASE_URL"] = pg_url
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    return pg_url


@pytest.fixture
async def pg_session_factory(migrated: str) -> AsyncIterator[async_sessionmaker]:  # type: ignore[type-arg]
    engine = create_async_engine(migrated)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_migrations_and_reports(pg_session_factory: async_sessionmaker) -> None:  # type: ignore[type-arg]
    async with pg_session_factory() as session, session.begin():
        tags_repo = TagRepository(session)
        for slug, title_fa, hashtag in SEED_TAGS:
            if await tags_repo.get_by_slug(slug) is None:
                await tags_repo.create(slug=slug, title_fa=title_fa, hashtag=hashtag)
        users = UserRepository(session)
        user = await users.upsert_from_bale(1, "ali", "علی", "احمدی")
        subs = SubmissionRepository(session)
        submission = await subs.create_draft(
            user_id=user.id,
            group_id=None,
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

    async with pg_session_factory() as session, session.begin():
        service = ReportService(session)
        overall = await service.overall()
        assert overall.total == 1
        assert overall.contributors == 1

        top_tags = await service.top_tags()
        assert top_tags[0].items == 1

        top_users = await service.top_users(limit=5)
        assert top_users[0].items == 1
        assert top_users[0].display_name == "علی احمدی"  # generated column

        matrix = await service.type_matrix()
        assert matrix[0].text_count == 1

        trend = await service.daily_trend()
        assert trend[0].items == 1

        hits = await service.search("هوش", use_trigram=True)
        assert hits and hits[0].short_id == submission.short_id

        health = await service.health()
        assert health.in_progress == 0
        assert health.db_size


async def test_advisory_lock_and_pg_specific(pg_session_factory: async_sessionmaker) -> None:  # type: ignore[type-arg]
    from app.core.locks import advisory_xact_lock

    async with pg_session_factory() as session, session.begin():
        await advisory_xact_lock(session, 1, 2)
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1
