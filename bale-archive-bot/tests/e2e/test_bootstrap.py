"""First-run bootstrap: no .env chat ids required."""

from __future__ import annotations

from app.bale.models import Update
from app.core.context import BotContext
from app.core.dispatcher import Dispatcher
from app.db.repositories.misc import AppSettingsRepository
from app.db.repositories.users import UserRepository
from tests.fakes.fake_bale import FakeBaleServer

OWNER_ID = 4242
ARCHIVE_GROUP = -100700800


def _clear_bootstrap(ctx: BotContext) -> None:
    ctx.runtime_admin_ids.clear()
    ctx.settings.admin_user_ids.clear()
    ctx.archive_chat_id = None
    ctx.admin_notify_chat_id = None


async def test_first_private_start_promotes_owner(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    _clear_bootstrap(ctx)
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900001,
                "message": {
                    "message_id": 1,
                    "date": 1,
                    "chat": {"id": OWNER_ID, "type": "private"},
                    "from": {
                        "id": OWNER_ID,
                        "is_bot": False,
                        "first_name": "مینا",
                    },
                    "text": "/start",
                },
            }
        )
    )
    assert OWNER_ID in ctx.runtime_admin_ids
    assert ctx.admin_notify_chat_id == OWNER_ID
    texts = "\n".join(fake_bale.sent_texts(OWNER_ID))
    assert "/archive" in texts
    async with ctx.db.session() as session:
        user = await UserRepository(session).get_by_bale_id(OWNER_ID)
        assert user is not None
        assert user.is_admin is True
        owner = await AppSettingsRepository(session).get("owner_user_id")
        assert int(owner) == OWNER_ID


async def test_group_archive_command_registers_chat(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    _clear_bootstrap(ctx)
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900002,
                "message": {
                    "message_id": 2,
                    "date": 1,
                    "chat": {
                        "id": ARCHIVE_GROUP,
                        "type": "group",
                        "title": "آرشیو خصوصی",
                    },
                    "from": {
                        "id": OWNER_ID,
                        "is_bot": False,
                        "first_name": "مینا",
                    },
                    "text": "/archive",
                },
            }
        )
    )
    assert ctx.archive_chat_id == ARCHIVE_GROUP
    assert OWNER_ID in ctx.runtime_admin_ids
    texts = "\n".join(fake_bale.sent_texts(ARCHIVE_GROUP))
    assert "آرشیو خصوصی" in texts or "ثبت شد" in texts
    async with ctx.db.session() as session:
        stored = await AppSettingsRepository(session).get("archive_chat_id")
        assert int(stored) == ARCHIVE_GROUP


async def test_persian_archive_word_registers_chat(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    _clear_bootstrap(ctx)
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900003,
                "message": {
                    "message_id": 3,
                    "date": 1,
                    "chat": {
                        "id": ARCHIVE_GROUP,
                        "type": "group",
                        "title": "آرشیو خصوصی",
                    },
                    "from": {
                        "id": OWNER_ID,
                        "is_bot": False,
                        "first_name": "مینا",
                    },
                    "text": "آرشیوم",
                },
            }
        )
    )
    assert ctx.archive_chat_id == ARCHIVE_GROUP
    texts = "\n".join(fake_bale.sent_texts(ARCHIVE_GROUP))
    assert "ثبت شد" in texts


async def test_group_content_opens_wizard_in_group(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    import asyncio

    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900004,
                "message": {
                    "message_id": 11,
                    "date": 1,
                    "chat": {"id": -100200300, "type": "group", "title": "رصد"},
                    "from": {
                        "id": 12345,
                        "is_bot": False,
                        "first_name": "علی",
                    },
                    "text": "این یک متن آزمایشی برای بایگانی است",
                },
            }
        )
    )
    await asyncio.sleep(0.2)
    markup = fake_bale.last_markup(-100200300)
    assert markup is not None
    data = [btn.get("callback_data", "") for row in markup["inline_keyboard"] for btn in row]
    assert any("|yes|" in item for item in data)
