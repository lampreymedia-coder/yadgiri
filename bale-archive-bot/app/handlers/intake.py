"""Group messages → (maybe) a wizard. Never writes Post rows.

Rules (CLAUDE-BOT-FIX.md sections 3 and 5):
* The archive group (ARCHIVE_CHAT_ID) is ignored completely.
* A group that is not in EhyaGroup with is_active = 1 gets total silence:
  no message, no database write, no deletion.
* In a registered group the sender gets a Person row (found by bale_user_id)
  and a PersonGroup row; the content itself is only held in memory until
  the sender confirms in the wizard.
"""

from __future__ import annotations

from app.bale.errors import BaleAPIError, NetworkError
from app.bale.models import Message
from app.core.context import BotContext
from app.core.wizard_store import WizardSession
from app.db import repo
from app.domain.classify import classify
from app.domain.content import ContentType
from app.handlers.wizard import open_wizard
from app.i18n import fa
from app.mapping import POST_TEXT, post_content_type
from app.observability.logging import get_logger
from app.timeutil import tehran_from_unix

logger = get_logger(__name__)

_SERVICE_KEYS = (
    "new_chat_title",
    "new_chat_photo",
    "delete_chat_photo",
    "pinned_message",
    "migrate_to_chat_id",
    "migrate_from_chat_id",
    "group_chat_created",
    "supergroup_chat_created",
    "channel_chat_created",
)


def is_archive_chat(ctx: BotContext, chat_id: int) -> bool:
    return ctx.archive_chat_id is not None and chat_id == ctx.archive_chat_id


def is_service_message(message: Message) -> bool:
    if message.new_chat_members or message.new_chat_member or message.left_chat_member:
        return True
    extra = message.model_extra or {}
    return any(extra.get(key) for key in _SERVICE_KEYS)


def display_name(message: Message) -> str:
    user = message.from_user
    if user is None:
        return ""
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return name or (f"@{user.username}" if user.username else str(user.id))


def content_text(messages: list[Message]) -> str:
    """Post.content_text: text or caption; '' for media without a caption."""
    for message in messages:
        for value in (message.text, message.caption):
            if value and value.strip():
                return value
    first = classify(messages[0])
    if first.content_type in (ContentType.CONTACT, ContentType.LOCATION):
        return first.text_content or ""
    return ""


async def process_group_batch(ctx: BotContext, messages: list[Message]) -> None:
    """One buffered group item (single message or album)."""
    primary = messages[0]
    if is_archive_chat(ctx, primary.chat.id):
        return
    sender = primary.from_user
    if sender is None or sender.is_bot or is_service_message(primary):
        return

    async with ctx.user_locks.get(("person", sender.id)), ctx.db.tx() as conn:
        group = await repo.get_active_group(conn, primary.chat.id)
        if group is None:
            return  # unregistered or inactive group: complete silence
        person = await repo.ensure_person(
            conn, sender.id, sender.username, sender.first_name, sender.last_name
        )
        await repo.ensure_membership(conn, person.id, group.id)

    if not person.is_active:
        logger.info("inactive_person_ignored", user_id=sender.id)
        try:
            await ctx.api.send_message(sender.id, fa.PERSON_INACTIVE)
        except (BaleAPIError, NetworkError) as exc:
            logger.info("inactive_notice_failed", error=str(exc))
        return

    kinds = [classify(message).content_type for message in messages]
    code = post_content_type(kinds)
    if code is None:
        logger.info("content_not_archivable", kinds=[k.value for k in kinds])
        return
    if code == POST_TEXT and not content_text(messages).strip():
        return

    if not ctx.spam_guard.allow(sender.id):
        try:
            await ctx.api.send_message(sender.id, fa.ERR_SPAM_LIMIT)
        except (BaleAPIError, NetworkError) as exc:
            logger.info("spam_notice_failed", error=str(exc))
        return

    session = WizardSession(
        sid=ctx.wizards.new_sid(),
        user_id=sender.id,
        person_id=person.id,
        group=group,
        origin_chat_id=primary.chat.id,
        origin_message_ids=[message.message_id for message in messages],
        messages=list(messages),
        content_type=code,
        content_text=content_text(messages),
        posted_at=tehran_from_unix(primary.date),
        sender_name=display_name(primary),
    )
    logger.info(
        "wizard_opened",
        sid=session.sid,
        group=group.id,
        user_id=sender.id,
        content_type=code,
        messages=len(messages),
    )
    await open_wizard(ctx, session)


def apply_edit(ctx: BotContext, message: Message) -> bool:
    """An edited original updates the still-open wizard's text (memory only)."""
    session = ctx.wizards.find_by_origin(message.chat.id, message.message_id)
    if session is None:
        return False
    session.messages = [
        message if item.message_id == message.message_id else item for item in session.messages
    ]
    session.content_text = content_text(session.messages)
    return True
