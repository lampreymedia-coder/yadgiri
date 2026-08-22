"""Unit tests: BaleClient retry/backoff semantics (no real network)."""

from __future__ import annotations

import json
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


async def test_send_payload_matches_bale_libraries() -> None:
    """Bale rejects nested reply_markup / numeric chat_id with a 404."""
    server = FakeBaleServer()
    client = await make_client(server)
    await client.request(
        "sendMessage",
        {
            "chat_id": 99,
            "text": "hi",
            "reply_markup": {"inline_keyboard": [[{"text": "بله", "callback_data": "1|yes|ab|"}]]},
        },
    )
    sent = server.calls_for("sendMessage")[0]
    assert sent["chat_id"] == "99"
    assert isinstance(sent["reply_markup"], str)
    decoded = json.loads(sent["reply_markup"])
    assert decoded["inline_keyboard"][0][0]["text"] == "بله"
    await client.close()


async def test_read_methods_use_get_like_official_library() -> None:
    server = FakeBaleServer()
    client = await make_client(server)
    await client.request("getMe")
    assert server.last_http_method == "GET"
    assert server.last_request is not None
    assert "python-bale-bot" in server.last_request.headers["user-agent"]
    assert "fa-IR" in server.last_request.headers["accept-language"]
    await client.close()


async def test_get_updates_posts_json_like_official_library() -> None:
    from app.bale.methods import BaleAPI

    server = FakeBaleServer()
    client = await make_client(server)
    api = BaleAPI(client)
    await api.get_updates(offset=12, limit=50)
    assert server.last_http_method == "POST"
    params = server.calls_for("getUpdates")[0]
    assert str(params["offset"]) == "12"
    assert str(params["limit"]) == "50"
    assert "timeout" not in params
    await client.close()


async def test_get_updates_falls_back_to_get_when_post_rejected() -> None:
    from app.bale.methods import BaleAPI

    server = FakeBaleServer()
    server.fail_with("getUpdates", 404, "method not found", times=1)
    client = await make_client(server)
    api = BaleAPI(client)
    result = await api.get_updates()
    assert result == []
    assert len(server.calls_for("getUpdates")) == 2
    assert server.last_http_method == "GET"
    await client.close()
