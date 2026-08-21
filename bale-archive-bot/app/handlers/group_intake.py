"""Group gateway intake and private-first intake.

Group flow: archive → persist → delete → wizard in the same group (reply).
Private flow: the user sends content straight to the bot; no deletion is
ever needed and the wizard runs in place.
"""

from __future__ import annotations

from app.bale.errors import BaleAPIError, NetworkError
from app.bale.keyboards import button, keyboard
from app.bale.models import InlineKeyboardMarkup, Message
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

ROLE_ARCHIVE = "archive"
ROLE_RESEARCH = "research"


def group_role(group: Group) -> str | None:
    raw = group.settings.get("role")
    return raw if isinstance(raw, str) else None


def role_already_asked(group: Group) -> bool:
    return bool(group.settings.get("role_asked"))


def set_group_role(group: Group, role: str) -> None:
    group.settings = {**group.settings, "role": role, "role_asked": True}


def role_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return keyboard(
        [
            [button(fa.BTN_GROUP_IS_RESEARCH, "srg", "", str(chat_id))],
            [button(fa.BTN_GROUP_IS_ARCHIVE, "sar", "", str(chat_id))],
        ]
    )


async def ask_group_role(
    ctx: BotContext, message: Message, group: Group, *, force: bool = False
) -> bool:
    """Ask in the group itself whether this chat is research or archive.

    Returns True when a prompt was posted (or attempted).
    """
    if not force and (role_already_asked(group) or group_role(group) is not None):
        return False
    if not force:
        set_group_role(group, ROLE_RESEARCH)
    title = message.chat.title or group.title or fa.fa_digits(message.chat.id)
    text = fa.bot_added_ask_role(title)
    markup = role_keyboard(message.chat.id)
    try:
        await ctx.api.send_message(
            message.chat.id,
            text,
            markup,
            reply_to_message_id=message.message_id,
            is_group=True,
        )
        group.settings = {**group.settings, "role_asked": True}
        return True
    except (BaleAPIError, NetworkError) as exc:
        logger.warning("bot_added_group_notice_failed", chat_id=message.chat.id, error=str(exc))
        group.settings = {**group.settings, "role_asked": False}
        return False


async def handle_group_hello(ctx: BotContext, message: Message) -> None:
    """`/start` (or equivalent) typed in a group: introduce the bot and ask the role."""
    async with ctx.db.session() as session:
        groups = GroupRepository(session)
        group = await groups.upsert(message.chat.id, message.chat.title, message.chat.type)
        await groups.set_active(group.id, True)
        if message.from_user is not None:
            from app.handlers.admin import promote_first_owner

            await promote_first_owner(ctx, session, message.from_user)
        asked = await ask_group_role(ctx, message, group, force=True)
    if asked:
        return
    try:
        await ctx.api.send_message(
            message.chat.id,
            fa.GROUP_HELLO,
            reply_to_message_id=message.message_id,
            is_group=True,
        )
    except (BaleAPIError, NetworkError) as exc:
        logger.warning("group_hello_failed", chat_id=message.chat.id, error=str(exc))


async def register_group_events(ctx: BotContext, message: Message) -> None:
    """Track bot membership: new_chat_members / new_chat_member / group_chat_created."""
    members = message.added_members()
    if not members and not message.group_chat_created and not message.left_chat_member:
        return
    async with ctx.db.session() as session:
        groups = GroupRepository(session)
        group = await groups.upsert(message.chat.id, message.chat.title, message.chat.type)
        bot_joined = message.group_chat_created or any(
            member.id == ctx.bot_user_id for member in members
        )
        if message.left_chat_member is not None and message.left_chat_member.id == ctx.bot_user_id:
            await groups.set_active(group.id, False)
            logger.info("bot_removed_from_group", chat_id=message.chat.id)
            return
        if not bot_joined:
            return
        logger.info("bot_added_to_group", chat_id=message.chat.id)
        await groups.set_active(group.id, True)
        if message.from_user is not None:
            from app.handlers.admin import promote_first_owner

            await promote_first_owner(ctx, session, message.from_user)
        await ask_group_role(ctx, message, group)


def _is_allowed_group(ctx: BotContext, chat_id: int) -> bool:
    allowed = ctx.settings.allowed_group_ids
    return not allowed or chat_id in allowed


def _should_ignore(ctx: BotContext, message: Message) -> bool:
    if message.from_user is None or message.from_user.is_bot:
        return True
    if message.new_chat_members or message.new_chat_member or message.left_chat_member:
        return True
    text = message.text or ""
    if text.startswith("/"):
        return True
    if ctx.settings.ignore_stickers and message.sticker is not None:
        return True
    classified = classify(message)
    if classified.content_type is ContentType.OTHER:
        # Still keep anything with a caption/text; classify already mapped those.
        return True
    return classified.content_type is ContentType.TEXT and not (message.text or "").strip()


async def process_group_batch(ctx: BotContext, messages: list[Message]) -> None:
    """Process one buffered batch (single message or album) from a group."""
    primary = messages[0]
    if ctx.archive_chat_id is not None and primary.chat.id == ctx.archive_chat_id:
        return
    if ctx.settings.ingest_mode is IngestMode.PRIVATE_FIRST:
        return
    if not _is_allowed_group(ctx, primary.chat.id):
        return

    async with ctx.db.session() as session:
        groups = GroupRepository(session)
        group = await groups.upsert(primary.chat.id, primary.chat.title, primary.chat.type)
        await groups.set_active(group.id, True)

        if group_role(group) != ROLE_ARCHIVE and not role_already_asked(group):
            await ask_group_role(ctx, primary, group)

        if primary.from_user is None:
            return

        users = UserRepository(session)
        user = await users.upsert_from_bale(
            primary.from_user.id,
            primary.from_user.username,
            primary.from_user.first_name,
            primary.from_user.last_name,
        )

        if group_role(group) == ROLE_ARCHIVE:
            return

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
            notify_id = ctx.admin_notify_chat_id or ctx.settings.admin_chat_id
            if notify_id is not None:
                outbox = OutboxRepository(session)
                await outbox.enqueue(
                    "admin_notify",
                    notify_id,
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

        await open_wizard(ctx, session, result.submission, user, group, origin=primary)


async def process_private_content(ctx: BotContext, message: Message) -> None:
    """Private-first ingest: content sent directly to the bot's private chat."""
    if ctx.settings.ingest_mode is IngestMode.GROUP_GATEWAY:
        return
    if message.from_user is None:
        return
    if _should_ignore(ctx, message):
        try:
            await ctx.api.send_message(message.chat.id, fa.GROUP_GOT_IT)
        except (BaleAPIError, NetworkError) as exc:
            logger.info("private_ignore_notice_failed", error=str(exc))
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
            if _is_allowed_group(ctx, g.bale_chat_id)
            and g.bale_chat_id != ctx.archive_chat_id
            and group_role(g) != ROLE_ARCHIVE
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

        await open_wizard(ctx, session, submission, user, target_group, origin=message)
