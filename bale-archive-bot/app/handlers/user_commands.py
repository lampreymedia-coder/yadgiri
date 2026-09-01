"""Non-admin commands: start, help, menu, tags, my, undo, resume, status, id."""

from __future__ import annotations

from app.bale.models import Message
from app.core.context import BotContext
from app.db.models import Group
from app.db.repositories.users import UserRepository
from app.handlers import menu
from app.handlers.wizard import _delete_group_hint, open_wizard, resume_wizard
from app.i18n import fa


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
        pending = await ctx.submission_service(session).submissions.latest_in_progress_for_user(
            user.id
        )
        if pending is not None:
            group = await session.get(Group, pending.group_id) if pending.group_id else None
            await _delete_group_hint(ctx, pending)
            if await resume_wizard(ctx, session, message):
                return
            await open_wizard(ctx, session, pending, user, group, origin=message)
            return

        if promoted or (ctx.is_runtime_admin(message.from_user.id) and ctx.archive_chat_id is None):
            text = fa.start_owner_setup(name)
        else:
            text = fa.start_message(name)
        show_admin = promoted or ctx.is_runtime_admin(message.from_user.id) or bool(user.is_admin)
    await ctx.api.send_message(
        message.chat.id, text, menu.persistent_reply_keyboard(ctx, is_admin=show_admin)
    )


async def handle_help(ctx: BotContext, message: Message) -> None:
    if message.from_user is None:
        return
    await menu.send_help(
        ctx, message.chat.id, message.from_user.id, private=message.is_private_message
    )


async def handle_menu(ctx: BotContext, message: Message) -> None:
    if message.from_user is None:
        return
    await menu.send_menu(
        ctx, message.chat.id, message.from_user.id, private=message.is_private_message
    )


async def handle_add_to_group(ctx: BotContext, message: Message) -> None:
    await menu.send_add_to_group(ctx, message.chat.id)


async def handle_tags(ctx: BotContext, message: Message) -> None:
    await menu.send_public_tags(ctx, message.chat.id)


async def handle_status(ctx: BotContext, message: Message) -> None:
    await menu.send_status(ctx, message.chat.id)


async def handle_id(ctx: BotContext, message: Message) -> None:
    await menu.send_id_card(ctx, message)


async def handle_my(ctx: BotContext, message: Message) -> None:
    if message.from_user is None:
        return
    await menu.send_my_list(ctx, message.chat.id, message.from_user.id)


async def handle_undo(ctx: BotContext, message: Message, args: list[str]) -> None:
    if message.from_user is None:
        return
    if not args:
        await menu.send_undo_help(ctx, message.chat.id, message.from_user.id)
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
