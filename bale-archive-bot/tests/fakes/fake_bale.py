"""In-process fake Bale server for tests — no network required.

Implements every approved method behind an ``httpx.MockTransport``,
records all calls, and can be configured to return 429 / 500 / timeouts
for specific methods.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class SentMessage:
    chat_id: int
    message_id: int
    text: str | None = None
    caption: str | None = None
    reply_markup: dict[str, Any] | None = None
    copied_from: tuple[int, int] | None = None
    deleted: bool = False


@dataclass
class FakeBaleServer:
    """Stateful fake: chats, messages, failure injection, call recording."""

    bot_id: int = 999
    bot_username: str = "archive_test_bot"
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    messages: dict[tuple[int, int], SentMessage] = field(default_factory=dict)
    fail_methods: dict[str, dict[str, Any]] = field(default_factory=dict)
    forbidden_private_chats: set[int] = field(default_factory=set)
    _message_seq: itertools.count[int] = field(default_factory=lambda: itertools.count(1000))

    # ─── Failure injection ───

    def fail_with(
        self, method: str, error_code: int, description: str = "injected", times: int = 1
    ) -> None:
        self.fail_methods[method] = {
            "error_code": error_code,
            "description": description,
            "times": times,
        }

    def fail_timeout(self, method: str, times: int = 1) -> None:
        self.fail_methods[method] = {"timeout": True, "times": times}

    def _maybe_fail(self, method: str) -> dict[str, Any] | None:
        spec = self.fail_methods.get(method)
        if not spec or spec["times"] <= 0:
            return None
        spec["times"] -= 1
        if spec.get("timeout"):
            raise httpx.ConnectTimeout("injected timeout")
        body: dict[str, Any] = {
            "ok": False,
            "error_code": spec["error_code"],
            "description": spec["description"],
        }
        if spec["error_code"] == 429:
            body["parameters"] = {"retry_after": spec.get("retry_after", 0)}
        return body

    # ─── Helpers ───

    def sent_texts(self, chat_id: int | None = None) -> list[str]:
        return [
            m.text or ""
            for m in self.messages.values()
            if not m.deleted and (chat_id is None or m.chat_id == chat_id)
        ]

    def last_markup(self, chat_id: int) -> dict[str, Any] | None:
        for message in reversed(list(self.messages.values())):
            if message.chat_id == chat_id and not message.deleted and message.reply_markup:
                return message.reply_markup
        return None

    def calls_for(self, method: str) -> list[dict[str, Any]]:
        return [params for name, params in self.calls if name == method]

    # ─── Request handling ───

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        try:
            params: dict[str, Any] = json.loads(request.content) if request.content else {}
        except ValueError:
            params = {}
        self.calls.append((method, dict(params)))
        markup = params.get("reply_markup")
        if isinstance(markup, str):
            try:
                params["reply_markup"] = json.loads(markup)
            except ValueError:
                pass

        injected = self._maybe_fail(method)
        if injected is not None:
            return httpx.Response(int(injected.get("error_code", 500)), json=injected)

        result = self._dispatch(method, params)
        if isinstance(result, httpx.Response):
            return result
        return httpx.Response(200, json={"ok": True, "result": result})

    def _error(self, code: int, description: str) -> httpx.Response:
        return httpx.Response(
            code, json={"ok": False, "error_code": code, "description": description}
        )

    def _new_message(
        self,
        chat_id: int,
        text: str | None = None,
        caption: str | None = None,
        reply_markup: dict[str, Any] | None = None,
        copied_from: tuple[int, int] | None = None,
    ) -> SentMessage:
        message = SentMessage(
            chat_id=chat_id,
            message_id=next(self._message_seq),
            text=text,
            caption=caption,
            reply_markup=reply_markup,
            copied_from=copied_from,
        )
        self.messages[(chat_id, message.message_id)] = message
        return message

    def _dispatch(self, method: str, params: dict[str, Any]) -> Any:
        if method == "getMe":
            return {
                "id": self.bot_id,
                "is_bot": True,
                "first_name": "Archive",
                "username": self.bot_username,
            }
        if method == "getUpdates":
            return []
        if method == "getWebhookInfo":
            return {"url": ""}
        if method == "setWebhook":
            return True
        if method == "sendMessage":
            chat_id = int(params["chat_id"])
            if chat_id in self.forbidden_private_chats:
                return self._error(403, "bot was blocked by the user")
            message = self._new_message(
                chat_id, text=params.get("text"), reply_markup=params.get("reply_markup")
            )
            return {
                "message_id": message.message_id,
                "chat": {"id": chat_id, "type": "private" if chat_id > 0 else "group"},
                "text": message.text,
            }
        if method == "copyMessage":
            from_key = (int(params["from_chat_id"]), int(params["message_id"]))
            source = self.messages.get(from_key)
            copied = self._new_message(
                int(params["chat_id"]),
                text=source.text if source else None,
                caption=params.get("caption"),
                copied_from=from_key,
            )
            return {"message_id": copied.message_id}
        if method == "forwardMessage":
            forwarded = self._new_message(int(params["chat_id"]))
            return {
                "message_id": forwarded.message_id,
                "chat": {"id": int(params["chat_id"]), "type": "group"},
            }
        if method == "editMessageText":
            key = (int(params["chat_id"]), int(params["message_id"]))
            message = self.messages.get(key)
            if message is None or message.deleted:
                return self._error(400, "message to edit not found")
            message.text = params.get("text")
            message.reply_markup = params.get("reply_markup")
            return {
                "message_id": message.message_id,
                "chat": {"id": message.chat_id, "type": "private"},
                "text": message.text,
            }
        if method == "deleteMessage":
            key = (int(params["chat_id"]), int(params["message_id"]))
            message = self.messages.get(key)
            if message is None:
                # Deleting an unseen (user-sent) message succeeds silently.
                return True
            message.deleted = True
            return True
        if method == "getFile":
            return {
                "file_id": params.get("file_id", ""),
                "file_path": f"files/{params.get('file_id', '')}",
                "file_size": 1024,
            }
        if method == "getChat":
            chat_id = int(params["chat_id"])
            return {
                "id": chat_id,
                "type": "private" if chat_id > 0 else "group",
                "title": f"chat-{chat_id}",
            }
        if method == "getChatMembersCount":
            return 5
        if method == "answerCallbackQuery":
            return True
        if method in (
            "sendPhoto",
            "sendAudio",
            "sendDocument",
            "sendVideo",
            "sendAnimation",
            "sendVoice",
            "sendLocation",
            "sendContact",
        ):
            message = self._new_message(
                int(params.get("chat_id", 0)), caption=params.get("caption")
            )
            return {
                "message_id": message.message_id,
                "chat": {"id": message.chat_id, "type": "group"},
            }
        if method == "sendMediaGroup":
            return []
        if method in (
            "pinChatMessage",
            "unPinChatMessage",
            "unpinAllChatMessages",
            "setChatTitle",
            "setChatDescription",
            "deleteChatPhoto",
            "leaveChat",
            "banChatMember",
            "unbanChatMember",
            "promoteChatMember",
            "revokeChatInviteLink",
            "logout",
            "close",
        ):
            return True
        if method == "createChatInviteLink":
            return {"invite_link": "https://ble.ir/join/fake"}
        if method == "exportChatInviteLink":
            return "https://ble.ir/join/fake"
        if method == "sendInvoice":
            message = self._new_message(int(params["chat_id"]))
            return {
                "message_id": message.message_id,
                "chat": {"id": message.chat_id, "type": "private"},
            }
        return self._error(404, f"method {method} not found")
