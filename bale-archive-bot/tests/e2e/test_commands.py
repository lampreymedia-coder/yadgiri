"""Public slash commands and menu buttons always return useful content."""

from __future__ import annotations

from app.bale.models import Update
from app.core.context import BotContext
from app.core.dispatcher import Dispatcher
from app.i18n import fa
from tests.e2e.test_wizard_flow import USER_ID, callback_update, load_update
from tests.fakes.fake_bale import FakeBaleServer

GROUP_ID = -100200300


def _private(text: str) -> Update:
    payload = load_update("text")
    payload["message"]["chat"] = {"id": USER_ID, "type": "private"}
    payload["message"]["text"] = text
    return Update.model_validate(payload)


def _group(text: str) -> Update:
    payload = load_update("text")
    payload["message"]["text"] = text
    return Update.model_validate(payload)


async def test_help_explains_how_the_bot_works(ctx: BotContext, fake_bale: FakeBaleServer) -> None:
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(_private("/help"))
    body = "\n".join(fake_bale.sent_texts(USER_ID))
    assert "نحوه کار" in body
    assert "تصویر هم ذخیره شود" in body
    assert "/tags" in body
    markup = fake_bale.last_markup(USER_ID)
    assert markup is not None
    labels = [btn["text"] for row in markup["inline_keyboard"] for btn in row]
    assert fa.BTN_MENU_HOW in labels
    assert fa.BTN_MENU_TAGS in labels


async def test_tags_status_id_and_menu_are_not_empty(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(_private("/tags"))
    await dispatcher.dispatch(_private("/status"))
    await dispatcher.dispatch(_private("/id"))
    await dispatcher.dispatch(_private("/menu"))
    texts = "\n".join(fake_bale.sent_texts(USER_ID))
    assert "یادگیری" in texts
    assert "#سند" in texts
    assert "روشن است" in texts
    assert fa.fa_digits(USER_ID) in texts
    assert fa.MENU_HEADER in texts
    markup = fake_bale.last_markup(USER_ID)
    assert markup is not None
    assert any(
        "|mn|" in (btn.get("callback_data") or "")
        for row in markup["inline_keyboard"]
        for btn in row
    )


async def test_start_private_has_working_menu_buttons(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(_private("/start"))
    markup = fake_bale.last_markup(USER_ID)
    assert markup is not None
    how = next(
        btn["callback_data"]
        for row in markup["inline_keyboard"]
        for btn in row
        if btn["text"] == fa.BTN_MENU_HOW
    )
    await dispatcher.dispatch(callback_update(how, USER_ID, 1000))
    assert any("نحوه کار" in t for t in fake_bale.sent_texts(USER_ID))


async def test_group_help_replies_in_the_group(ctx: BotContext, fake_bale: FakeBaleServer) -> None:
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(_group("/help"))
    assert any("نحوه کار" in t for t in fake_bale.sent_texts(GROUP_ID))


async def test_undo_without_code_explains_usage(ctx: BotContext, fake_bale: FakeBaleServer) -> None:
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(_private("/undo"))
    assert any("/undo" in t for t in fake_bale.sent_texts(USER_ID))


async def test_persian_help_alias(ctx: BotContext, fake_bale: FakeBaleServer) -> None:
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(_private("راهنما"))
    assert any("نحوه کار" in t for t in fake_bale.sent_texts(USER_ID))


async def test_unknown_command_lists_real_commands(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(_private("/nonesuch"))
    body = "\n".join(fake_bale.sent_texts(USER_ID))
    assert "این دستور را ندارم" in body
    assert "/help" in body
