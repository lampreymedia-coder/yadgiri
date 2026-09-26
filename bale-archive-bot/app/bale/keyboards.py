"""Inline keyboard construction and compact callback_data codec.

callback_data scheme (ASCII only, <= 64 bytes, spec section 2-7)::

    <v>|<act>|<sid>|<arg>

* ``v``   — protocol version, currently "1"
* ``act`` — short ASCII action code (e.g. ``tg``, ``cnt``, ``ok``)
* ``sid`` — 6-char base36 short id of the submission ("" for global actions)
* ``arg`` — optional ASCII argument (tag id, count, page number)
"""

from __future__ import annotations

from dataclasses import dataclass

from app.bale.models import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

CALLBACK_VERSION = "1"
MAX_CALLBACK_BYTES = 64


class CallbackDataError(ValueError):
    """Raised when callback data cannot be packed or parsed."""


@dataclass(frozen=True, slots=True)
class CallbackData:
    action: str
    sid: str = ""
    arg: str = ""
    version: str = CALLBACK_VERSION

    def pack(self) -> str:
        data = f"{self.version}|{self.action}|{self.sid}|{self.arg}"
        encoded = data.encode("ascii", errors="strict")
        if len(encoded) > MAX_CALLBACK_BYTES:
            msg = f"callback_data too long: {len(encoded)} bytes"
            raise CallbackDataError(msg)
        return data


def pack_callback(action: str, sid: str = "", arg: str = "") -> str:
    """Pack an action into the compact ASCII callback_data string."""
    if not action.isascii() or not sid.isascii() or not arg.isascii():
        msg = "callback_data parts must be ASCII"
        raise CallbackDataError(msg)
    if "|" in action or "|" in sid or "|" in arg:
        msg = "callback_data parts must not contain '|'"
        raise CallbackDataError(msg)
    return CallbackData(action=action, sid=sid, arg=arg).pack()


def parse_callback(data: str) -> CallbackData:
    """Parse callback_data; raises :class:`CallbackDataError` on malformed input."""
    parts = data.split("|")
    if len(parts) != 4:
        msg = f"malformed callback_data: {data!r}"
        raise CallbackDataError(msg)
    version, action, sid, arg = parts
    if version != CALLBACK_VERSION:
        msg = f"unsupported callback version: {version!r}"
        raise CallbackDataError(msg)
    if not action:
        msg = "empty callback action"
        raise CallbackDataError(msg)
    return CallbackData(action=action, sid=sid, arg=arg, version=version)


def button(text: str, action: str, sid: str = "", arg: str = "") -> InlineKeyboardButton:
    """Create a callback button with packed data."""
    return InlineKeyboardButton(text=text, callback_data=pack_callback(action, sid, arg))


def url_button(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=url)


def keyboard(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reply_keyboard(rows: list[list[KeyboardButton]], *, resize: bool = True) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=resize)


def grid(buttons: list[InlineKeyboardButton], columns: int) -> list[list[InlineKeyboardButton]]:
    """Lay buttons out in ``columns`` columns preserving order."""
    if columns < 1:
        columns = 1
    return [buttons[i : i + columns] for i in range(0, len(buttons), columns)]


def pagination_row(
    action: str,
    sid: str,
    page: int,
    total_pages: int,
    labels: tuple[str, str, str, str] = ("⏮", "◀️", "▶️", "⏭"),
) -> list[InlineKeyboardButton]:
    """Build the standard pagination row; page numbers live in callback_data."""
    first, prev, nxt, last = labels
    row: list[InlineKeyboardButton] = []
    if page > 1:
        row.append(button(first, action, sid, "1"))
        row.append(button(prev, action, sid, str(page - 1)))
    row.append(
        InlineKeyboardButton(
            text=f"{page}/{total_pages}", callback_data=pack_callback("noop", sid, "")
        )
    )
    if page < total_pages:
        row.append(button(nxt, action, sid, str(page + 1)))
        row.append(button(last, action, sid, str(total_pages)))
    return row
