"""Unit tests: Bale payload coercion used by Iranian gateways."""

from __future__ import annotations

from app.bale.models import Message, Update


def test_chat_and_user_ids_accept_numeric_strings() -> None:
    update = Update.try_parse(
        {
            "update_id": "100145",
            "message": {
                "message_id": "9",
                "date": "1",
                "chat": {"id": "-100200300", "type": "group", "title": "رصد"},
                "from": {"id": "1290496049", "is_bot": False, "first_name": "فاطمه"},
                "text": "/start",
            },
        }
    )
    assert update is not None
    assert update.update_id == 100145
    assert update.message is not None
    assert update.message.chat.id == -100200300
    assert update.message.from_user is not None
    assert update.message.from_user.id == 1290496049


def test_missing_chat_type_with_title_is_group() -> None:
    message = Message.model_validate(
        {
            "message_id": 1,
            "chat": {"id": 555, "title": "گروه رصد"},
            "from": {"id": 1, "is_bot": False, "first_name": "a"},
            "text": "سلام",
        }
    )
    assert message.is_group_message is True
    assert message.is_private_message is False


def test_private_chat_without_title_stays_private() -> None:
    message = Message.model_validate(
        {
            "message_id": 1,
            "chat": {"id": 555, "type": "private"},
            "from": {"id": 1, "is_bot": False, "first_name": "a"},
            "text": "سلام",
        }
    )
    assert message.is_private_message is True
