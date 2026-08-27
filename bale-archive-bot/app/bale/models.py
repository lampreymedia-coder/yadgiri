"""Pydantic models for Bale API objects.

Only the update kinds that Bale actually delivers are modelled:
``message``, ``edited_message``, ``callback_query``, and (when present)
``my_chat_member`` / ``chat_member`` join events. Unknown extra
fields are kept (``model_config.extra="allow"``) so the raw update stays
lossless in ``submissions.raw_update`` and undocumented fields such as
``media_group_id`` can be probed at runtime.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

_ID_KEYS = {
    "id",
    "update_id",
    "message_id",
    "chat_id",
    "from_chat_id",
    "user_id",
    "date",
    "forward_from_message_id",
    "forward_date",
}


def _as_int(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lstrip("-").isdigit():
            return int(stripped)
        if stripped.count(".") == 1 and stripped.replace(".", "").lstrip("-").isdigit():
            return int(float(stripped))
    return value


def _coerce_ids(value: Any) -> Any:
    if isinstance(value, list):
        return [_coerce_ids(item) for item in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            out[key] = _as_int(item) if key in _ID_KEYS else _coerce_ids(item)
        return out
    return value


class _BaleModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class User(_BaleModel):
    id: int
    is_bot: bool = False
    first_name: str = ""
    last_name: str | None = None
    username: str | None = None

    @field_validator("id", mode="before")
    @classmethod
    def _user_id(cls, value: Any) -> Any:
        return _as_int(value)


class Chat(_BaleModel):
    id: int
    type: str = ""
    title: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None

    @field_validator("id", mode="before")
    @classmethod
    def _chat_id(cls, value: Any) -> Any:
        return _as_int(value)


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

    @field_validator("duration", "file_size", mode="before")
    @classmethod
    def _audio_ints(cls, value: Any) -> Any:
        return _as_int(value)


class Voice(_BaleModel):
    file_id: str
    file_unique_id: str | None = None
    duration: int | None = None
    mime_type: str | None = None
    file_size: int | None = None

    @field_validator("duration", "file_size", mode="before")
    @classmethod
    def _voice_ints(cls, value: Any) -> Any:
        return _as_int(value)


class Document(_BaleModel):
    file_id: str
    file_unique_id: str | None = None
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None

    @field_validator("file_size", mode="before")
    @classmethod
    def _document_ints(cls, value: Any) -> Any:
        return _as_int(value)


class Video(_BaleModel):
    file_id: str
    file_unique_id: str | None = None
    width: int | None = None
    height: int | None = None
    duration: int | None = None
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None

    @field_validator("width", "height", "duration", "file_size", mode="before")
    @classmethod
    def _video_ints(cls, value: Any) -> Any:
        return _as_int(value)


class Animation(_BaleModel):
    file_id: str
    file_unique_id: str | None = None
    width: int | None = None
    height: int | None = None
    duration: int | None = None
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None

    @field_validator("width", "height", "duration", "file_size", mode="before")
    @classmethod
    def _animation_ints(cls, value: Any) -> Any:
        return _as_int(value)


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


class VideoNote(_BaleModel):
    file_id: str
    file_unique_id: str | None = None
    length: int | None = None
    duration: int | None = None
    file_size: int | None = None
    mime_type: str | None = None

    @field_validator("length", "duration", "file_size", mode="before")
    @classmethod
    def _video_note_ints(cls, value: Any) -> Any:
        return _as_int(value)


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
    video_note: VideoNote | None = None
    animation: Animation | None = None
    sticker: Sticker | None = None
    contact: Contact | None = None
    location: Location | None = None
    reply_to_message: Message | None = None
    forward_from: User | None = None
    forward_from_chat: Chat | None = None
    forward_from_message_id: int | None = None
    forward_date: int | None = None
    forward_sender_name: str | None = None
    new_chat_members: list[User] | None = None
    new_chat_member: User | None = None  # singular form some Bale payloads use
    left_chat_member: User | None = None
    group_chat_created: bool | None = None
    # Undocumented in Bale docs; kept optional and verified by api_probe.
    media_group_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_media_payload(cls, value: Any) -> Any:
        """Accept Bale variants: ``file`` instead of document, list wrappers, string file_ids."""
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if data.get("file") and not data.get("document"):
            data["document"] = data["file"]
        members = data.get("new_chat_members")
        if isinstance(members, dict):
            data["new_chat_members"] = [members]
        participant = data.get("new_chat_participant")
        if participant and not data.get("new_chat_member"):
            data["new_chat_member"] = participant
        for key in (
            "voice",
            "audio",
            "video",
            "video_note",
            "document",
            "animation",
            "sticker",
        ):
            item = data.get(key)
            if isinstance(item, list) and item:
                data[key] = item[0]
            elif isinstance(item, str) and item:
                data[key] = {"file_id": item}
            elif item in ({}, False):
                data.pop(key, None)
        return data

    def added_members(self) -> list[User]:
        """Join events: Bale may send an array, a single user, or both."""
        members = list(self.new_chat_members or [])
        if self.new_chat_member is not None:
            members.append(self.new_chat_member)
        return members

    @property
    def is_group_message(self) -> bool:
        return not self.is_private_message

    @property
    def is_private_message(self) -> bool:
        ctype = (self.chat.type or "").lower()
        if ctype in ("group", "supergroup", "channel"):
            return False
        # Missing type or private/pv: a title means a group/channel.
        return not bool(self.chat.title)

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
    my_chat_member: dict[str, Any] | None = None
    chat_member: dict[str, Any] | None = None

    @field_validator("update_id", mode="before")
    @classmethod
    def _update_id(cls, value: Any) -> Any:
        return _as_int(value)

    @classmethod
    def try_parse(cls, item: Any) -> Update | None:
        """Parse one update; coerce string ids used by some Bale gateways."""
        try:
            return cls.model_validate(item)
        except (ValidationError, ValueError, TypeError):
            if not isinstance(item, dict):
                return None
            try:
                return cls.model_validate(_coerce_ids(item))
            except (ValidationError, ValueError, TypeError):
                return None

    @property
    def kind(self) -> str:
        if self.message is not None:
            return "message"
        if self.edited_message is not None:
            return "edited_message"
        if self.callback_query is not None:
            return "callback_query"
        if self.my_chat_member is not None:
            return "my_chat_member"
        if self.chat_member is not None:
            return "chat_member"
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
