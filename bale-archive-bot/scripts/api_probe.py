"""Probe every approved Bale API method against a real test group.

Usage:
    BALE_BOT_TOKEN=... PROBE_CHAT_ID=<test group id> python scripts/api_probe.py

Writes raw findings to docs/BALE_API_NOTES.md:
* which methods respond and which return error codes,
* the exact raw JSON of one real update per content type,
* whether media_group_id / entities / message_thread_id exist,
* whether answerCallbackQuery works,
* observed rate-limit behaviour.

Only harmless parameters are used; nothing destructive runs against the
test group except sending and deleting the probe's own messages.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

BASE = os.environ.get("BALE_API_BASE", "https://tapi.bale.ai")
TOKEN = os.environ.get("BALE_BOT_TOKEN", "")
CHAT_ID = os.environ.get("PROBE_CHAT_ID", "")

APPROVED_METHODS = [
    "getMe",
    "getUpdates",
    "setWebhook",
    "getWebhookInfo",
    "sendMessage",
    "sendPhoto",
    "sendAudio",
    "sendDocument",
    "sendVideo",
    "sendAnimation",
    "sendVoice",
    "sendMediaGroup",
    "sendLocation",
    "sendContact",
    "forwardMessage",
    "copyMessage",
    "editMessageText",
    "deleteMessage",
    "getFile",
    "getChat",
    "getChatMembersCount",
    "leaveChat",
    "banChatMember",
    "unbanChatMember",
    "promoteChatMember",
    "pinChatMessage",
    "unPinChatMessage",
    "unpinAllChatMessages",
    "setChatTitle",
    "setChatDescription",
    "setChatPhoto",
    "deleteChatPhoto",
    "createChatInviteLink",
    "revokeChatInviteLink",
    "exportChatInviteLink",
    "answerCallbackQuery",
    "sendInvoice",
    "logout",
    "close",
]

# Methods that are dangerous to invoke even with harmless params.
SKIP_INVOKE = {
    "logout",
    "close",
    "setWebhook",
    "leaveChat",
    "banChatMember",
    "setChatTitle",
    "setChatDescription",
    "setChatPhoto",
    "deleteChatPhoto",
    "revokeChatInviteLink",
    "unpinAllChatMessages",
}


async def call(client: httpx.AsyncClient, method: str, params: dict[str, Any]) -> dict[str, Any]:
    url = f"{BASE}/bot{TOKEN}/{method}"
    started = time.monotonic()
    try:
        response = await client.post(url, json=params, timeout=15)
        elapsed = time.monotonic() - started
        body = response.json()
        return {"http_status": response.status_code, "elapsed_s": round(elapsed, 3), **body}
    except (httpx.HTTPError, ValueError) as exc:
        return {"ok": False, "transport_error": repr(exc)}


async def probe_methods(client: httpx.AsyncClient) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    chat = int(CHAT_ID) if CHAT_ID else 0
    harmless: dict[str, dict[str, Any]] = {
        "getMe": {},
        "getUpdates": {"limit": 1},
        "getWebhookInfo": {},
        "sendMessage": {"chat_id": chat, "text": "probe"},
        "getChat": {"chat_id": chat},
        "getChatMembersCount": {"chat_id": chat},
        "getFile": {"file_id": "probe-nonexistent"},
        "answerCallbackQuery": {"callback_query_id": "probe-nonexistent"},
        "editMessageText": {"chat_id": chat, "message_id": 1, "text": "probe"},
        "deleteMessage": {"chat_id": chat, "message_id": 999999999},
        "copyMessage": {"chat_id": chat, "from_chat_id": chat, "message_id": 999999999},
        "forwardMessage": {"chat_id": chat, "from_chat_id": chat, "message_id": 999999999},
        "pinChatMessage": {"chat_id": chat, "message_id": 999999999},
        "unPinChatMessage": {"chat_id": chat, "message_id": 999999999},
        "createChatInviteLink": {"chat_id": chat},
        "exportChatInviteLink": {"chat_id": chat},
        "unbanChatMember": {"chat_id": chat, "user_id": 1},
        "promoteChatMember": {"chat_id": chat, "user_id": 1},
        "sendLocation": {"chat_id": chat, "latitude": 35.7, "longitude": 51.4},
        "sendContact": {"chat_id": chat, "phone_number": "+980000000000", "first_name": "probe"},
        "sendMediaGroup": {"chat_id": chat, "media": []},
        "sendInvoice": {
            "chat_id": chat,
            "title": "p",
            "description": "p",
            "payload": "p",
            "provider_token": "p",
            "prices": [],
        },
    }
    for method in APPROVED_METHODS:
        if method in SKIP_INVOKE:
            results[method] = {"skipped": True, "reason": "destructive; not invoked"}
            continue
        params = harmless.get(method, {"chat_id": chat})
        results[method] = await call(client, method, params)
        await asyncio.sleep(0.3)
    return results


async def probe_rate_limit(client: httpx.AsyncClient) -> dict[str, Any]:
    """Fire a burst of getMe calls and record whether/when a 429 appears."""
    outcomes: list[int] = []
    first_429: dict[str, Any] | None = None
    for _ in range(30):
        result = await call(client, "getMe", {})
        code = int(result.get("error_code", 0)) if not result.get("ok") else 200
        outcomes.append(code)
        if code == 429 and first_429 is None:
            first_429 = result
    return {"outcomes": outcomes, "first_429": first_429}


async def collect_updates(client: httpx.AsyncClient, seconds: int = 60) -> list[dict[str, Any]]:
    """Record raw updates for `seconds`; send each content type manually."""
    print(f"Send each content type to the test group now ({seconds}s window)...")
    collected: list[dict[str, Any]] = []
    offset: int | None = None
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        params: dict[str, Any] = {"limit": 100}
        if offset is not None:
            params["offset"] = offset
        result = await call(client, "getUpdates", params)
        for update in result.get("result", []) or []:
            collected.append(update)
            offset = update["update_id"] + 1
        await asyncio.sleep(1.0)
    return collected


def analyse_updates(updates: list[dict[str, Any]]) -> dict[str, Any]:
    seen_fields: set[str] = set()
    samples: dict[str, dict[str, Any]] = {}
    field_order = [
        "voice",
        "audio",
        "animation",
        "video",
        "photo",
        "document",
        "sticker",
        "contact",
        "location",
        "text",
    ]
    for update in updates:
        message = update.get("message") or {}
        seen_fields.update(message.keys())
        for content in field_order:
            if content in message and content not in samples:
                samples[content] = update
                break
    return {
        "message_fields_seen": sorted(seen_fields),
        "has_media_group_id": "media_group_id" in seen_fields,
        "has_entities": "entities" in seen_fields,
        "has_message_thread_id": "message_thread_id" in seen_fields,
        "samples": samples,
    }


def write_notes(
    results: dict[str, dict[str, Any]],
    rate: dict[str, Any],
    analysis: dict[str, Any],
) -> None:
    notes = Path(__file__).resolve().parent.parent / "docs" / "BALE_API_NOTES.md"
    notes.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Bale API probe results",
        "",
        f"Probed at: {datetime.now(UTC).isoformat()}",
        "",
        "## Method availability",
        "",
        "| Method | Outcome |",
        "|--------|---------|",
    ]
    for method, result in results.items():
        if result.get("skipped"):
            outcome = "skipped (destructive)"
        elif result.get("ok"):
            outcome = "OK"
        elif "error_code" in result:
            outcome = f"error_code={result['error_code']}: {result.get('description', '')}"
        else:
            outcome = result.get("transport_error", "unknown")
        lines.append(f"| `{method}` | {outcome} |")
    lines += [
        "",
        "## Update structure",
        "",
        f"- `media_group_id` present: **{analysis['has_media_group_id']}**",
        f"- `entities` present: **{analysis['has_entities']}**",
        f"- `message_thread_id` present: **{analysis['has_message_thread_id']}**",
        f"- Message fields seen: `{', '.join(analysis['message_fields_seen'])}`",
        "",
        "## Raw update samples (one per content type)",
        "",
    ]
    for content, sample in analysis["samples"].items():
        lines += [
            f"### {content}",
            "",
            "```json",
            json.dumps(sample, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    lines += [
        "## Rate limit burst test (30 rapid getMe calls)",
        "",
        "```json",
        json.dumps(rate, ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    notes.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {notes}")


async def main() -> int:
    if not TOKEN:
        print("BALE_BOT_TOKEN is required", file=sys.stderr)
        return 2
    if not CHAT_ID:
        print("PROBE_CHAT_ID (a test group id) is required", file=sys.stderr)
        return 2
    async with httpx.AsyncClient() as client:
        print("Probing method availability...")
        results = await probe_methods(client)
        print("Collecting live updates (send content types now)...")
        updates = await collect_updates(client, seconds=int(os.environ.get("PROBE_WINDOW_S", "60")))
        analysis = analyse_updates(updates)
        print("Testing rate-limit behaviour...")
        rate = await probe_rate_limit(client)
    write_notes(results, rate, analysis)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
