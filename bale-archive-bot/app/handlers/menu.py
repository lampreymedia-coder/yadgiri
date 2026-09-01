"""Public command menu: every button and slash command returns real content."""

from __future__ import annotations

from sqlalchemy import func, select

from app.bale.keyboards import button, keyboard, parse_callback, reply_keyboard, url_button
from app.bale.models import (
    CallbackQuery,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyMarkup,
)
from app.core.context import BotContext
from app.db.models import IN_PROGRESS_STATUSES, Submission, SubmissionStatus
from app.db.repositories.groups import GroupRepository
from app.db.repositories.submissions import SubmissionRepository
from app.db.repositories.tags import TagRepository
from app.db.repositories.users import UserRepository
from app.domain.group_roles import ROLE_ARCHIVE, ROLE_RESEARCH, group_role, tag_slug_of
from app.i18n import fa
from app.observability.logging import get_logger

logger = get_logger(__name__)

MENU_ACTIONS = {"mn"}
ACT_HOW = "how"
ACT_TAGS = "tags"
ACT_MY = "my"
ACT_RESUME = "res"
ACT_STATUS = "st"
ACT_ID = "id"
ACT_PANEL = "pnl"


def main_menu_keyboard(ctx: BotContext, *, is_admin: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            button(fa.BTN_MENU_HOW, "mn", "", ACT_HOW),
            button(fa.BTN_MENU_TAGS, "mn", "", ACT_TAGS),
        ],
        [
            button(fa.BTN_MENU_MY, "mn", "", ACT_MY),
            button(fa.BTN_MENU_RESUME, "mn", "", ACT_RESUME),
        ],
        [
            button(fa.BTN_MENU_STATUS, "mn", "", ACT_STATUS),
            button(fa.BTN_MENU_ID, "mn", "", ACT_ID),
        ],
    ]
    if is_admin and ctx.bot_username:
        rows.append(
            [
                url_button(
                    fa.BTN_ADD_TO_GROUP,
                    f"https://ble.ir/{ctx.bot_username}?startgroup=start",
                )
            ]
        )
    if is_admin:
        rows.append([button(fa.BTN_MENU_PANEL, "mn", "", ACT_PANEL)])
    return keyboard(rows)


def persistent_reply_keyboard(ctx: BotContext, *, is_admin: bool) -> ReplyKeyboardMarkup:
    """Bottom-of-chat command bar for private conversations only."""
    rows: list[list[KeyboardButton]] = [
        [
            KeyboardButton(text=fa.BTN_MENU_HOW),
            KeyboardButton(text=fa.BTN_MENU_TAGS),
        ],
        [
            KeyboardButton(text=fa.BTN_MENU_MY),
            KeyboardButton(text=fa.BTN_MENU_RESUME),
        ],
        [
            KeyboardButton(text=fa.BTN_MENU_STATUS),
            KeyboardButton(text=fa.BTN_MENU_ID),
        ],
    ]
    if is_admin:
        if ctx.bot_username:
            rows.append([KeyboardButton(text=fa.BTN_ADD_TO_GROUP)])
        rows.append([KeyboardButton(text=fa.BTN_MENU_PANEL)])
    return reply_keyboard(rows)


def chrome_markup(ctx: BotContext, *, is_admin: bool, private: bool) -> ReplyMarkup:
    """Private chats get the persistent bar; groups keep an inline menu."""
    if private:
        return persistent_reply_keyboard(ctx, is_admin=is_admin)
    return main_menu_keyboard(ctx, is_admin=is_admin)


def add_to_group_markup(ctx: BotContext) -> InlineKeyboardMarkup | None:
    if not ctx.bot_username:
        return None
    return keyboard(
        [
            [
                url_button(
                    fa.BTN_ADD_TO_GROUP,
                    f"https://ble.ir/{ctx.bot_username}?startgroup=start",
                )
            ]
        ]
    )


async def _is_admin(ctx: BotContext, bale_user_id: int) -> bool:
    if ctx.is_runtime_admin(bale_user_id):
        return True
    async with ctx.db.session() as session:
        user = await UserRepository(session).get_by_bale_id(bale_user_id)
    return bool(user is not None and user.is_admin)


async def send_menu(ctx: BotContext, chat_id: int, user_id: int, *, private: bool) -> None:
    admin = await _is_admin(ctx, user_id)
    await ctx.api.send_message(
        chat_id, fa.MENU_HEADER, chrome_markup(ctx, is_admin=admin, private=private)
    )


async def send_help(ctx: BotContext, chat_id: int, user_id: int, *, private: bool) -> None:
    admin = await _is_admin(ctx, user_id)
    await ctx.api.send_message(
        chat_id,
        fa.help_message(is_admin=admin),
        chrome_markup(ctx, is_admin=admin, private=private),
    )


async def send_add_to_group(ctx: BotContext, chat_id: int) -> None:
    markup = add_to_group_markup(ctx)
    if markup is None:
        await ctx.api.send_message(chat_id, fa.ADD_TO_GROUP_UNAVAILABLE)
        return
    url = f"https://ble.ir/{ctx.bot_username}?startgroup=start"
    await ctx.api.send_message(chat_id, fa.add_to_group_invite(url), markup)


async def send_public_tags(ctx: BotContext, chat_id: int) -> None:
    async with ctx.db.session() as session:
        tags = await TagRepository(session).list_active()
    if not tags:
        await ctx.api.send_message(chat_id, fa.TAGS_EMPTY)
        return
    lines = [fa.TAGS_PUBLIC_HEADER, fa.REPORT_DIVIDER, fa.TAGS_INTRO, ""]
    for tag in tags:
        hint = (tag.description or "").strip() or fa.SEED_TAG_HINTS.get(tag.slug, "")
        lines.append(fa.public_tag_line(tag.title_fa, tag.hashtag, hint))
    await ctx.api.send_message(chat_id, "\n".join(lines))


