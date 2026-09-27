"""Private-chat admin panel (inline buttons, edited in place).

callback_data: ``1|pa|<screen>|<arg>`` (ASCII, ≤ 64 bytes).
Typed answers (a new hashtag name, an admin id …) wait in memory for 30 min.
Every read is a SELECT on the seven bot tables; hashtag/group changes are
single-row INSERT/UPDATE; admins live only in admins.json.
"""

from __future__ import annotations

import time
from datetime import timedelta
from typing import Any

from sqlalchemy import text

from app.bale.errors import BaleAPIError, NetworkError
from app.bale.keyboards import button, keyboard
from app.bale.models import CallbackQuery, InlineKeyboardButton, Message
from app.core.admins import RemoveResult
from app.core.context import BotContext
from app.db import repo
from app.domain.excel import build_workbook
from app.domain.reports import (
    PostFilter,
    Report,
    build_report,
    export_rows,
    person_label,
    today_range,
)
from app.i18n import fa
from app.observability.logging import get_logger
from app.timeutil import tehran_now

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
    return [
        [btn(fa.BTN_PANEL_STATS, "st"), btn(fa.BTN_PANEL_TAG_REPORT, "tr")],
        [btn(fa.BTN_PANEL_USERS, "us"), btn(fa.BTN_PANEL_GROUPS, "gr")],
        [btn(fa.BTN_PANEL_EXPORT, "xl")],
        [btn(fa.BTN_PANEL_TAGS, "hm"), btn(fa.BTN_PANEL_ADMINS, "adm")],
        [btn(fa.BTN_PANEL_DISK, "dk")],
    ]


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
    assert message.from_user is not None
    chat_id = message.chat.id
    name = " ".join((message.text or "").replace("#", " ").replace("_", " ").split())
    if kind not in {"tag_add", "tag_rename"}:
        logger.info("panel_input_ignored", kind=kind)
        return
    if not name or len(name) > 100:
        await say(ctx, chat_id, fa.TAG_NAME_INVALID)
        return
    async with ctx.db.tx() as conn:
        if kind == "tag_add":
            ok = await repo.add_hashtag(conn, name)
        else:
            ok = await repo.rename_hashtag(conn, int(arg), name)
    logger.info("admin_action", action=kind, actor=message.from_user.id, name=name, ok=ok)
    await say(ctx, chat_id, fa.tag_saved(name) if ok else fa.TAG_NAME_TAKEN)
    await _screen_tag_manage(ctx, chat_id, None)


# ─── Reports (2-4) ───


async def _report(ctx: BotContext, flt: PostFilter | None = None, top_n: int = 5) -> Report:
    async with ctx.db.tx() as conn:
        return await build_report(conn, top_n=top_n, flt=flt)


async def _top_people(ctx: BotContext, limit: int = 15) -> list[tuple[int, str, int]]:
    async with ctx.db.tx() as conn:
        result = await conn.execute(
            text(
                "SELECT pe.id, pe.firstname, pe.lastname, pe.bale_username, pe.bale_user_id, "
                "COUNT(p.id) AS n FROM Person pe JOIN Post p ON p.person_id = pe.id "
                "GROUP BY pe.id, pe.firstname, pe.lastname, pe.bale_username, pe.bale_user_id "
                "ORDER BY n DESC, pe.id LIMIT :lim"
            ),
            {"lim": limit},
        )
        return [(int(row.id), person_label(row), int(row.n)) for row in result]


