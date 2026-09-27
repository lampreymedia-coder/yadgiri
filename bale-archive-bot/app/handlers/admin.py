"""Admin commands. Admins come from ADMIN_USER_IDS (.env) and admins.json.

Group side: /register (asks the level 1–7 with buttons) and /unregister.
Private side: /groups, /stats, /admins, /addadmin, /removeadmin.
Admin actions are recorded only in the log file.
"""

from __future__ import annotations

from app.bale.errors import BaleAPIError, NetworkError
from app.bale.keyboards import button, grid, keyboard
from app.bale.models import CallbackQuery, Message
from app.core.context import BotContext
from app.db import repo
from app.domain.reports import build_report
from app.i18n import fa
from app.observability.logging import get_logger

logger = get_logger(__name__)

ACT_LEVEL = "lv"
LEVELS = range(1, 8)


async def _send(ctx: BotContext, chat_id: int, text: str, **kwargs: object) -> None:
    try:
        await ctx.api.send_message(chat_id, text, **kwargs)  # type: ignore[arg-type]
    except (BaleAPIError, NetworkError) as exc:
        logger.warning("admin_send_failed", chat_id=chat_id, error=str(exc))


def level_keyboard(chat_id: int) -> object:
    """The group id rides in callback_data, so the tap works even without cq.message."""
    return keyboard(
        grid(
            [button(fa.fa_digits(level), ACT_LEVEL, str(chat_id), str(level)) for level in LEVELS],
            4,
        )
    )


# ─── Group commands ───


async def handle_group_command(ctx: BotContext, message: Message, command: str) -> None:
    """/register and /unregister inside a group. Non-admins get silence."""
    assert message.from_user is not None
    actor = message.from_user.id
    if not ctx.is_admin(actor):
        return
    chat_id = message.chat.id
    if ctx.archive_chat_id is not None and chat_id == ctx.archive_chat_id:
        await _send(ctx, chat_id, fa.REGISTER_ARCHIVE_REFUSED, is_group=True)
        return
    if command == "register":
        await _send(
            ctx,
            chat_id,
            fa.REGISTER_PICK_LEVEL,
            reply_markup=level_keyboard(chat_id),
            is_group=True,
        )
        logger.info("admin_action", action="register_started", actor=actor, chat_id=chat_id)
        return
    if command == "unregister":
        async with ctx.db.tx() as conn:
            existing = await repo.get_group(conn, chat_id)
            changed = await repo.unregister_group(conn, chat_id)
        if changed and existing is not None:
            await _send(ctx, chat_id, fa.unregister_done(existing.name), is_group=True)
        else:
            await _send(ctx, chat_id, fa.UNREGISTER_NOT_FOUND, is_group=True)
        logger.info(
            "admin_action", action="unregister", actor=actor, chat_id=chat_id, changed=changed
        )


async def handle_level_callback(ctx: BotContext, cq: CallbackQuery, sid: str, arg: str) -> None:
    """Level tap after /register. Deliberately NOT behind the unregistered-group silence."""
    actor = cq.from_user.id
    chat_id: int | None = None
    if sid.lstrip("-").isdigit():
        chat_id = int(sid)
    elif cq.message is not None:
        chat_id = cq.message.chat.id
    if chat_id is None:
        logger.info("callback_dropped", reason="level_without_chat", actor=actor, data=cq.data)
        await _answer(ctx, cq)
        return
    if not ctx.is_admin(actor):
        logger.info("callback_dropped", reason="level_not_admin", actor=actor, chat_id=chat_id)
        await _answer(ctx, cq, fa.REGISTER_ONLY_ADMIN)
        return
    if not arg.isdigit() or int(arg) not in LEVELS:
        logger.info("callback_dropped", reason="level_invalid", actor=actor, arg=arg)
        await _answer(ctx, cq)
        return
    if chat_id == actor or (cq.message is not None and cq.message.is_private_message):
        logger.info("callback_dropped", reason="level_in_private_chat", actor=actor)
        await _answer(ctx, cq, fa.REGISTER_IN_GROUP_ONLY)
        return
    if ctx.archive_chat_id is not None and chat_id == ctx.archive_chat_id:
        logger.info("callback_dropped", reason="level_archive_group", actor=actor)
        await _answer(ctx, cq, fa.REGISTER_ARCHIVE_REFUSED)
        return
    level = int(arg)
    name = cq.message.chat.title if cq.message is not None else None
    if not name:
        try:
            name = (await ctx.api.get_chat(chat_id)).title
        except (BaleAPIError, NetworkError) as exc:
            logger.info("register_get_chat_failed", chat_id=chat_id, error=str(exc))
    name = name or str(chat_id)
    async with ctx.db.tx() as conn:
        group = await repo.register_group(conn, chat_id, name, level)
    await _answer(ctx, cq)
    logger.info("admin_action", action="register", actor=actor, chat_id=chat_id, level=level)
    text = fa.register_done(group.name, group.level)
    try:
        if cq.message is not None:
            await ctx.api.safe_edit(chat_id, cq.message.message_id, text, None, is_group=True)
        else:
            await ctx.api.send_message(chat_id, text, is_group=True)
    except (BaleAPIError, NetworkError) as exc:
        logger.info("register_edit_failed", error=str(exc))


async def _answer(ctx: BotContext, cq: CallbackQuery, text: str | None = None) -> None:
    try:
        await ctx.api.answer_callback_query(cq.id, text)
    except (BaleAPIError, NetworkError) as exc:
        logger.info("answer_callback_failed", error=str(exc))


# ─── Private commands ───

PRIVATE_ADMIN_COMMANDS = {
    "groups",
    "stats",
    "admins",
    "addadmin",
    "removeadmin",
    "transferowner",
    "admin",
    "panel",
}


async def handle_private_command(
    ctx: BotContext, message: Message, command: str, args: list[str]
) -> None:
    from app.handlers import panel

    assert message.from_user is not None
    chat_id = message.chat.id
    actor = message.from_user.id
    if not ctx.is_admin(actor):
        await _send(ctx, chat_id, fa.UNKNOWN_COMMAND)
        return
    logger.info("admin_action", action=command, actor=actor, args=args)

    if command in {"admin", "panel"}:
        await panel.open_home(ctx, chat_id, actor)
    elif command == "groups":
        async with ctx.db.tx() as conn:
            groups = await repo.list_groups(conn)
        rows = [(g.name, g.bale_group_id, g.level, g.is_active) for g in groups]
        await _send(ctx, chat_id, fa.groups_list(rows))
    elif command == "stats":
        async with ctx.db.tx() as conn:
            report = await build_report(conn)
        await _send(ctx, chat_id, fa.report_text(report))
    elif command == "admins":
        await panel.screen_admins(ctx, chat_id, actor, None)
    elif command in {"addadmin", "removeadmin", "transferowner"}:
        target = _parse_id(args)
        if target is None:
            usage = {
                "addadmin": fa.ADMIN_USAGE_ADD,
                "removeadmin": fa.ADMIN_USAGE_REMOVE,
                "transferowner": fa.OWNER_USAGE,
            }[command]
            await _send(ctx, chat_id, usage)
            return
        action = {
            "addadmin": panel.add_admin,
            "removeadmin": panel.remove_admin,
            "transferowner": panel.transfer_owner,
        }[command]
        await _send(ctx, chat_id, action(ctx, actor, target))


def _parse_id(args: list[str]) -> int | None:
    if not args:
        return None
    raw = args[0].strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    return int(raw) if raw.isdigit() else None
