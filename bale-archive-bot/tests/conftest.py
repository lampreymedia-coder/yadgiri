"""Shared fixtures: fake Bale server, in-memory database, bot context."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest

os.environ.setdefault("BALE_BOT_TOKEN", "test-token")
os.environ.setdefault("ARCHIVE_CHAT_ID", "-500")
os.environ.setdefault("ADMIN_CHAT_ID", "-600")
os.environ.setdefault("ADMIN_USER_IDS", "111")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.bale.capabilities import Capabilities
from app.bale.client import BaleClient
from app.bale.methods import BaleAPI
from app.config import Settings
from app.core.context import BotContext
from app.db.base import Base
from app.db.repositories.tags import TagRepository
from app.db.session import Database
from app.i18n.fa import SEED_TAGS
from tests.fakes.fake_bale import FakeBaleServer


@pytest.fixture
def settings() -> Settings:
    return Settings(
        BALE_BOT_TOKEN="test-token",
        ARCHIVE_CHAT_ID=-500,
        ADMIN_CHAT_ID=-600,
        ADMIN_USER_IDS=[111],
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        UNDO_WINDOW_MINUTES=10,
        ALBUM_WINDOW_MS=50,
    )


@pytest.fixture
def fake_bale() -> FakeBaleServer:
    return FakeBaleServer()


@pytest.fixture
async def api(fake_bale: FakeBaleServer) -> AsyncIterator[BaleAPI]:
    client = BaleClient("test-token", transport=fake_bale.transport())
    yield BaleAPI(client)
    await client.close()


@pytest.fixture
async def db(settings: Settings) -> AsyncIterator[Database]:
    database = Database(settings.database_url)
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield database
    await database.dispose()


@pytest.fixture
async def seeded_db(db: Database) -> Database:
    async with db.session() as session:
        repo = TagRepository(session)
        for slug, title_fa, hashtag in SEED_TAGS:
            await repo.create(slug=slug, title_fa=title_fa, hashtag=hashtag)
    return db


@pytest.fixture
async def ctx(
    settings: Settings, api: BaleAPI, seeded_db: Database, fake_bale: FakeBaleServer
) -> BotContext:
    caps = Capabilities()
    caps.probed = True
    context = BotContext(settings=settings, api=api, db=seeded_db, caps=caps)
    context.bot_username = fake_bale.bot_username
    context.bot_user_id = fake_bale.bot_id
    return context