async def _report_callback(
    ctx: BotContext, chat_id: int, actor: int, message_id: int | None, screen: str, arg: str
) -> bool:
    if screen == "st":
        report = await _report(ctx)
        await show(ctx, chat_id, message_id, fa.report_text(report), [back()])
    elif screen == "tr":
        report = await _report(ctx)
        await show(ctx, chat_id, message_id, fa.tag_bars(report), [back()])
    elif screen == "us":
        people = await _top_people(ctx)
        rows = [[btn(f"{label} — {fa.fa_digits(n)}", "usr", str(pid))] for pid, label, n in people]
        rows.append(back())
        await show(ctx, chat_id, message_id, fa.active_users(people), rows)
    elif screen == "usr" and arg.isdigit():
        report = await _report(ctx, PostFilter(person_id=int(arg)))
        name = next(
            (label for pid, label, _ in await _top_people(ctx, 200) if pid == int(arg)), arg
        )
        await show(ctx, chat_id, message_id, fa.scoped_report("👤 " + name, report), [back("us")])
    elif screen == "gr":
        async with ctx.db.tx() as conn:
            groups = await repo.list_groups(conn)
        rows = [[btn(("" if g.is_active else "⛔️ ") + g.name, "grs", str(g.id))] for g in groups]
        rows.append(back())
        await show(ctx, chat_id, message_id, fa.GROUPS_PICK if groups else fa.NO_GROUPS, rows)
    elif screen in {"grs", "grl", "grt"}:
        await _group_screen(ctx, chat_id, actor, message_id, screen, arg)
    elif screen == "dk":
        await show(ctx, chat_id, message_id, await _disk_text(ctx), [back()])
    else:
        return False
    return True


async def _group_screen(
    ctx: BotContext, chat_id: int, actor: int, message_id: int | None, screen: str, arg: str
) -> None:
    group_part, _, value = arg.partition(":")
    if not group_part.isdigit():
        return
    group_id = int(group_part)
    async with ctx.db.tx() as conn:
        if screen == "grl" and value.isdigit() and 1 <= int(value) <= 7:
            await repo.set_group_level(conn, group_id, int(value))
            logger.info(
                "admin_action", action="group_level", actor=actor, group=group_id, level=value
            )
        elif screen == "grt" and value in {"0", "1"}:
            await repo.set_group_active(conn, group_id, value == "1")
            logger.info(
                "admin_action", action="group_active", actor=actor, group=group_id, active=value
            )
        group = await repo.get_group_by_id(conn, group_id)
    if group is None:
        return
    report = await _report(ctx, PostFilter(ehya_group_id=group_id))
    body = (
        fa.group_detail(group.name, group.level, group.is_active)
        + "\n\n"
        + fa.scoped_report("📂 " + group.name, report)
    )
    levels = [
        btn(
            ("✅ " if level == group.level else "") + fa.fa_digits(level),
            "grl",
            f"{group_id}:{level}",
        )
        for level in range(1, 8)
    ]
    toggle = (
        btn(fa.BTN_GROUP_DISABLE, "grt", f"{group_id}:0")
        if group.is_active
        else btn(fa.BTN_GROUP_ENABLE, "grt", f"{group_id}:1")
    )
    rows = [levels[:4], levels[4:], [toggle], back("gr")]
    await show(ctx, chat_id, message_id, body, rows)


async def _disk_text(ctx: BotContext) -> str:
    import asyncio
    import shutil

    root = ctx.settings.data_path
    media = ctx.settings.media_root

    def measure() -> tuple[int, int, int, int]:
        usage = shutil.disk_usage(root if root.exists() else "/")
        size = files = 0
        if media.exists():
            for path in media.rglob("*"):
                if path.is_file():
                    files += 1
                    size += path.stat().st_size
        return usage.total, usage.free, size, files

    total, free, media_size, files = await asyncio.to_thread(measure)
    before, after = ctx.compression_log.totals()
    return fa.disk_status(total, free, media_size, files) + fa.compression_line(before, after)


# ─── Excel export (2-4) ───


