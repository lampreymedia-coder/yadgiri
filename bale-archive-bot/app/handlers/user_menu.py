"""Regular user's private chat: my posts, my stats, undo the last post, help."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from app.bale.errors import BaleAPIError, NetworkError
from app.bale.keyboards import button, keyboard, reply_keyboard
from app.bale.models import CallbackQuery, KeyboardButton, ReplyKeyboardMarkup
from app.core.context import BotContext
from app.db import repo
from app.domain.reports import PostFilter, build_report
from app.i18n import fa
from app.observability.logging import get_logger
from app.timeutil import tehran_now

logger = get_logger(__name__)

ACT_UNDO = "un"
UNDO_MINUTES = 10


def main_keyboard(is_admin: bool) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=fa.BTN_MY_POSTS), KeyboardButton(text=fa.BTN_MY_STATS)],
        [KeyboardButton(text=fa.BTN_UNDO_LAST), KeyboardButton(text=fa.BTN_HELP)],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=fa.BTN_ADMIN_PANEL)])
    return reply_keyboard(rows)


async def _send(ctx: BotContext, chat_id: int, body: str, markup: object = None) -> None:
    try:
        await ctx.api.send_message(chat_id, body, markup)  # type: ignore[arg-type]
    except (BaleAPIError, NetworkError) as exc:
        logger.info("user_menu_send_failed", chat_id=chat_id, error=str(exc))


async def send_start(ctx: BotContext, user_id: int) -> None:
    await _send(ctx, user_id, fa.START, main_keyboard(ctx.is_admin(user_id)))


async def send_help(ctx: BotContext, user_id: int) -> None:
    body = fa.HELP
    if ctx.is_admin(user_id):
        body = f"{body}\n\n{fa.ADMIN_HELP}"
    await _send(ctx, user_id, body, main_keyboard(ctx.is_admin(user_id)))


async def _person_id(ctx: BotContext, user_id: int) -> int | None:
    async with ctx.db.tx() as conn:
        person = await repo.get_person(conn, user_id)
    return person.id if person is not None else None


async def send_my_posts(ctx: BotContext, user_id: int) -> None:
    person_id = await _person_id(ctx, user_id)
    posts: list[repo.OwnPost] = []
    if person_id is not None:
        async with ctx.db.tx() as conn:
            posts = await repo.own_posts(conn, person_id)
    await _send(ctx, user_id, fa.my_posts(posts))


async def send_my_stats(ctx: BotContext, user_id: int) -> None:
    person_id = await _person_id(ctx, user_id)
    if person_id is None:
        await _send(ctx, user_id, fa.NOTHING_YET)
        return
    async with ctx.db.tx() as conn:
        report = await build_report(conn, flt=PostFilter(person_id=person_id))
    await _send(ctx, user_id, fa.scoped_report("📊 آمار من", report))


def _undo_deadline_ok(created_at: object) -> bool:
    return created_at is not None and tehran_now() - created_at <= timedelta(minutes=UNDO_MINUTES)  # type: ignore[operator]


async def ask_undo(ctx: BotContext, user_id: int) -> None:
    person_id = await _person_id(ctx, user_id)
    posts: list[repo.OwnPost] = []
    if person_id is not None:
        async with ctx.db.tx() as conn:
            posts = await repo.own_posts(conn, person_id, limit=1)
    if not posts or not _undo_deadline_ok(posts[0].created_at):
        await _send(ctx, user_id, fa.UNDO_NOTHING)
        return
    post = posts[0]
    markup = keyboard(
        [
            [button(fa.BTN_UNDO_CONFIRM, ACT_UNDO, "", str(post.id))],
            [button(fa.BTN_UNDO_KEEP, ACT_UNDO, "", "0")],
        ]
    )
    await _send(ctx, user_id, fa.undo_question(post), markup)


def _remove_files(ctx: BotContext, paths: list[str]) -> int:
    """Delete local copies (never a bale: reference, never outside the media folder)."""
    root = ctx.settings.media_root.resolve()
    removed = 0
    for raw in paths:
        if raw.startswith("bale:"):
            continue
        path = Path(raw).resolve()
        if root not in path.parents:
            logger.warning("undo_file_outside_media", path=raw)
            continue
        try:
            path.unlink(missing_ok=True)
            removed += 1
        except OSError as exc:
            logger.warning("undo_file_delete_failed", path=raw, error=str(exc))
    return removed


async def handle_undo_callback(ctx: BotContext, cq: CallbackQuery, arg: str) -> None:
    user_id = cq.from_user.id
    try:
        await ctx.api.answer_callback_query(cq.id)
    except (BaleAPIError, NetworkError) as exc:
        logger.info("answer_callback_failed", error=str(exc))
    if cq.message is not None:
        try:
            await ctx.api.delete_message(cq.message.chat.id, cq.message.message_id)
        except (BaleAPIError, NetworkError) as exc:
            logger.info("undo_prompt_delete_failed", error=str(exc))
    if not arg.isdigit() or arg == "0":
        return
    post_id = int(arg)
    person_id = await _person_id(ctx, user_id)
    if person_id is None:
        logger.info("callback_dropped", reason="undo_unknown_person", actor=user_id)
        return
    async with ctx.db.tx() as conn:
        mine = [p for p in await repo.own_posts(conn, person_id, limit=1) if p.id == post_id]
        if not mine or not _undo_deadline_ok(mine[0].created_at):
            paths = None
        else:
            paths = await repo.delete_own_post(conn, post_id, person_id)
    if paths is None:
        await _send(ctx, user_id, fa.UNDO_TOO_LATE)
        return
    removed = _remove_files(ctx, paths)
    ctx.compression_log.forget_paths(paths)
    logger.info("post_undone", post_id=post_id, user_id=user_id, files_removed=removed)
    await _send(ctx, user_id, fa.UNDO_DONE)