async def send_status(ctx: BotContext, chat_id: int) -> None:
    async with ctx.db.session() as session:
        groups = await GroupRepository(session).list_active()
        tags = await TagRepository(session).list_active()
        pending = int(
            await session.scalar(
                select(func.count())
                .select_from(Submission)
                .where(Submission.status.in_(IN_PROGRESS_STATUSES))
            )
            or 0
        )
    research = [g for g in groups if group_role(g) == ROLE_RESEARCH]
    archives = [g for g in groups if group_role(g) == ROLE_ARCHIVE]
    bound_slugs = {tag_slug_of(g) for g in archives if tag_slug_of(g)}
    missing = [t.hashtag for t in tags if t.slug not in bound_slugs]
    await ctx.api.send_message(
        chat_id,
        fa.status_report(
            ctx.bot_username,
            len(research),
            len(bound_slugs),
            len(tags),
            missing,
            pending,
        ),
    )


async def send_id_card(ctx: BotContext, message: Message) -> None:
    if message.from_user is None:
        return
    title = message.chat.title or ""
    name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip() or (
        message.from_user.username or ""
    )
    await ctx.api.send_message(
        message.chat.id,
        fa.id_card(
            message.from_user.id,
            name,
            message.from_user.username,
            message.chat.id,
            title,
            message.is_private_message,
        ),
    )


async def send_my_list(ctx: BotContext, chat_id: int, bale_user_id: int) -> None:
    async with ctx.db.session() as session:
        user = await UserRepository(session).get_by_bale_id(bale_user_id)
        if user is None:
            await ctx.api.send_message(chat_id, fa.MY_EMPTY)
            return
        items = await SubmissionRepository(session).list_recent_by_user(user.id, limit=10)
        if not items:
            await ctx.api.send_message(chat_id, fa.MY_EMPTY)
            return
        lines = [fa.MY_HEADER, fa.REPORT_DIVIDER]
        lines.extend(
            fa.my_item_line(
                s.short_id, s.content_type.value, fa.status_name(s.status.value), s.created_at
            )
            for s in items
        )
        lines.append("")
        lines.append(fa.UNDO_USAGE)
    await ctx.api.send_message(chat_id, "\n".join(lines))


async def send_undo_help(ctx: BotContext, chat_id: int, bale_user_id: int) -> None:
    async with ctx.db.session() as session:
        user = await UserRepository(session).get_by_bale_id(bale_user_id)
        lines = [fa.UNDO_USAGE]
        if user is not None:
            items = await SubmissionRepository(session).list_recent_by_user(user.id, limit=5)
            completed = [s for s in items if s.status is SubmissionStatus.COMPLETED]
            if completed:
                lines.append("")
                lines.append(fa.MY_HEADER)
                lines.extend(
                    fa.my_item_line(
                        s.short_id,
                        s.content_type.value,
                        fa.status_name(s.status.value),
                        s.created_at,
                    )
                    for s in completed
                )
            else:
                lines.append("")
                lines.append(fa.UNDO_NONE_RECENT)
    await ctx.api.send_message(chat_id, "\n".join(lines))


async def handle_menu_callback(ctx: BotContext, cq: CallbackQuery) -> None:
    data = parse_callback(cq.data or "")
    chat_id = cq.message.chat.id if cq.message is not None else cq.from_user.id
    user_id = cq.from_user.id
    private = cq.message.is_private_message if cq.message is not None else True
    if data.arg == ACT_HOW:
        await send_help(ctx, chat_id, user_id, private=private)
    elif data.arg == ACT_TAGS:
        await send_public_tags(ctx, chat_id)
    elif data.arg == ACT_MY:
        await send_my_list(ctx, chat_id, user_id)
    elif data.arg == ACT_RESUME:
        from app.handlers.wizard import resume_wizard

        if cq.message is None:
            await ctx.api.send_message(chat_id, fa.RESUME_NOTHING)
        else:
            async with ctx.db.session() as session:
                resumed = await resume_wizard(ctx, session, cq.message, user_id=cq.from_user.id)
            if not resumed:
                await ctx.api.send_message(chat_id, fa.RESUME_NOTHING)
    elif data.arg == ACT_STATUS:
        await send_status(ctx, chat_id)
    elif data.arg == ACT_ID:
        if cq.message is not None:
            fake = cq.message
            # Callback message is the bot's own menu; report the tapper + this chat.
            await ctx.api.send_message(
                chat_id,
                fa.id_card(
                    user_id,
                    cq.from_user.first_name or "",
                    cq.from_user.username,
                    chat_id,
                    fake.chat.title or "",
                    fake.is_private_message,
                ),
            )
        else:
            await send_menu(ctx, chat_id, user_id, private=private)
    elif data.arg == ACT_PANEL:
        if await _is_admin(ctx, user_id):
            from app.handlers.admin import send_panel

            await send_panel(ctx, chat_id)
        else:
            await ctx.api.send_message(chat_id, fa.ERR_NOT_YOURS)
    else:
        await send_menu(ctx, chat_id, user_id, private=private)

    if ctx.caps.has("answerCallbackQuery"):
        from app.bale.errors import BaleAPIError, NetworkError

        try:
            await ctx.api.answer_callback_query(cq.id)
        except (BaleAPIError, NetworkError) as exc:
            logger.info("menu_answer_callback_failed", error=str(exc))
