"""Typed wrappers for every approved Bale API method (spec section 2-13).

No other method name is ever sent to the API. Each wrapper converts the
JSON result into the matching pydantic model.
"""

from __future__ import annotations

from typing import Any

from app.bale.client import BaleClient
from app.bale.errors import BaleAPIError, NotFound
from app.bale.models import (
    Chat,
    File,
    InlineKeyboardMarkup,
    Message,
    Update,
    User,
    WebhookInfo,
)
from app.observability.logging import get_logger

logger = get_logger(__name__)


class BaleAPI:
    """High-level typed facade over :class:`BaleClient`."""

    def __init__(self, client: BaleClient) -> None:
        self.client = client

    # ─── Bot lifecycle ───

    async def get_me(self) -> User:
        return User.model_validate(await self.client.request("getMe"))

    async def logout(self) -> bool:
        return bool(await self.client.request("logout"))

    async def close(self) -> bool:
        return bool(await self.client.request("close"))

    # ─── Updates ───

    async def get_updates(self, offset: int | None = None, limit: int = 100) -> list[Update]:
        # Bale getUpdates supports only offset & limit (1..100); no long-polling.
        result = await self.client.request(
            "getUpdates", {"offset": offset, "limit": max(1, min(limit, 100))}
        )
        return [Update.model_validate(item) for item in result or []]

    async def set_webhook(self, url: str) -> bool:
        return bool(await self.client.request("setWebhook", {"url": url}))

    async def get_webhook_info(self) -> WebhookInfo:
        return WebhookInfo.model_validate(await self.client.request("getWebhookInfo"))

    # ─── Sending ───

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
        reply_to_message_id: int | None = None,
        is_group: bool = False,
    ) -> Message:
        params: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "reply_to_message_id": reply_to_message_id,
        }
        if reply_markup is not None:
            params["reply_markup"] = reply_markup.to_payload()
        result = await self.client.request(
            "sendMessage", params, chat_id=chat_id, is_group=is_group
        )
        return Message.model_validate(result)

    async def _send_media(
        self,
        method: str,
        field: str,
        chat_id: int,
        media: str | bytes,
        caption: str | None = None,
        file_name: str = "file.bin",
        mime_type: str = "application/octet-stream",
        reply_to_message_id: int | None = None,
        is_group: bool = False,
    ) -> Message:
        params: dict[str, Any] = {
            "chat_id": chat_id,
            "caption": caption,
            "reply_to_message_id": reply_to_message_id,
        }
        files: dict[str, tuple[str, bytes, str]] | None = None
        if isinstance(media, bytes):
            files = {field: (file_name, media, mime_type)}
        else:
            params[field] = media
        result = await self.client.request(
            method, params, files=files, chat_id=chat_id, is_group=is_group
        )
        return Message.model_validate(result)

    async def send_photo(
        self,
        chat_id: int,
        photo: str | bytes,
        caption: str | None = None,
        is_group: bool = False,
    ) -> Message:
        return await self._send_media(
            "sendPhoto", "photo", chat_id, photo, caption, "photo.jpg", "image/jpeg", None, is_group
        )

    async def send_audio(
        self,
        chat_id: int,
        audio: str | bytes,
        caption: str | None = None,
        is_group: bool = False,
    ) -> Message:
        return await self._send_media(
            "sendAudio", "audio", chat_id, audio, caption, "audio.mp3", "audio/mpeg", None, is_group
        )

    async def send_document(
        self,
        chat_id: int,
        document: str | bytes,
        caption: str | None = None,
        file_name: str = "file.bin",
        is_group: bool = False,
    ) -> Message:
        return await self._send_media(
            "sendDocument",
            "document",
            chat_id,
            document,
            caption,
            file_name,
            "application/octet-stream",
            None,
            is_group,
        )

    async def send_video(
        self,
        chat_id: int,
        video: str | bytes,
        caption: str | None = None,
        is_group: bool = False,
    ) -> Message:
        return await self._send_media(
            "sendVideo", "video", chat_id, video, caption, "video.mp4", "video/mp4", None, is_group
        )

    async def send_animation(
        self,
        chat_id: int,
        animation: str | bytes,
        caption: str | None = None,
        is_group: bool = False,
    ) -> Message:
        return await self._send_media(
            "sendAnimation",
            "animation",
            chat_id,
            animation,
            caption,
            "animation.mp4",
            "video/mp4",
            None,
            is_group,
        )

    async def send_voice(
        self,
        chat_id: int,
        voice: str | bytes,
        caption: str | None = None,
        is_group: bool = False,
    ) -> Message:
        return await self._send_media(
            "sendVoice", "voice", chat_id, voice, caption, "voice.ogg", "audio/ogg", None, is_group
        )

    async def send_media_group(
        self, chat_id: int, media: list[dict[str, Any]], is_group: bool = False
    ) -> list[Message]:
        result = await self.client.request(
            "sendMediaGroup",
            {"chat_id": chat_id, "media": media},
            chat_id=chat_id,
            is_group=is_group,
        )
        return [Message.model_validate(item) for item in result or []]

    async def send_location(
        self, chat_id: int, latitude: float, longitude: float, is_group: bool = False
    ) -> Message:
        result = await self.client.request(
            "sendLocation",
            {"chat_id": chat_id, "latitude": latitude, "longitude": longitude},
            chat_id=chat_id,
            is_group=is_group,
        )
        return Message.model_validate(result)

    async def send_contact(
        self,
        chat_id: int,
        phone_number: str,
        first_name: str,
        last_name: str | None = None,
        is_group: bool = False,
    ) -> Message:
        result = await self.client.request(
            "sendContact",
            {
                "chat_id": chat_id,
                "phone_number": phone_number,
                "first_name": first_name,
                "last_name": last_name,
            },
            chat_id=chat_id,
            is_group=is_group,
        )
        return Message.model_validate(result)

    async def forward_message(
        self, chat_id: int, from_chat_id: int, message_id: int, is_group: bool = False
    ) -> Message:
        result = await self.client.request(
            "forwardMessage",
            {"chat_id": chat_id, "from_chat_id": from_chat_id, "message_id": message_id},
            chat_id=chat_id,
            is_group=is_group,
        )
        return Message.model_validate(result)

    async def copy_message(
        self,
        chat_id: int,
        from_chat_id: int,
        message_id: int,
        caption: str | None = None,
        is_group: bool = False,
    ) -> int:
        """Copy a message; returns the new message_id."""
        result = await self.client.request(
            "copyMessage",
            {
                "chat_id": chat_id,
                "from_chat_id": from_chat_id,
                "message_id": message_id,
                "caption": caption,
            },
            chat_id=chat_id,
            is_group=is_group,
        )
        if isinstance(result, dict) and "message_id" in result:
            return int(result["message_id"])
        return int(result)

    # ─── Editing / deleting ───

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> Message | bool:
        params: dict[str, Any] = {"chat_id": chat_id, "message_id": message_id, "text": text}
        if reply_markup is not None:
            params["reply_markup"] = reply_markup.to_payload()
        result = await self.client.request("editMessageText", params, chat_id=chat_id)
        if isinstance(result, dict):
            return Message.model_validate(result)
        return bool(result)

    async def delete_message(self, chat_id: int, message_id: int) -> bool:
        return bool(
            await self.client.request(
                "deleteMessage", {"chat_id": chat_id, "message_id": message_id}, chat_id=chat_id
            )
        )

    async def safe_edit(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
        is_group: bool = False,
    ) -> int:
        """Edit text+keyboard together; fall back to delete+send when the edit fails.

        Returns the message_id that now displays ``text`` (may differ from
        the input when the fallback path was taken).
        """
        try:
            await self.edit_message_text(chat_id, message_id, text, reply_markup)
        except BaleAPIError as exc:
            logger.info(
                "safe_edit_fallback",
                chat_id=chat_id,
                message_id=message_id,
                error_code=exc.error_code,
            )
            try:
                await self.delete_message(chat_id, message_id)
            except BaleAPIError:
                logger.info("safe_edit_delete_failed", chat_id=chat_id, message_id=message_id)
            sent = await self.send_message(chat_id, text, reply_markup, is_group=is_group)
            return sent.message_id
        return message_id

    # ─── Files ───

    async def get_file(self, file_id: str) -> File:
        return File.model_validate(await self.client.request("getFile", {"file_id": file_id}))

    # ─── Chats ───

    async def get_chat(self, chat_id: int) -> Chat:
        return Chat.model_validate(await self.client.request("getChat", {"chat_id": chat_id}))

    async def get_chat_members_count(self, chat_id: int) -> int:
        return int(await self.client.request("getChatMembersCount", {"chat_id": chat_id}))

    async def leave_chat(self, chat_id: int) -> bool:
        return bool(await self.client.request("leaveChat", {"chat_id": chat_id}))

    async def ban_chat_member(self, chat_id: int, user_id: int) -> bool:
        return bool(
            await self.client.request(
                "banChatMember", {"chat_id": chat_id, "user_id": user_id}, chat_id=chat_id
            )
        )

    async def unban_chat_member(self, chat_id: int, user_id: int) -> bool:
        return bool(
            await self.client.request(
                "unbanChatMember", {"chat_id": chat_id, "user_id": user_id}, chat_id=chat_id
            )
        )

    async def promote_chat_member(self, chat_id: int, user_id: int, **permissions: bool) -> bool:
        params: dict[str, Any] = {"chat_id": chat_id, "user_id": user_id}
        params.update(permissions)
        return bool(await self.client.request("promoteChatMember", params, chat_id=chat_id))

    async def pin_chat_message(self, chat_id: int, message_id: int) -> bool:
        return bool(
            await self.client.request(
                "pinChatMessage", {"chat_id": chat_id, "message_id": message_id}, chat_id=chat_id
            )
        )

    async def unpin_chat_message(self, chat_id: int, message_id: int) -> bool:
        return bool(
            await self.client.request(
                "unPinChatMessage", {"chat_id": chat_id, "message_id": message_id}, chat_id=chat_id
            )
        )

    async def unpin_all_chat_messages(self, chat_id: int) -> bool:
        return bool(
            await self.client.request("unpinAllChatMessages", {"chat_id": chat_id}, chat_id=chat_id)
        )

    async def set_chat_title(self, chat_id: int, title: str) -> bool:
        return bool(
            await self.client.request(
                "setChatTitle", {"chat_id": chat_id, "title": title}, chat_id=chat_id
            )
        )

    async def set_chat_description(self, chat_id: int, description: str) -> bool:
        return bool(
            await self.client.request(
                "setChatDescription",
                {"chat_id": chat_id, "description": description},
                chat_id=chat_id,
            )
        )

    async def set_chat_photo(self, chat_id: int, photo: bytes) -> bool:
        return bool(
            await self.client.request(
                "setChatPhoto",
                {"chat_id": chat_id},
                files={"photo": ("photo.jpg", photo, "image/jpeg")},
                chat_id=chat_id,
            )
        )

    async def delete_chat_photo(self, chat_id: int) -> bool:
        return bool(
            await self.client.request("deleteChatPhoto", {"chat_id": chat_id}, chat_id=chat_id)
        )

    async def create_chat_invite_link(self, chat_id: int) -> str:
        result = await self.client.request(
            "createChatInviteLink", {"chat_id": chat_id}, chat_id=chat_id
        )
        if isinstance(result, dict):
            return str(result.get("invite_link", ""))
        return str(result)

    async def revoke_chat_invite_link(self, chat_id: int, invite_link: str) -> bool:
        return bool(
            await self.client.request(
                "revokeChatInviteLink",
                {"chat_id": chat_id, "invite_link": invite_link},
                chat_id=chat_id,
            )
        )

    async def export_chat_invite_link(self, chat_id: int) -> str:
        return str(
            await self.client.request("exportChatInviteLink", {"chat_id": chat_id}, chat_id=chat_id)
        )

    # ─── Callbacks ───

    async def answer_callback_query(
        self, callback_query_id: str, text: str | None = None, show_alert: bool = False
    ) -> bool:
        try:
            return bool(
                await self.client.request(
                    "answerCallbackQuery",
                    {
                        "callback_query_id": callback_query_id,
                        "text": text,
                        "show_alert": show_alert,
                    },
                )
            )
        except NotFound:
            # Method missing on this deployment (capability probed at startup);
            # ignoring is safe — the button press simply gets no toast.
            logger.info("answer_callback_query_unsupported")
            return False

    # ─── Payments ───

    async def send_invoice(
        self,
        chat_id: int,
        title: str,
        description: str,
        payload: str,
        provider_token: str,
        prices: list[dict[str, Any]],
    ) -> Message:
        result = await self.client.request(
            "sendInvoice",
            {
                "chat_id": chat_id,
                "title": title,
                "description": description,
                "payload": payload,
                "provider_token": provider_token,
                "prices": prices,
            },
            chat_id=chat_id,
        )
        return Message.model_validate(result)
