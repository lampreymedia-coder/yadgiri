"""Group gateway intake: persist, then open the hashtag wizard in private chat.

Research groups keep the original message visible. Archive groups are write
destinations only. Role questions and the tagging wizard never stay in the
group; bot prompts there are deleted as soon as the private flow continues.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.bale.errors import BaleAPIError, NetworkError
from app.bale.keyboards import button, keyboard
from app.bale.models import InlineKeyboardMarkup, Message
from app.config import IngestMode
from app.core.context import BotContext
from app.db.models import IN_PROGRESS_STATUSES, ContentType, Group, SubmissionStatus
from app.db.repositories.groups import GroupRepository
from app.db.repositories.outbox import OutboxRepository
from app.db.repositories.users import UserRepository
from app.domain.classify import ClassifiedContent, classify
from app.domain.delivery import inspect_research_delivery
from app.domain.group_roles import (
    ROLE_ARCHIVE,
    delete_group_prompt,
    ensure_research_role,
    group_role,
    is_archive_destination,
    patch_settings,
)
from app.handlers.wizard import open_wizard, refresh_after_origin_edit, render_group_choice
from app.i18n import fa
from app.observability.logging import get_logger

logger = get_logger(__name__)

_DELIVERY_NOTICE_COOLDOWN_SECONDS = 20 * 60


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


def _payload_user_id(user: object) -> int | None:
    if not isinstance(user, dict):
        return None
    raw = user.get("id")
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.lstrip("-").isdigit():
        return int(raw)
    return None


def membership_event_as_message(payload: dict[str, Any], bot_user_id: int) -> Message | None:
    """Turn a ``my_chat_member`` / ``chat_member`` payload into a join/leave message."""
    chat = payload.get("chat")
    new_member = payload.get("new_chat_member")
    if not isinstance(chat, dict) or not isinstance(new_member, dict):
        return None
    user = new_member.get("user")
    if not isinstance(user, dict) or _payload_user_id(user) != bot_user_id:
        return None
    status = str(new_member.get("status") or "").lower()
    old = payload.get("old_chat_member")
    old_status = ""
    if isinstance(old, dict):
        old_status = str(old.get("status") or "").lower()
    body: dict[str, Any] = {
        "message_id": 0,
        "date": payload.get("date") or 0,
        "chat": chat,
        "from": payload.get("from"),
    }
    if status in {"left", "kicked"}:
        body["left_chat_member"] = user
    elif status in {"member", "administrator", "creator", "restricted"}:
        if old_status in {"administrator", "creator"} and status == "member":
            return None
        body["new_chat_member"] = user
    else:
        return None
    try:
        return Message.model_validate(body)
    except (ValueError, TypeError):
        return None


async def handle_group_hello(ctx: BotContext, message: Message) -> None:
    """`/start` or a bare mention in a group: never clutter the group itself."""
    async with ctx.db.session() as session:
        groups = GroupRepository(session)
        group = await groups.upsert(message.chat.id, message.chat.title, message.chat.type)
        await groups.set_active(group.id, True)
        if not await _activate_pending_group(ctx, session, group):
            return
        from app.handlers.admin import promote_first_owner

        if message.from_user is not None:
            await promote_first_owner(ctx, session, message.from_user)
        user_id = message.from_user.id if message.from_user is not None else None
        if user_id is None:
            return
        title = message.chat.title or group.title or fa.fa_digits(message.chat.id)
        if group_role(group) == ROLE_ARCHIVE:
            try:
                await ctx.api.send_message(user_id, fa.archive_already_set(title))
            except (BaleAPIError, NetworkError) as exc:
                logger.info("group_hello_dm_failed", error=str(exc))
            return
        ensure_research_role(group)
        await send_research_ready_notice(
            ctx, session, group, user_id, fa.research_need_admin(title, ctx.bot_username)
        )


async def _chat_member_status(ctx: BotContext, chat_id: int, user_id: int) -> str | None:
    try:
        member = await ctx.api.get_chat_member(chat_id, user_id)
    except (BaleAPIError, NetworkError) as exc:
        logger.warning(
            "chat_member_status_failed", chat_id=chat_id, user_id=user_id, error=str(exc)
        )
        return None
    status = member.get("status")
    return str(status).lower() if status is not None else None


async def _wait_for_admin_promotion(
    ctx: BotContext,
    session: AsyncSession,
    message: Message,
    group: Group,
) -> None:
    groups = GroupRepository(session)
    title = message.chat.title or group.title or fa.fa_digits(message.chat.id)
    adder_id = message.from_user.id if message.from_user is not None else None
    if group_role(group) != ROLE_ARCHIVE:
        ensure_research_role(group)
    patch_settings(group, pending_admin=True, pending_adder_id=adder_id)
    await groups.set_active(group.id, True)
    notice = fa.bot_join_waiting_for_admin(title)
    dm_sent = False
    if adder_id is not None:
        try:
            await ctx.api.send_message(adder_id, notice)
            dm_sent = True
        except (BaleAPIError, NetworkError) as exc:
            logger.warning(
                "pending_admin_private_notice_failed",
                chat_id=adder_id,
                error=str(exc),
            )
    if dm_sent:
        logger.info("bot_waiting_for_admin", chat_id=message.chat.id, adder_id=adder_id)
        return
    try:
        sent = await ctx.api.send_message(message.chat.id, notice, is_group=True)
        patch_settings(
            group,
            prompt_chat_id=message.chat.id,
            prompt_message_id=sent.message_id,
        )
    except (BaleAPIError, NetworkError) as exc:
        logger.warning(
            "pending_admin_group_notice_failed",
            chat_id=message.chat.id,
            error=str(exc),
        )
    logger.info("bot_waiting_for_admin", chat_id=message.chat.id, adder_id=adder_id)


def looks_like_withheld_content(message: Message) -> bool:
    """True when Bale sent a group stub with no text, media, or service payload."""
    if not message.is_group_message:
        return False
    if message.added_members() or message.left_chat_member or message.group_chat_created:
        return False
    if _is_service_message(message):
        return False
    return not _has_user_content(message)


async def send_research_ready_notice(
    ctx: BotContext,
    session: AsyncSession,
    group: Group,
    user_id: int | None,
    fallback: str,
    *,
    withheld: bool = False,
) -> bool:
    """DM the user: either the optimistic ready text, or why Bale is silent."""
    if user_id is None:
        return False
    report = await inspect_research_delivery(ctx.api, group.bale_chat_id, ctx.bot_user_id)
    explain = withheld or report.at_risk
    if explain:
        last_at = 0.0
        last = group.settings.get("delivery_notice_at")
        if last is not None:
            with contextlib.suppress(TypeError, ValueError):
                last_at = float(str(last))
        now = time.time()
        if last_at and now - last_at < _DELIVERY_NOTICE_COOLDOWN_SECONDS:
            return False
        text = fa.research_delivery_gap(
            group.title or fa.fa_digits(group.bale_chat_id),
            member_count=report.member_count,
            admin_count=report.admin_count,
            bot_is_admin=report.bot_is_admin,
            almost_all_admins=report.almost_all_admins,
            withheld=withheld,
        )
    else:
        text = fallback
    try:
        await ctx.api.send_message(user_id, text)
    except (BaleAPIError, NetworkError) as exc:
        logger.warning(
            "research_ready_notice_failed",
            chat_id=group.bale_chat_id,
            user_id=user_id,
            error=str(exc),
        )
        return False
    if explain:
        patch_settings(group, delivery_notice_at=time.time())
    return True


async def handle_withheld_group_content(ctx: BotContext, message: Message) -> None:
    """When Bale delivers an empty stub, tell the sender instead of staying silent."""
    extra = message.model_extra or {}
    logger.info(
        "group_update_without_text",
        chat_id=message.chat.id,
        message_id=message.message_id,
        from_id=message.from_user.id if message.from_user else None,
        extra_keys=sorted(extra.keys()),
        raw_keys=sorted(message.raw().keys()),
    )
    user_id = message.from_user.id if message.from_user is not None else None
    if user_id is None:
        return
    async with ctx.db.session() as session:
        groups = GroupRepository(session)
        group = await groups.get_by_bale_id(message.chat.id)
        if group is None:
            group = await groups.upsert(message.chat.id, message.chat.title, message.chat.type)
        if group.settings.get("pending_admin"):
            return
        if is_archive_destination(group, ctx.archive_chat_id) or group_role(group) == ROLE_ARCHIVE:
            return
        title = message.chat.title or group.title or fa.fa_digits(message.chat.id)
        if group.title != title:
            group.title = title
        ensure_research_role(group)
        await send_research_ready_notice(
            ctx,
            session,
            group,
            user_id,
            fa.research_admin_setup_done(title),
            withheld=True,
        )


async def _activate_pending_group(
    ctx: BotContext,
    session: AsyncSession,
    group: Group,
) -> bool:
    """After promotion, unlock content. The adder need not be a group admin."""
    if not group.settings.get("pending_admin"):
        return True
    bot_status = await _chat_member_status(ctx, group.bale_chat_id, ctx.bot_user_id)
    if bot_status not in {"administrator", "creator"}:
        return False

    patch_settings(group, pending_admin=False, pending_adder_id=None)
    await delete_group_prompt(ctx.api, group)
    if group_role(group) != ROLE_ARCHIVE:
        ensure_research_role(group)
    logger.info("pending_group_activated", chat_id=group.bale_chat_id)
    return True


async def register_group_events(ctx: BotContext, message: Message) -> None:
    """Track bot membership: new_chat_members / new_chat_member / group_chat_created."""
    members = message.added_members()
    if not members and not message.group_chat_created and not message.left_chat_member:
        return
    async with ctx.db.session() as session:
        groups = GroupRepository(session)
        group = await groups.upsert(message.chat.id, message.chat.title, message.chat.type)
        if group.settings.get("pending_admin"):
            adder_id = message.from_user.id if message.from_user is not None else None
            title = message.chat.title or group.title or fa.fa_digits(message.chat.id)
            if await _activate_pending_group(ctx, session, group):
                if group_role(group) != ROLE_ARCHIVE:
                    await send_research_ready_notice(
                        ctx,
                        session,
                        group,
                        adder_id,
                        fa.research_admin_setup_done(title),
                    )
                return
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
        from app.handlers.admin import promote_first_owner

        adder_id = message.from_user.id if message.from_user is not None else None
        if message.from_user is not None:
            await promote_first_owner(ctx, session, message.from_user)
        await groups.set_active(group.id, True)
        title = message.chat.title or group.title or fa.fa_digits(message.chat.id)
        bot_status = await _chat_member_status(ctx, message.chat.id, ctx.bot_user_id)
        if group_role(group) == ROLE_ARCHIVE:
            if bot_status not in {"administrator", "creator"}:
                await _wait_for_admin_promotion(ctx, session, message, group)
                return
            if adder_id is not None:
                try:
                    await ctx.api.send_message(adder_id, fa.archive_already_set(title))
                except (BaleAPIError, NetworkError) as exc:
                    logger.warning(
                        "archive_rejoin_dm_failed",
                        chat_id=message.chat.id,
                        error=str(exc),
                    )
            return
        ensure_research_role(group)
        if bot_status not in {"administrator", "creator"}:
            await _wait_for_admin_promotion(ctx, session, message, group)
            return
        patch_settings(group, pending_admin=False, pending_adder_id=None)
        await send_research_ready_notice(
            ctx, session, group, adder_id, fa.research_rejoined(title, ctx.bot_username)
        )


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
    if not _has_user_content(message):
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
        if not await _activate_pending_group(ctx, session, group):
            return

        if is_archive_destination(group, ctx.archive_chat_id):
            return

        ensure_research_role(group)

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
