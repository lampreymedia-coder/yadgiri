"""Private-chat admin panel (inline buttons, edited in place).

callback_data: ``1|pa|<screen>|<arg>`` (ASCII, ≤ 64 bytes).
Typed answers (a new hashtag name, an admin id …) wait in memory for 30 min.
Every read is a SELECT on the seven bot tables; hashtag/group changes are
single-row INSERT/UPDATE; admins live only in admins.json.
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import text

from app.bale.errors import BaleAPIError, NetworkError
from app.bale.keyboards import button, keyboard
from app.bale.models import CallbackQuery, InlineKeyboardButton, Message
from app.core.admins import RemoveResult
from app.core.context import BotContext
from app.i18n import fa
from app.observability.logging import get_logger

logger = get_logger(__name__)

ACT_PANEL = "pa"
INPUT_TTL_SECONDS = 30 * 60


def btn(label: str, screen: str, arg: str = "") -> InlineKeyboardButton:
    return button(label, ACT_PANEL, screen, arg)


def back(screen: str = "home") -> list[InlineKeyboardButton]:
    return [btn(fa.BTN_PANEL_BACK, screen)]


async def show(
    ctx: BotContext,
    chat_id: int,
    message_id: int | None,
    body: str,
    rows: list[list[InlineKeyboardButton]],
) -> None:
    markup = keyboard(rows) if rows else None
    try:
        if message_id is not None:
            await ctx.api.safe_edit(chat_id, message_id, body, markup)
        else:
            await ctx.api.send_message(chat_id, body, markup)
    except (BaleAPIError, NetworkError) as exc:
        logger.warning("panel_show_failed", chat_id=chat_id, error=str(exc))


async def say(ctx: BotContext, chat_id: int, body: str) -> None:
    try:
        await ctx.api.send_message(chat_id, body)
    except (BaleAPIError, NetworkError) as exc:
        logger.info("panel_say_failed", chat_id=chat_id, error=str(exc))


# ─── Waiting for typed input ───


def expect_input(ctx: BotContext, user_id: int, kind: str, arg: str = "") -> None:
    ctx.pending_input[user_id] = (kind, arg, time.monotonic())


def take_input(ctx: BotContext, user_id: int) -> tuple[str, str] | None:
    item = ctx.pending_input.pop(user_id, None)
    if item is None:
        return None
    kind, arg, started = item
    if time.monotonic() - started > INPUT_TTL_SECONDS:
        return None
    return kind, arg


def _digits(value: str) -> str:
    return value.strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))


# ─── Home ───


def home_rows(ctx: BotContext, user_id: int) -> list[list[InlineKeyboardButton]]:
    return [[btn(fa.BTN_PANEL_ADMINS, "adm")]]


async def open_home(
    ctx: BotContext, chat_id: int, user_id: int, message_id: int | None = None
) -> None:
    await show(ctx, chat_id, message_id, fa.PANEL_HOME, home_rows(ctx, user_id))


# ─── Admins (2-3) ───


async def screen_admins(
    ctx: BotContext, chat_id: int, user_id: int, message_id: int | None
) -> None:
    body = fa.admins_panel(sorted(ctx.admins.all), ctx.admins.owner, ctx.admins.env_ids)
    rows: list[list[InlineKeyboardButton]] = []
    if ctx.admins.is_owner(user_id):
        rows.append([btn(fa.BTN_ADMIN_ADD_ID, "aid")])
        rows.append([btn(fa.BTN_ADMIN_ADD_FWD, "afw")])
        rows.append([btn(fa.BTN_ADMIN_ADD_PICK, "apk")])
        for admin_id in sorted(ctx.admins.all):
            if admin_id != ctx.admins.owner and admin_id not in ctx.admins.env_ids:
                rows.append([btn(fa.btn_admin_remove(admin_id), "arm", str(admin_id))])
        rows.append([btn(fa.BTN_OWNER_TRANSFER, "aow")])
    else:
        body += "\n\n" + fa.OWNER_ONLY
    rows.append(back())
    await show(ctx, chat_id, message_id, body, rows)


async def _pickable_people(ctx: BotContext) -> list[tuple[int, str]]:
    from app.domain.reports import person_label

    async with ctx.db.tx() as conn:
        result = await conn.execute(
            text(
                "SELECT id, firstname, lastname, bale_username, bale_user_id FROM Person "
                "WHERE bale_user_id IS NOT NULL AND (is_active IS NULL OR is_active = 1) "
                "ORDER BY id DESC LIMIT 40"
            )
        )
        people = [(int(row.bale_user_id), person_label(row)) for row in result]
    return [(uid, label) for uid, label in people if not ctx.admins.is_admin(uid)][:20]


def add_admin(ctx: BotContext, actor: int, target: int) -> str:
    if not ctx.admins.is_owner(actor):
        return fa.OWNER_ONLY
    added = ctx.admins.add(target)
    logger.info("admin_action", action="addadmin", actor=actor, target=target, added=added)
    return fa.admin_added(target) if added else fa.admin_already(target)


def remove_admin(ctx: BotContext, actor: int, target: int) -> str:
    if not ctx.admins.is_owner(actor):
        return fa.OWNER_ONLY
    result = ctx.admins.remove(target)
    logger.info(
        "admin_action", action="removeadmin", actor=actor, target=target, result=result.value
    )
    return {
        RemoveResult.REMOVED: fa.admin_removed(target),
        RemoveResult.NOT_ADMIN: fa.admin_not_found(target),
        RemoveResult.FROM_ENV: fa.admin_from_env(target),
        RemoveResult.IS_OWNER: fa.ADMIN_IS_OWNER,
        RemoveResult.LAST_ADMIN: fa.ADMIN_LAST,
    }[result]


def transfer_owner(ctx: BotContext, actor: int, target: int) -> str:
    if not ctx.admins.is_owner(actor):
        return fa.OWNER_ONLY
    if target == actor:
        return fa.OWNER_ALREADY
    ctx.admins.transfer_owner(target)
    logger.info("admin_action", action="transfer_owner", actor=actor, target=target)
    return fa.owner_transferred(target)


async def _admin_callback(
    ctx: BotContext, chat_id: int, actor: int, message_id: int | None, screen: str, arg: str
) -> bool:
    owner_only = {"aid", "afw", "apk", "apa", "arm", "aow", "aoc", "aox"}
    if screen in owner_only and not ctx.admins.is_owner(actor):
        await say(ctx, chat_id, fa.OWNER_ONLY)
        return True
    if screen == "adm":
        await screen_admins(ctx, chat_id, actor, message_id)
    elif screen == "aid":
        expect_input(ctx, actor, "admin_id")
        await say(ctx, chat_id, fa.ASK_ADMIN_ID)
    elif screen == "afw":
        expect_input(ctx, actor, "admin_forward")
        await say(ctx, chat_id, fa.ASK_ADMIN_FORWARD)
    elif screen == "apk":
        people = await _pickable_people(ctx)
        rows = [[btn(label, "apa", str(uid))] for uid, label in people]
        rows.append(back("adm"))
        await show(ctx, chat_id, message_id, fa.PICK_PERSON if people else fa.NO_PEOPLE, rows)
    elif screen == "apa" and arg.lstrip("-").isdigit():
        await say(ctx, chat_id, add_admin(ctx, actor, int(arg)))
        await screen_admins(ctx, chat_id, actor, message_id)
    elif screen == "arm" and arg.lstrip("-").isdigit():
        await say(ctx, chat_id, remove_admin(ctx, actor, int(arg)))
        await screen_admins(ctx, chat_id, actor, message_id)
    elif screen == "aow":
        rows = [
            [btn(str(admin_id), "aoc", str(admin_id))]
            for admin_id in sorted(ctx.admins.all)
            if admin_id != actor
        ]
        rows.append(back("adm"))
        await show(ctx, chat_id, message_id, fa.PICK_NEW_OWNER, rows)
    elif screen == "aoc" and arg.lstrip("-").isdigit():
        rows = [[btn(fa.BTN_YES_TRANSFER, "aox", arg)], back("adm")]
        await show(ctx, chat_id, message_id, fa.confirm_transfer(int(arg)), rows)
    elif screen == "aox" and arg.lstrip("-").isdigit():
        await say(ctx, chat_id, transfer_owner(ctx, actor, int(arg)))
        await screen_admins(ctx, chat_id, actor, message_id)
    else:
        return False
    return True


# ─── Entry points ───


async def handle_callback(ctx: BotContext, cq: CallbackQuery, screen: str, arg: str) -> None:
    actor = cq.from_user.id
    try:
        await ctx.api.answer_callback_query(cq.id)
    except (BaleAPIError, NetworkError) as exc:
        logger.info("answer_callback_failed", error=str(exc))
    if not ctx.is_admin(actor):
        logger.info("callback_dropped", reason="panel_not_admin", actor=actor)
        return
    chat_id = cq.message.chat.id if cq.message is not None else actor
    message_id = cq.message.message_id if cq.message is not None else None
    if screen == "home":
        await open_home(ctx, chat_id, actor, message_id)
        return
    for handler in _SECTIONS:
        if await handler(ctx, chat_id, actor, message_id, screen, arg):
            return
    logger.info("callback_dropped", reason="panel_unknown_screen", screen=screen)


async def handle_input(ctx: BotContext, message: Message, kind: str, arg: str) -> None:
    """A typed answer the panel asked for."""
    assert message.from_user is not None
    actor = message.from_user.id
    chat_id = message.chat.id
    if not ctx.is_admin(actor):
        return
    body = (message.text or "").strip()
    if kind == "admin_id":
        value = _digits(body)
        if not value.isdigit():
            await say(ctx, chat_id, fa.ADMIN_USAGE_ADD)
            return
        await say(ctx, chat_id, add_admin(ctx, actor, int(value)))
    elif kind == "admin_forward":
        source = message.forward_from
        if source is None:
            await say(ctx, chat_id, fa.FORWARD_HAS_NO_USER)
            return
        await say(ctx, chat_id, add_admin(ctx, actor, source.id))
    else:
        await _handle_more_input(ctx, message, kind, arg)


async def _handle_more_input(ctx: BotContext, message: Message, kind: str, arg: str) -> None:
    logger.info("panel_input_ignored", kind=kind)


_SECTIONS: list[Any] = [_admin_callback]
