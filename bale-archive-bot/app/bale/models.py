"""Pydantic models for Bale API objects.

Only the update kinds that Bale actually delivers are modelled:
``message``, ``edited_message`` and ``callback_query``. Unknown extra
fields are kept (``model_config.extra="allow"``) so the raw update stays
lossless in ``submissions.raw_update`` and undocumented fields such as
``media_group_id`` can be probed at runtime.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _BaleModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class User(_BaleModel):
    id: int
    is_bot: bool = False
    first_name: str = ""
    last_name: str | None = None
    username: str | None = None


class Chat(_BaleModel):
    id: int
    type: str = "private"
    title: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class PhotoSize(_BaleModel):
    file_id: str
    file_unique_id: str | None = None
    width: int | None = None
    height: int | None = None
    file_size: int | None = None


class Audio(_BaleModel):
    file_id: str
    file_unique_id: str | None = None
    duration: int | None = None
    title: str | None = None
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None


class Voice(_BaleModel):
    file_id: str
    file_unique_id: str | None = None
    duration: int | None = None
    mime_type: str | None = None
    file_size: int | None = None


class Document(_BaleModel):
    file_id: str
    file_unique_id: str | None = None
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None


class Video(_BaleModel):
    file_id: str
    file_unique_id: str | None = None
    width: int | None = None
    height: int | None = None
    duration: int | None = None
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None


class Animation(_BaleModel):
    file_id: str
    file_unique_id: str | None = None
    width: int | None = None
    height: int | None = None
    duration: int | None = None
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None


class Sticker(_BaleModel):
    file_id: str
    file_unique_id: str | None = None
    width: int | None = None
    height: int | None = None
    file_size: int | None = None


class Contact(_BaleModel):
    phone_number: str
    first_name: str = ""
    last_name: str | None = None
    user_id: int | None = None


class Location(_BaleModel):
    longitude: float
    latitude: float


class File(_BaleModel):
    file_id: str
    file_unique_id: str | None = None
    file_size: int | None = None
    file_path: str | None = None


class Message(_BaleModel):
    message_id: int
    date: int | None = None
    chat: Chat
    from_user: User | None = Field(default=None, alias="from")
    text: str | None = None
    caption: str | None = None
    photo: list[PhotoSize] | None = None
    audio: Audio | None = None
    voice: Voice | None = None
    document: Document | None = None
    video: Video | None = None
    animation: Animation | None = None
    sticker: Sticker | None = None
    contact: Contact | None = None
    location: Location | None = None
    reply_to_message: Message | None = None
    forward_from: User | None = None
    forward_from_chat: Chat | None = None
    forward_from_message_id: int | None = None
    new_chat_members: list[User] | None = None
    left_chat_member: User | None = None
    # Undocumented in Bale docs; kept optional and verified by api_probe.
    media_group_id: str | None = None

    @property
    def is_group_message(self) -> bool:
        return self.chat.type in ("group", "supergroup")

    @property
    def is_private_message(self) -> bool:
        return self.chat.type == "private"

    def raw(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


class CallbackQuery(_BaleModel):
    id: str
    from_user: User = Field(alias="from")
    message: Message | None = None
    data: str | None = None


class Update(_BaleModel):
    update_id: int
    message: Message | None = None
    edited_message: Message | None = None
    callback_query: CallbackQuery | None = None

    @property
    def kind(self) -> str:
        if self.message is not None:
            return "message"
        if self.edited_message is not None:
            return "edited_message"
        if self.callback_query is not None:
            return "callback_query"
        return "unknown"

    def raw(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


class InlineKeyboardButton(_BaleModel):
    text: str
    callback_data: str | None = None
    url: str | None = None


class InlineKeyboardMarkup(_BaleModel):
    inline_keyboard: list[list[InlineKeyboardButton]]

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class WebhookInfo(_BaleModel):
    url: str = ""
    pending_update_count: int | None = None
