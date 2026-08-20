"""Group gateway intake and private-first intake.

Group flow (spec section 3): archive → persist → delete → wizard.
Private flow: the user sends content straight to the bot; no deletion is
ever needed and the wizard runs in place.
"""

from __future__ import annotations

from app.bale.errors import BaleAPIError, NetworkError
from app.bale.models import Message
from app.config import IngestMode
from app.core.context import BotContext
from app.db.models import ContentType, Group
from app.db.repositories.groups import GroupRepository
from app.db.repositories.outbox import OutboxRepository
from app.db.repositories.users import UserRepository
from app.domain.classify import classify
from app.handlers.wizard import open_wizard, render_group_choice
from app.i18n import fa
from app.observability.logging import get_logger

logger = get_logger(__name__)


async def register_group_events(ctx: BotContext, message: Message) -> None:
    """Track bot membership: new_chat_members is the only join signal."""
    if not message.new_chat_members:
        return
    async with ctx.db.session() as session:
        groups = GroupRepository(session)
        group = await groups.upsert(message.chat.id, message.chat.title, message.chat.type)
        for member in message.new_chat_members:
            if member.id == ctx.bot_user_id:
                logger.info("bot_added_to_group", chat_id=message.chat.id)
                await groups.set_active(group.id, True)
                if message.from_user is not None:
                    from app.handlers.admin import promote_first_owner

                    await promote_first_owner(ctx, session, message.from_user)
                title = message.chat.title or fa.fa_digits(message.chat.id)
                from app.bale.keyboards import button, keyboard

                markup = keyboard(
                    [
                        [
                            button(
                                fa.BTN_GROUP_IS_RESEARCH,
                                "srg",
                                "",
                                str(message.chat.id),
                            )
                        ],
                        [
                            button(
                                fa.BTN_GROUP_IS_ARCHIVE,
                                "sar",
                                "",
                                str(message.chat.id),
                            )
                        ],
                    ]
                )
                text = fa.bot_added_ask_role(title)
                notified = False
                notify_ids = set(ctx.runtime_admin_ids)
                if message.from_user is not None:
                    notify_ids.add(message.from_user.id)
                for admin_id in notify_ids:
                    try:
                        await ctx.api.send_message(admin_id, text, markup)
                        notified = True
                    except (BaleAPIError, NetworkError) as exc:
                        logger.info("bot_added_admin_notice_failed", error=str(exc))
                if not notified:
                    try:
                        await ctx.api.send_message(message.chat.id, text, markup, is_group=True)
                    except (BaleAPIError, NetworkError) as exc:
                        logger.warning("bot_added_group_notice_failed", error=str(exc))


def _is_allowed_group(ctx: BotContext, chat_id: int) -> bool:
    allowed = ctx.settings.allowed_group_ids
    return not allowed or chat_id in allowed


def _should_ignore(ctx: BotContext, message: Message) -> bool:
    if message.from_user is None or message.from_user.is_bot:
        return True
    if message.new_chat_members or message.left_chat_member:
        return True
    text = message.text or ""
    if text.startswith("/"):
        return True
    if ctx.settings.ignore_stickers and message.sticker is not None:
        return True
    # Empty content (no text, no media) is nothing to archive.
    classified = classify(message)
    return classified.content_type is ContentType.OTHER or (
        classified.content_type is ContentType.TEXT and not (message.text or "").strip()
    )


async def process_group_batch(ctx: BotContext, messages: list[Message]) -> None:
    """Process one buffered batch (single message or album) from a group."""
    primary = messages[0]
    if primary.from_user is None:
        return
    if ctx.archive_chat_id is not None and primary.chat.id == ctx.archive_chat_id:
        return
    if ctx.settings.ingest_mode is IngestMode.PRIVATE_FIRST:
        return
    if not _is_allowed_group(ctx, primary.chat.id):
        return

    async with ctx.db.session() as session:
        users = UserRepository(session)
        groups = GroupRepository(session)
        user = await users.upsert_from_bale(
            primary.from_user.id,
            primary.from_user.username,
            primary.from_user.first_name,
            primary.from_user.last_name,
        )
        group = await groups.upsert(primary.chat.id, primary.chat.title, primary.chat.type)

        if user.is_blocked:
            return

        if not ctx.spam_guard.allow(user.bale_user_id):
            try:
                await ctx.api.send_message(
                    primary.chat.id,
                    fa.ERR_SPAM_LIMIT,
                    reply_to_message_id=primary.message_id,
                    is_group=True,
                )
            except (BaleAPIError, NetworkError) as exc:
                logger.warning("spam_notice_failed", error=str(exc))
            if ctx.settings.admin_chat_id is not None:
                outbox = OutboxRepository(session)
                await outbox.enqueue(
                    "admin_notify",
                    ctx.settings.admin_chat_id,
                    {
                        "text": fa.admin_spam_alert(
                            user.display_name or str(user.bale_user_id),
                            user.bale_user_id,
                            ctx.spam_guard.count(user.bale_user_id),
                        )
                    },
                )
            return

        classified = classify(messages[0])
        service = ctx.submission_service(session)
        result = await service.intake(
            messages, classified, user, group, raw_update=messages[0].raw()
        )

        if not result.archived or result.submission is None:
            # Golden rule path: nothing was deleted; tell the user briefly.
            try:
                await ctx.api.send_message(
                    primary.chat.id,
                    fa.ERR_SERVER,
                    reply_to_message_id=primary.message_id,
                    is_group=True,
                )
            except (BaleAPIError, NetworkError) as exc:
                logger.warning("intake_failure_notice_failed", error=str(exc))
            return

        await open_wizard(ctx, session, result.submission, user, group)


async def process_private_content(ctx: BotContext, message: Message) -> None:
    """Private-first ingest: content sent directly to the bot's private chat."""
    if ctx.settings.ingest_mode is IngestMode.GROUP_GATEWAY:
        return
    if message.from_user is None:
        return
    if _should_ignore(ctx, message):
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
        if user.is_blocked:
            return
        if not ctx.spam_guard.allow(user.bale_user_id):
            await ctx.api.send_message(message.chat.id, fa.ERR_SPAM_LIMIT)
            return

        groups_repo = GroupRepository(session)
        active_groups = [
            g
            for g in await groups_repo.list_active()
            if _is_allowed_group(ctx, g.bale_chat_id) and g.bale_chat_id != ctx.archive_chat_id
        ]
        target_group: Group | None = active_groups[0] if len(active_groups) == 1 else None

        classified = classify(message)
        service = ctx.submission_service(session)
        result = await service.intake(
            [message], classified, user, target_group, raw_update=message.raw()
        )
        if not result.archived or result.submission is None:
            await ctx.api.send_message(message.chat.id, fa.ERR_SERVER)
            return

        submission = result.submission
        if target_group is None and len(active_groups) > 1:
            # Ask which group this belongs to before the decision step.
            text, markup = render_group_choice(active_groups, submission.short_id)
            sent = await ctx.api.send_message(message.chat.id, text, markup)
            submission.wizard_chat_id = message.chat.id
            submission.wizard_message_id = sent.message_id
            from app.core.fsm import Conversation, WizardState

            conversation = Conversation(chat_id=message.chat.id, user_id=user.bale_user_id)
            conversation.transition(WizardState.AWAITING_DECISION)
            conversation.payload = {"sid": submission.short_id, "selected": [], "target": None}
            await ctx.state_store(session).save(conversation, ctx.settings.submission_ttl_minutes)
            return

        await open_wizard(ctx, session, submission, user, target_group)
