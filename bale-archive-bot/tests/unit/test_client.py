"""Unit tests: BaleClient retry/backoff semantics (no real network)."""

from __future__ import annotations

from typing import Any

import pytest

import app.bale.client as client_module
from app.bale.client import BaleClient
from app.bale.errors import BadRequest, NotFound, ServerError
from tests.fakes.fake_bale import FakeBaleServer


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_seconds: float) -> None:
        return

    monkeypatch.setattr(client_module.asyncio, "sleep", instant)


async def make_client(server: FakeBaleServer) -> BaleClient:
    return BaleClient("tkn", transport=server.transport())


async def test_ok_response_returns_result() -> None:
    server = FakeBaleServer()
    client = await make_client(server)
    result = await client.request("getMe")
    assert result["username"] == server.bot_username
    await client.close()


async def test_429_respects_retry_after_then_succeeds() -> None:
    server = FakeBaleServer()
    server.fail_with("getMe", 429, "too many", times=2)
    client = await make_client(server)
    result = await client.request("getMe")
    assert result["id"] == server.bot_id
    assert len(server.calls_for("getMe")) == 3
    await client.close()


async def test_500_retried_with_backoff() -> None:
    server = FakeBaleServer()
    server.fail_with("getMe", 500, "boom", times=3)
    client = await make_client(server)
    result = await client.request("getMe")
    assert result["is_bot"] is True
    assert len(server.calls_for("getMe")) == 4
    await client.close()


async def test_500_exhausts_after_max_attempts() -> None:
    server = FakeBaleServer()
    server.fail_with("getMe", 500, "boom", times=99)
    client = await make_client(server)
    with pytest.raises(ServerError):
        await client.request("getMe", max_attempts=3)
    assert len(server.calls_for("getMe")) == 3
    await client.close()


async def test_400_never_retried() -> None:
    server = FakeBaleServer()
    server.fail_with("sendMessage", 400, "bad params", times=99)
    client = await make_client(server)
    with pytest.raises(BadRequest):
        await client.request("sendMessage", {"chat_id": 1, "text": "x"})
    assert len(server.calls_for("sendMessage")) == 1
    await client.close()


async def test_404_raises_not_found() -> None:
    server = FakeBaleServer()
    client = await make_client(server)
    with pytest.raises(NotFound):
        await client.request("imaginaryMethod")
    await client.close()


async def test_timeout_retried() -> None:
    server = FakeBaleServer()
    server.fail_timeout("getMe", times=2)
    client = await make_client(server)
    result: dict[str, Any] = await client.request("getMe")
    assert result["id"] == server.bot_id
    assert len(server.calls_for("getMe")) == 3
    await client.close()


async def test_none_params_stripped() -> None:
    server = FakeBaleServer()
    client = await make_client(server)
    await client.request("sendMessage", {"chat_id": 1, "text": "hi", "reply_markup": None})
    sent = server.calls_for("sendMessage")[0]
    assert "reply_markup" not in sent
    await client.close()
