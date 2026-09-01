"""SQLite lock handling: busy is retryable, not an outage."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.core.context import BotContext
from app.core.dispatcher import Dispatcher
from app.db.session import Database, is_connectivity_error, is_sqlite_busy
from app.i18n import fa
from tests.e2e.test_commands import _private
from tests.fakes.fake_bale import FakeBaleServer


def _locked_error() -> OperationalError:
    orig = sqlite3.OperationalError("database is locked")
    return OperationalError("(sqlite3.OperationalError) database is locked", {}, orig)


def test_sqlite_busy_is_not_a_connectivity_outage() -> None:
    exc = _locked_error()
    assert is_sqlite_busy(exc) is True
    assert is_connectivity_error(exc) is False


def test_unable_to_open_sqlite_file_is_connectivity() -> None:
    orig = sqlite3.OperationalError("unable to open database file")
    exc = OperationalError("(sqlite3.OperationalError) unable to open database file", {}, orig)
    assert is_sqlite_busy(exc) is False
    assert is_connectivity_error(exc) is True


async def test_file_sqlite_enables_wal_and_busy_timeout(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path}/lock.db")
    async with database.session() as session:
        mode = await session.scalar(text("PRAGMA journal_mode"))
        timeout = await session.scalar(text("PRAGMA busy_timeout"))
    await database.dispose()
    assert str(mode).lower() == "wal"
    assert int(timeout or 0) >= 30000


async def test_sqlite_lock_on_claim_retries_and_does_not_alarm(
    ctx: BotContext,
    fake_bale: FakeBaleServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import dispatcher as dispatcher_mod
    from app.core.idempotency import claim_update as real_claim

    calls = {"n": 0}

    async def flaky_claim(session: object, update_id: int) -> bool:
        calls["n"] += 1
        if calls["n"] == 1:
            raise _locked_error()
        return await real_claim(session, update_id)  # type: ignore[arg-type]

    monkeypatch.setattr(dispatcher_mod, "claim_update", flaky_claim)
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(_private("/help"))
    texts = fake_bale.sent_texts()
    assert fa.ERR_DEGRADED not in texts
    assert any("نحوه کار" in text for text in texts)
    assert calls["n"] >= 2


async def test_sqlite_lock_exhausted_spools_silently(
    ctx: BotContext,
    fake_bale: FakeBaleServer,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.core import dispatcher as dispatcher_mod

    async def always_locked(_session: object, _update_id: int) -> bool:
        raise _locked_error()

    monkeypatch.setattr(dispatcher_mod, "claim_update", always_locked)
    dispatcher = Dispatcher(ctx)
    dispatcher._spool_dir = tmp_path / "spool"
    await dispatcher.dispatch(_private("/help"))
    assert fa.ERR_DEGRADED not in fake_bale.sent_texts()
    assert fa.ERR_GENERIC not in fake_bale.sent_texts()
    assert list(dispatcher._spool_dir.glob("*.json"))
