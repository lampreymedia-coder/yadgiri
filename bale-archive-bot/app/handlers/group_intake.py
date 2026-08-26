"""Group gateway intake: persist, then open the hashtag wizard in private chat.

Research groups keep the original message visible. Archive groups are write
destinations only. Role questions and the tagging wizard never stay in the
group; bot prompts there are deleted as soon as the private flow continues.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.bale.errors import BaleAPIError, NetworkError
from app.bale.keyboards import button, keyboard, url_button
from app.bale.models import InlineKeyboardMarkup, Message
from app.config import IngestMode
from app.core.context import BotContext
from app.db.models import IN_PROGRESS_STATUSES, ContentType, Group, SubmissionStatus
from app.db.repositories.groups import GroupRepository
from app.db.repositories.outbox import OutboxRepository
from app.db.repositories.users import UserRepository
from app.domain.classify import ClassifiedContent, classify
from app.domain.group_roles import (
    ROLE_ARCHIVE,
    ROLE_RESEARCH,
    group_role,
    is_archive_destination,
    needs_role,
    patch_settings,
    role_already_asked,
)
from app.handlers.wizard import open_wizard, refresh_after_origin_edit, render_group_choice
from app.i18n import fa
from app.observability.logging import get_logger

logger = get_logger(__name__)


def strip_leading_bot_mention(message: Message, bot_username: str | None) -> Message:
    """Remove an addressing mention while preserving the user's content.

    Bale may deliver addressed messages even when it withholds ordinary group
    messages. Treat ``@bot content`` as content rather than archiving the bot
    username with it, so every research group has a reliable fallback path.
    """
    if not bot_username:
        return message
    token = f"@{bot_username}".casefold()
    changes: dict[str, str] = {}
    for field in ("text", "caption"):
        value = getattr(message, field)
        stripped = (value or "").lstrip()
        if not stripped.casefold().startswith(token):
            continue
        remainder = stripped[len(token) :]
        if remainder and not remainder[0].isspace():
            continue
        changes[field] = remainder.lstrip()
    return message.model_copy(update=changes) if changes else message


def role_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return keyboard(
        [
            [button(fa.BTN_GROUP_IS_RESEARCH, "srg", "", str(chat_id))],
            [button(fa.BTN_GROUP_IS_ARCHIVE, "sar", "", str(chat_id))],
        ]
    )


def archive_tag_keyboard(chat_id: int, tags: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    """``tags`` is (slug, button_label)."""
    rows = [[button(label, "stg", str(chat_id), slug)] for slug, label in tags]
    rows.append([button(fa.BTN_BACK, "srb", "", str(chat_id))])
    return keyboard(rows)


async def ask_role_privately(
    ctx: BotContext,
    session: AsyncSession,
    group: Group,
    user_bale_id: int | None,
    group_title: str,
    *,
    force: bool = False,
) -> bool:
    """Ask research vs archive in a private chat. Returns True if a DM was sent."""
    if not force and not needs_role(group) and role_already_asked(group):
        return False
    patch_settings(group, role_asked=True)
    if user_bale_id is None:
        return False
    text = fa.bot_added_ask_role(group_title)
    markup = role_keyboard(group.bale_chat_id)
    try:
        await ctx.api.send_message(user_bale_id, text, markup)
        return True
    except (BaleAPIError, NetworkError) as exc:
        logger.warning("role_dm_failed", chat_id=group.bale_chat_id, error=str(exc))
    hint = fa.group_role_private_hint(ctx.bot_username)
    url = f"https://ble.ir/{ctx.bot_username}" if ctx.bot_username else None
    hint_markup = keyboard([[url_button(fa.BTN_OPEN_PRIVATE, url)]]) if url else None
    try:
        sent = await ctx.api.send_message(group.bale_chat_id, hint, hint_markup, is_group=True)
        patch_settings(
            group,
            prompt_chat_id=group.bale_chat_id,
            prompt_message_id=sent.message_id,
        )
    except (BaleAPIError, NetworkError) as exc:
        logger.warning("role_group_hint_failed", chat_id=group.bale_chat_id, error=str(exc))
        patch_settings(group, role_asked=False)
    return False


async def handle_group_hello(ctx: BotContext, message: Message) -> None:
    """`/start` or a bare mention in a group: never clutter the group itself."""
    async with ctx.db.session() as session:
        groups = GroupRepository(session)
        group = await groups.upsert(message.chat.id, message.chat.title, message.chat.type)
        await groups.set_active(group.id, True)
        from app.handlers.admin import is_admin, promote_first_owner

        if message.from_user is not None:
            await promote_first_owner(ctx, session, message.from_user)
        user_id = message.from_user.id if message.from_user is not None else None
        if user_id is None or not await is_admin(ctx, session, user_id):
            return
        title = message.chat.title or group.title or fa.fa_digits(message.chat.id)
        role = group_role(group)
        try:
            if role == ROLE_RESEARCH:
                await ctx.api.send_message(
                    user_id, fa.research_need_admin(title, ctx.bot_username)
                )
                return
            if role == ROLE_ARCHIVE:
                await ctx.api.send_message(user_id, fa.archive_already_set(title))
                return
        except (BaleAPIError, NetworkError) as exc:
            logger.info("group_hello_dm_failed", error=str(exc))
            return
        await ask_role_privately(ctx, session, group, user_id, title, force=True)


async def _leave_unauthorized_group(
    ctx: BotContext,
    session: AsyncSession,
    message: Message,
    group: Group,
) -> None:
    groups = GroupRepository(session)
    title = message.chat.title or group.title or fa.fa_digits(message.chat.id)
    adder = message.from_user
    adder_id = adder.id if adder is not None else None
    adder_name = ""
    if adder is not None:
        adder_name = adder.first_name or adder.username or fa.fa_digits(adder.id)
    try:
        await ctx.api.send_message(
            message.chat.id, fa.bot_left_unauthorized_group(title), is_group=True
        )
    except (BaleAPIError, NetworkError) as exc:
        logger.warning("unauthorized_join_notice_failed", chat_id=message.chat.id, error=str(exc))
    if adder_id is not None:
        try:
            await ctx.api.send_message(adder_id, fa.BOT_JOIN_DENIED)
        except (BaleAPIError, NetworkError) as exc:
            logger.warning("unauthorized_join_dm_failed", chat_id=adder_id, error=str(exc))
    owner_id = next(iter(ctx.runtime_admin_ids), None) or ctx.admin_notify_chat_id
    if owner_id is not None and owner_id != adder_id:
        try:
            await ctx.api.send_message(owner_id, fa.admin_unauthorized_add(title, adder_name))
        except (BaleAPIError, NetworkError) as exc:
            logger.warning("unauthorized_join_owner_failed", chat_id=owner_id, error=str(exc))
    try:
        await ctx.api.leave_chat(message.chat.id)
    except (BaleAPIError, NetworkError) as exc:
        logger.warning("unauthorized_leave_failed", chat_id=message.chat.id, error=str(exc))
    await groups.set_active(group.id, False)
    logger.info("bot_left_unauthorized_group", chat_id=message.chat.id, adder_id=adder_id)


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
        from app.handlers.admin import is_admin, promote_first_owner

        if message.from_user is not None:
            await promote_first_owner(ctx, session, message.from_user)
        adder_id = message.from_user.id if message.from_user is not None else None
        allowed = adder_id is not None and await is_admin(ctx, session, adder_id)
        if not allowed:
            await _leave_unauthorized_group(ctx, session, message, group)
            return
        await groups.set_active(group.id, True)
        title = message.chat.title or group.title or fa.fa_digits(message.chat.id)
        role = group_role(group)
        if role == ROLE_RESEARCH:
            try:
                await ctx.api.send_message(
                    adder_id, fa.research_rejoined(title, ctx.bot_username)
                )
            except (BaleAPIError, NetworkError) as exc:
                logger.warning(
                    "research_rejoin_dm_failed", chat_id=message.chat.id, error=str(exc)
                )
            return
        if role == ROLE_ARCHIVE:
            try:
                await ctx.api.send_message(adder_id, fa.archive_already_set(title))
            except (BaleAPIError, NetworkError) as exc:
                logger.warning(
                    "archive_rejoin_dm_failed", chat_id=message.chat.id, error=str(exc)
                )
            return
        await ask_role_privately(ctx, session, group, adder_id, title)


def _is_allowed_group(ctx: BotContext, chat_id: int) -> bool:
    allowed = ctx.settings.allowed_group_ids
    return not allowed or chat_id in allowed


def _is_gif(classified: ClassifiedContent) -> bool:
    if classified.content_type is ContentType.ANIMATION:
        return True
    if classified.content_type is ContentType.DOCUMENT:
        mime = (classified.content_subtype or "").lower()
        name = ""
        if classified.media:
            name = (classified.media[0].file_name or "").lower()
        if mime == "image_file" and name.endswith(".gif"):
            return True
        raw_mime = classified.media[0].mime_type if classified.media else None
        if raw_mime and "gif" in raw_mime.lower():
            return True
    return False


def _has_user_content(message: Message) -> bool:
    extra = message.model_extra or {}
    return any(
        (
            (message.text or "").strip(),
            (message.caption or "").strip(),
            message.photo,
            message.video,
            message.video_note,
            message.audio,
            message.voice,
            message.document,
            message.animation,
            message.sticker,
            message.contact,
            message.location,
            extra.get("file"),
            extra.get("voice"),
            extra.get("audio"),
            extra.get("video_note"),
        )
    )


def _is_service_message(message: Message) -> bool:
    extra = message.model_extra or {}
    service_keys = (
        "new_chat_title",
        "new_chat_photo",
        "delete_chat_photo",
        "pinned_message",
        "migrate_to_chat_id",
        "migrate_from_chat_id",
        "supergroup_chat_created",
        "channel_chat_created",
        "video_chat_started",
        "video_chat_ended",
        "video_chat_participants_invited",
        "message_auto_delete_timer_changed",
    )
    return any(extra.get(key) for key in service_keys) and not _has_user_content(message)


def _should_ignore(ctx: BotContext, message: Message) -> bool:
    del ctx
    if message.from_user is None or message.from_user.is_bot:
        return True
    if message.new_chat_members or message.new_chat_member or message.left_chat_member:
        return True
    if _is_service_message(message):
        return True
    text = message.text or ""
    if text.startswith("/"):
        return True
    classified = classify(message)
    if classified.content_type is ContentType.STICKER:
        return True
    if _is_gif(classified):
        return True
    return classified.content_type is ContentType.TEXT and not (message.text or "").strip()


async def process_group_batch(ctx: BotContext, messages: list[Message]) -> None:
    """Process one buffered batch (single message or album) from a group."""
    primary = messages[0]
    if not _is_allowed_group(ctx, primary.chat.id):
        return
    if ctx.settings.ingest_mode is IngestMode.PRIVATE_FIRST:
        return

    async with ctx.db.session() as session:
        groups = GroupRepository(session)
        group = await groups.upsert(primary.chat.id, primary.chat.title, primary.chat.type)
        await groups.set_active(group.id, True)

        if is_archive_destination(group, ctx.archive_chat_id):
            return

        if needs_role(group) and not role_already_asked(group):
            from app.handlers.admin import is_admin, promote_first_owner

            if primary.from_user is not None:
                await promote_first_owner(ctx, session, primary.from_user)
            user_id = primary.from_user.id if primary.from_user is not None else None
            title = primary.chat.title or group.title or fa.fa_digits(primary.chat.id)
            if user_id is not None and await is_admin(ctx, session, user_id):
                await ask_role_privately(ctx, session, group, user_id, title)

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
                await ctx.api.send_message(user.bale_user_id, fa.ERR_SPAM_LIMIT)
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
                await ctx.api.send_message(user.bale_user_id, fa.ERR_SERVER)
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
            and not is_archive_destination(g, ctx.archive_chat_id)
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


async def handle_edited_message(ctx: BotContext, message: Message) -> None:
    """Apply an origin edit to the existing submission; never open a second wizard."""
    if message.from_user is None or message.from_user.is_bot:
        return
    async with ctx.db.session() as session:
        users = UserRepository(session)
        user = await users.get_by_bale_id(message.from_user.id)
        if user is None:
            logger.info(
                "edited_message_unknown_user",
                chat_id=message.chat.id,
                message_id=message.message_id,
            )
            return
        service = ctx.submission_service(session)
        submission = await service.submissions.find_by_origin_for_user(
            user.id, message.chat.id, message.message_id
        )
        if submission is None:
            logger.info(
                "edited_message_no_submission",
                chat_id=message.chat.id,
                message_id=message.message_id,
            )
            return
        classified = classify(message)
        service.apply_content_update(submission, classified, message.raw())
        logger.info(
            "origin_edit_applied",
            short_id=submission.short_id,
            status=submission.status.value,
        )
        if submission.status in IN_PROGRESS_STATUSES:
            await refresh_after_origin_edit(ctx, session, submission)
            return
        if submission.status is SubmissionStatus.COMPLETED:
            sender = user.display_name or user.username or fa.fa_digits(user.bale_user_id)
            await service.refresh_archive_copies(submission, sender)
