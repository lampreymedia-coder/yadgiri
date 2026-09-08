"""Load test: 200 concurrent updates → zero duplicates, zero unhandled errors."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.bale.capabilities import Capabilities
from app.bale.client import BaleClient
from app.bale.methods import BaleAPI
from app.bale.models import Update
from app.config import Settings
from app.core.context import BotContext
from app.core.dispatcher import Dispatcher
from app.db.base import Base
from app.db.models import ProcessedUpdate, Submission
from app.db.repositories.tags import TagRepository
from app.db.session import Database
from app.i18n.fa import SEED_TAGS
from tests.e2e.test_wizard_flow import load_update
from tests.fakes.fake_bale import FakeBaleServer


@pytest.fixture
async def file_db(tmp_path: Path) -> AsyncIterator[Database]:
    database = Database(f"sqlite+aiosqlite:///{tmp_path}/load.db")
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with database.session() as session:
        repo = TagRepository(session)
        for slug, title_fa, hashtag in SEED_TAGS:
            await repo.create(slug=slug, title_fa=title_fa, hashtag=hashtag)
    yield database
    await database.dispose()


async def test_200_concurrent_updates(
    settings: Settings, fake_bale: FakeBaleServer, file_db: Database
) -> None:
    client = BaleClient("test-token", transport=fake_bale.transport())
    api = BaleAPI(client)
    caps = Capabilities()
    caps.probed = True
    ctx = BotContext(settings=settings, api=api, db=file_db, caps=caps)
    ctx.bot_username = fake_bale.bot_username
    ctx.bot_user_id = fake_bale.bot_id
    ctx.spam_guard._max = 10_000
    dispatcher = Dispatcher(ctx)

    updates: list[Update] = []
    for i in range(100):
        raw = load_update("text")
        raw["message"]["message_id"] = 50_000 + i
        raw["message"]["text"] = f"پیام آزمایشی شماره {i}"
        # Spread across many users to avoid the per-conversation lock
        # serialising everything (that path is covered elsewhere).
        raw["message"]["from"] = {
            "id": 100_000 + i,
            "is_bot": False,
            "first_name": f"user{i}",
        }
        update = Update.model_validate(raw)
        updates.append(update)
        updates.append(update)  # exact duplicate: must be processed once

    started = time.monotonic()
    latencies: list[float] = []
    # SQLite allows a single writer; bound concurrency the way the polling
    # loop naturally does. Correctness (zero duplicates) is still exercised
    # with fully concurrent duplicate pairs inside each window.
    gate = asyncio.Semaphore(16)

    async def timed_dispatch(update: Update) -> None:
        async with gate:
            t0 = time.monotonic()
            await dispatcher.dispatch(update)
            latencies.append(time.monotonic() - t0)

    await asyncio.gather(*(timed_dispatch(u) for u in updates))
    elapsed = time.monotonic() - started

    async with file_db.session() as session:
        submission_count = int(
            await session.scalar(select(func.count()).select_from(Submission)) or 0
        )
        processed_count = int(
            await session.scalar(select(func.count()).select_from(ProcessedUpdate)) or 0
        )

    assert submission_count == 100, f"expected 100 submissions, got {submission_count}"
    assert processed_count == 100
    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)]
    assert p95 < 2.0, f"p95 latency {p95:.2f}s exceeds 2s (total {elapsed:.2f}s)"
    await client.close()