async def _export_callback(
    ctx: BotContext, chat_id: int, actor: int, message_id: int | None, screen: str, arg: str
) -> bool:
    if screen == "xl":
        rows = [
            [btn(fa.BTN_EXPORT_ALL, "xa")],
            [btn(fa.BTN_EXPORT_TAG, "xh"), btn(fa.BTN_EXPORT_GROUP, "xg")],
            [btn(fa.BTN_EXPORT_RANGE, "xr")],
            back(),
        ]
        await show(ctx, chat_id, message_id, fa.EXPORT_MENU, rows)
    elif screen == "xh":
        async with ctx.db.tx() as conn:
            tags = await repo.all_hashtags(conn)
        rows = [[btn(fa.hashtag_label(name), "xhs", str(tag_id))] for tag_id, name, _ in tags]
        rows.append(back("xl"))
        await show(ctx, chat_id, message_id, fa.EXPORT_PICK_TAG, rows)
    elif screen == "xg":
        async with ctx.db.tx() as conn:
            groups = await repo.list_groups(conn)
        rows = [[btn(g.name, "xgs", str(g.id))] for g in groups]
        rows.append(back("xl"))
        await show(ctx, chat_id, message_id, fa.EXPORT_PICK_GROUP, rows)
    elif screen == "xr":
        rows = [
            [btn(fa.range_label(days), "xrs", str(days)) for days in (1, 7)],
            [btn(fa.range_label(days), "xrs", str(days)) for days in (30, 365)],
            back("xl"),
        ]
        await show(ctx, chat_id, message_id, fa.EXPORT_PICK_RANGE, rows)
    elif screen == "xa":
        await send_export(ctx, chat_id, PostFilter(), "همه")
    elif screen == "xhs" and arg.isdigit():
        await send_export(ctx, chat_id, PostFilter(hashtag_id=int(arg)), "هشتگ")
    elif screen == "xgs" and arg.isdigit():
        await send_export(ctx, chat_id, PostFilter(ehya_group_id=int(arg)), "گروه")
    elif screen == "xrs" and arg.isdigit():
        start, end = today_range()
        flt = PostFilter(start=start - timedelta(days=int(arg) - 1), end=end)
        await send_export(ctx, chat_id, flt, fa.range_label(int(arg)))
    else:
        return False
    return True


async def send_export(ctx: BotContext, chat_id: int, flt: PostFilter, label: str) -> bool:
    async with ctx.db.tx() as conn:
        rows = await export_rows(conn, flt)
    if not rows:
        await say(ctx, chat_id, fa.EXPORT_EMPTY)
        return False
    data = build_workbook(rows)
    file_name = f"archive-{tehran_now():%Y%m%d-%H%M}.xlsx"
    try:
        await ctx.api.send_document(
            chat_id, data, caption=fa.export_caption(label, len(rows)), file_name=file_name
        )
    except (BaleAPIError, NetworkError) as exc:
        logger.warning("export_send_failed", error=str(exc))
        await say(ctx, chat_id, fa.EXPORT_FAILED)
        return False
    logger.info("admin_action", action="export", chat_id=chat_id, rows=len(rows), label=label)
    return True


# ─── Hashtag management (2-4) ───


async def _screen_tag_manage(ctx: BotContext, chat_id: int, message_id: int | None) -> None:
    async with ctx.db.tx() as conn:
        tags = await repo.all_hashtags(conn)
    rows: list[list[InlineKeyboardButton]] = []
    for tag_id, name, active in tags:
        rows.append(
            [
                btn(("✅ " if active else "⛔️ ") + name, "ht", f"{tag_id}:{0 if active else 1}"),
                btn(fa.BTN_TAG_RENAME, "hr", str(tag_id)),
            ]
        )
    rows.append([btn(fa.BTN_TAG_ADD, "ha")])
    rows.append(back())
    await show(ctx, chat_id, message_id, fa.TAG_MANAGE, rows)


async def _tag_callback(
    ctx: BotContext, chat_id: int, actor: int, message_id: int | None, screen: str, arg: str
) -> bool:
    if screen == "hm":
        await _screen_tag_manage(ctx, chat_id, message_id)
    elif screen == "ha":
        expect_input(ctx, actor, "tag_add")
        await say(ctx, chat_id, fa.ASK_TAG_NAME)
    elif screen == "hr" and arg.isdigit():
        expect_input(ctx, actor, "tag_rename", arg)
        await say(ctx, chat_id, fa.ASK_TAG_RENAME)
    elif screen == "ht":
        tag_part, _, value = arg.partition(":")
        if tag_part.isdigit() and value in {"0", "1"}:
            async with ctx.db.tx() as conn:
                await repo.set_hashtag_active(conn, int(tag_part), value == "1")
            logger.info(
                "admin_action", action="tag_active", actor=actor, tag=tag_part, active=value
            )
        await _screen_tag_manage(ctx, chat_id, message_id)
    else:
        return False
    return True


_SECTIONS: list[Any] = [_admin_callback, _report_callback, _export_callback, _tag_callback]
