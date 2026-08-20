"""Non-admin commands: /start /help /my /undo /resume."""

from __future__ import annotations

from app.bale.models import Message
from app.core.context import BotContext
from app.db.models import Group
from app.db.repositories.users import UserRepository
from app.handlers.wizard import resume_wizard
from app.i18n import fa
from app.observability.logging import get_logger

logger = get_logger(__name__)


async def handle_start(ctx: BotContext, message: Message) -> None:
    if message.from_user is None:
        return
    async with ctx.db.session() as session:
        users = UserRepository(session)
        user = await users.upsert_from_bale(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
            message.from_user.last_name,
        )
        await users.set_private_chat(user.id, True)
        name = user.display_name or user.username or ""
        from app.handlers.admin import promote_first_owner

        promoted = await promote_first_owner(ctx, session, message.from_user)
        if promoted or (ctx.is_runtime_admin(message.from_user.id) and ctx.archive_chat_id is None):
            text = fa.start_owner_setup(name)
        else:
            text = fa.start_message(name)
    await ctx.api.send_message(message.chat.id, text)


async def handle_help(ctx: BotContext, message: Message) -> None:
    await ctx.api.send_message(message.chat.id, fa.HELP_MESSAGE)


async def handle_my(ctx: BotContext, message: Message) -> None:
    if message.from_user is None:
        return
    async with ctx.db.session() as session:
        users = UserRepository(session)
        user = await users.get_by_bale_id(message.from_user.id)
        if user is None:
            await ctx.api.send_message(message.chat.id, fa.MY_EMPTY)
            return
        service = ctx.submission_service(session)
        items = await service.submissions.list_recent_by_user(user.id, limit=10)
        if not items:
            await ctx.api.send_message(message.chat.id, fa.MY_EMPTY)
            return
        lines = [fa.MY_HEADER]
        lines.extend(
            fa.my_item_line(
                s.short_id, s.content_type.value, fa.status_name(s.status.value), s.created_at
            )
            for s in items
        )
    await ctx.api.send_message(message.chat.id, "\n".join(lines))


async def handle_undo(ctx: BotContext, message: Message, args: list[str]) -> None:
    if message.from_user is None:
        return
    if not args:
        await ctx.api.send_message(message.chat.id, fa.ERR_UNDO_NOT_FOUND)
        return
    short_id = args[0].strip().lower()
    async with ctx.db.session() as session:
        service = ctx.submission_service(session)
        submission = await service.submissions.get_by_short_id(short_id)
        users = UserRepository(session)
        user = await users.get_by_bale_id(message.from_user.id)
        if submission is None or user is None or submission.user_id != user.id:
            await ctx.api.send_message(message.chat.id, fa.ERR_UNDO_NOT_FOUND)
            return
        group = await session.get(Group, submission.group_id) if submission.group_id else None
        undone = await service.undo(submission, group)
    if undone:
        await ctx.api.send_message(message.chat.id, fa.UNDO_SUCCESS)
    else:
        await ctx.api.send_message(message.chat.id, fa.ERR_UNDO_EXPIRED)


async def handle_resume(ctx: BotContext, message: Message) -> None:
    async with ctx.db.session() as session:
        resumed = await resume_wizard(ctx, session, message)
    if not resumed:
        await ctx.api.send_message(message.chat.id, fa.RESUME_NOTHING)
