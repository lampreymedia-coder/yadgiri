"""Public slash commands and menu buttons always return useful content."""

from __future__ import annotations

from app.bale.models import Update
from app.core.context import BotContext
from app.core.dispatcher import Dispatcher
from app.i18n import fa
from tests.e2e.test_wizard_flow import USER_ID, load_update
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


def _reply_labels(markup: dict | None) -> list[str]:
    return FakeBaleServer.markup_labels(markup)


async def test_help_explains_how_the_bot_works(ctx: BotContext, fake_bale: FakeBaleServer) -> None:
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(_private("/help"))
    body = "\n".join(fake_bale.sent_texts(USER_ID))
    assert "نحوه کار" in body
    assert "تصویر هم ذخیره شود" in body
    assert "/tags" in body
    markup = fake_bale.last_markup(USER_ID)
    assert markup is not None
    assert "keyboard" in markup
    labels = _reply_labels(markup)
    assert fa.BTN_MENU_HOW in labels
    assert fa.BTN_MENU_TAGS in labels
    assert fa.BTN_MENU_MY in labels
    assert fa.BTN_MENU_RESUME in labels
    assert fa.BTN_MENU_STATUS in labels
    assert fa.BTN_MENU_ID in labels
    assert fa.BTN_ADD_TO_GROUP not in labels
    assert fa.BTN_MENU_PANEL not in labels


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
    assert "keyboard" in markup
    assert fa.BTN_MENU_HOW in _reply_labels(markup)


async def test_start_private_attaches_reply_keyboard(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(_private("/start"))
    markup = fake_bale.last_markup(USER_ID)
    assert markup is not None
    assert "keyboard" in markup
    assert markup.get("resize_keyboard") is True
    assert "inline_keyboard" not in markup
    await dispatcher.dispatch(_private(fa.BTN_MENU_HOW))
    assert any("نحوه کار" in t for t in fake_bale.sent_texts(USER_ID))


async def test_reply_keyboard_labels_route_to_real_replies(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(_private(fa.BTN_MENU_TAGS))
    await dispatcher.dispatch(_private(fa.BTN_MENU_STATUS))
    await dispatcher.dispatch(_private(fa.BTN_MENU_ID))
    await dispatcher.dispatch(_private(fa.BTN_MENU_MY))
    await dispatcher.dispatch(_private(fa.BTN_RESTART))
    texts = "\n".join(fake_bale.sent_texts(USER_ID))
    assert "یادگیری" in texts
    assert "روشن است" in texts
    assert fa.fa_digits(USER_ID) in texts
    assert fa.MY_EMPTY in texts or "ثبت" in texts
    assert any("دکمه‌های پایین صفحه" in t for t in fake_bale.sent_texts(USER_ID))


async def test_group_help_uses_inline_not_reply_keyboard(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(_group("/help"))
    assert any("نحوه کار" in t for t in fake_bale.sent_texts(GROUP_ID))
    markup = fake_bale.last_markup(GROUP_ID)
    assert markup is not None
    assert "inline_keyboard" in markup
    assert "keyboard" not in markup


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


async def test_admin_reply_keyboard_includes_panel_and_add_group(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    ctx.runtime_admin_ids = {USER_ID}
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(_private("/start"))
    labels = _reply_labels(fake_bale.last_markup(USER_ID))
    assert fa.BTN_MENU_PANEL in labels
    assert fa.BTN_ADD_TO_GROUP in labels
    await dispatcher.dispatch(_private(fa.BTN_ADD_TO_GROUP))
    texts = "\n".join(fake_bale.sent_texts(USER_ID))
    assert "ble.ir" in texts
    markup = fake_bale.last_markup(USER_ID)
    assert markup is not None
    assert "inline_keyboard" in markup
