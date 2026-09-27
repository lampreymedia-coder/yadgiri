"""The archive wizard, held in the sender's private chat.

decision (بله / خیر / انصراف) → hashtags (multi-select, ≥1) → preview → تأیید نهایی.
Nothing touches Post/PostHashtag/PostMedia before «تأیید نهایی»; the write
itself is :func:`app.domain.archive.save_confirmed`. The original group
message is never deleted. When the wizard ends, only its own private
messages (and a group hint, if one was shown) are removed.
"""

from __future__ import annotations

from app.bale.errors import BaleAPIError, NetworkError
from app.bale.keyboards import button, grid, keyboard, url_button
from app.bale.models import CallbackQuery, InlineKeyboardMarkup
from app.core.context import BotContext
from app.core.wizard_store import (
    STEP_DECISION,
    STEP_PREVIEW,
    STEP_SAVING,
    STEP_TAGS,
    WizardSession,
)
from app.db import repo
from app.domain.archive import Outcome, save_confirmed
from app.i18n import fa
from app.observability.logging import get_logger

logger = get_logger(__name__)

# callback_data actions (ASCII, packed as "1|act|sid|arg" ≤ 64 bytes)
ACT_YES = "y"
ACT_NO = "n"
ACT_CANCEL = "x"
ACT_TOGGLE = "t"
ACT_CONTINUE = "c"
ACT_BACK = "b"
ACT_FINAL = "f"
ACT_EDIT_TAGS = "e"

WIZARD_ACTIONS = {
    ACT_YES,
    ACT_NO,
    ACT_CANCEL,
    ACT_TOGGLE,
    ACT_CONTINUE,
    ACT_BACK,
    ACT_FINAL,
    ACT_EDIT_TAGS,
}


# ─── Rendering ───


def render_decision(s: WizardSession) -> tuple[str, InlineKeyboardMarkup]:
    text = fa.decision_prompt(s.group.name, s.content_type, s.content_text)
    rows = [
        [button(fa.BTN_SAVE_YES, ACT_YES, s.sid)],
        [button(fa.BTN_SAVE_NO, ACT_NO, s.sid), button(fa.BTN_CANCEL, ACT_CANCEL, s.sid)],
    ]
    return text, keyboard(rows)


def render_tags(
    s: WizardSession, hashtags: list[repo.HashtagRow]
) -> tuple[str, InlineKeyboardMarkup]:
    if not hashtags:
        return fa.NO_ACTIVE_HASHTAGS, keyboard([[button(fa.BTN_CANCEL, ACT_CANCEL, s.sid)]])
    tag_buttons = [
        button(
            f"{fa.TAG_CHECKED if tag.id in s.selected else fa.TAG_UNCHECKED} {tag.name}",
            ACT_TOGGLE,
            s.sid,
            str(tag.id),
        )
        for tag in hashtags
    ]
    rows = grid(tag_buttons, 2 if len(hashtags) > 4 else 1)
    rows.append([button(fa.BTN_CONTINUE, ACT_CONTINUE, s.sid)])
    rows.append([button(fa.BTN_BACK, ACT_BACK, s.sid), button(fa.BTN_CANCEL, ACT_CANCEL, s.sid)])
    return fa.tags_prompt(len(s.selected)), keyboard(rows)


def _file_count(s: WizardSession) -> int:
    from app.domain.classify import classify

    return sum(len(classify(message).media) for message in s.messages)


def render_preview(s: WizardSession, names: list[str]) -> tuple[str, InlineKeyboardMarkup]:
    text = fa.preview(s.group.name, s.content_type, s.content_text, _file_count(s), names)
    rows = [
        [button(fa.BTN_FINAL_CONFIRM, ACT_FINAL, s.sid)],
        [button(fa.BTN_EDIT_TAGS, ACT_EDIT_TAGS, s.sid)],
        [button(fa.BTN_CANCEL, ACT_CANCEL, s.sid)],
    ]
    return text, keyboard(rows)


async def _hashtags(ctx: BotContext) -> list[repo.HashtagRow]:
    async with ctx.db.tx() as conn:
        return await repo.active_hashtags(conn)


# ─── Opening / closing ───


async def open_wizard(ctx: BotContext, s: WizardSession) -> bool:
    """Show the first question in private chat. Falls back to a short group hint."""
    ctx.wizards.add(s)
    return await _show_in_private(ctx, s)


async def _show_in_private(ctx: BotContext, s: WizardSession) -> bool:
    subject_id: int | None = None
    try:
        subject_id = await ctx.api.copy_message(s.user_id, s.origin_chat_id, s.primary_message_id)
        s.private_extra_ids.append(subject_id)
    except (BaleAPIError, NetworkError) as exc:
        logger.info("wizard_subject_copy_failed", sid=s.sid, error=str(exc))
    text, markup = render_decision(s)
    try:
        sent = await ctx.api.send_message(s.user_id, text, markup, reply_to_message_id=subject_id)
    except (BaleAPIError, NetworkError) as exc:
        logger.info("wizard_private_open_failed", sid=s.sid, error=str(exc))
        await _show_group_hint(ctx, s)
        return False
    s.wizard_message_id = sent.message_id
    s.step = STEP_DECISION
    await _delete_group_hint(ctx, s)
    return True


async def _show_group_hint(ctx: BotContext, s: WizardSession) -> None:
    if s.hint_message_id is not None or not ctx.bot_username:
        return
    markup = keyboard([[url_button(fa.BTN_OPEN_PRIVATE, f"https://ble.ir/{ctx.bot_username}")]])
    try:
        sent = await ctx.api.send_message(
            s.origin_chat_id,
            fa.dm_hint(ctx.bot_username),
            markup,
            reply_to_message_id=s.primary_message_id,
            is_group=True,
        )
        s.hint_message_id = sent.message_id
    except (BaleAPIError, NetworkError) as exc:
        logger.warning("wizard_group_hint_failed", sid=s.sid, error=str(exc))


async def _delete_group_hint(ctx: BotContext, s: WizardSession) -> None:
    if s.hint_message_id is None:
        return
    await _try_delete(ctx, s.origin_chat_id, s.hint_message_id)
    s.hint_message_id = None


async def _try_delete(ctx: BotContext, chat_id: int, message_id: int) -> None:
    try:
        await ctx.api.delete_message(chat_id, message_id)
    except (BaleAPIError, NetworkError) as exc:
        logger.info("delete_failed", chat_id=chat_id, message_id=message_id, error=str(exc))


async def close_wizard(ctx: BotContext, s: WizardSession) -> None:
    """Forget the wizard and delete only its own messages. Never the original."""
    ctx.wizards.pop(s.sid)
    if s.wizard_message_id is not None:
        await _try_delete(ctx, s.user_id, s.wizard_message_id)
    for message_id in s.private_extra_ids:
        await _try_delete(ctx, s.user_id, message_id)
    await _delete_group_hint(ctx, s)


async def resume_pending(ctx: BotContext, user_id: int) -> int:
    """After the user opens the private chat, show wizards that waited for it."""
    opened = 0
    for s in ctx.wizards.for_user(user_id):
        if s.wizard_message_id is None and s.step != STEP_SAVING and await _show_in_private(ctx, s):
            opened += 1
    return opened


async def expire_and_remind(ctx: BotContext) -> None:
    """Periodic: discard wizards older than the TTL; one reminder before that."""
    ttl = ctx.settings.wizard_ttl_minutes * 60
    for s in ctx.wizards.expired(ttl):
        logger.info("wizard_expired", sid=s.sid)
        await close_wizard(ctx, s)
    remind_after = ctx.settings.reminder_after_minutes * 60
    for s in ctx.wizards.all():
        if s.reminded or s.wizard_message_id is None or s.step == STEP_SAVING:
            continue
        if s.age_seconds() < remind_after:
            continue
        s.reminded = True
        try:
            sent = await ctx.api.send_message(
                s.user_id, fa.REMINDER, reply_to_message_id=s.wizard_message_id
            )
            s.private_extra_ids.append(sent.message_id)
        except (BaleAPIError, NetworkError) as exc:
            logger.info("wizard_reminder_failed", sid=s.sid, error=str(exc))


# ─── Callbacks ───


async def _answer(ctx: BotContext, cq: CallbackQuery, text: str | None = None) -> None:
    try:
        await ctx.api.answer_callback_query(cq.id, text)
    except (BaleAPIError, NetworkError) as exc:
        logger.info("answer_callback_failed", error=str(exc))


async def _edit(ctx: BotContext, s: WizardSession, text: str, markup: InlineKeyboardMarkup) -> None:
    if s.wizard_message_id is None:
        return
    s.wizard_message_id = await ctx.api.safe_edit(s.user_id, s.wizard_message_id, text, markup)


async def _notify_admins(ctx: BotContext, text: str) -> None:
    await ctx.notifier.send_all(text)


async def _tell_user(ctx: BotContext, s: WizardSession, text: str) -> None:
    try:
        await ctx.api.send_message(s.user_id, text)
    except (BaleAPIError, NetworkError) as exc:
        logger.info("user_notice_failed", error=str(exc))


async def handle_callback(
    ctx: BotContext, cq: CallbackQuery, action: str, sid: str, arg: str
) -> None:
    s = ctx.wizards.get(sid)
    if s is None:
        logger.info("callback_dropped", reason="wizard_expired", sid=sid, actor=cq.from_user.id)
        await _answer(ctx, cq, fa.ERR_EXPIRED)
        if cq.message is not None:
            try:
                await ctx.api.delete_message(cq.message.chat.id, cq.message.message_id)
            except (BaleAPIError, NetworkError) as exc:
                logger.info("stale_wizard_delete_failed", error=str(exc))
        return
    if cq.from_user.id != s.user_id:
        logger.info("callback_dropped", reason="not_sender", sid=sid, actor=cq.from_user.id)
        await _answer(ctx, cq, fa.ERR_NOT_YOURS)
        return
    if s.step == STEP_SAVING:
        await _answer(ctx, cq)
        return

    if action in (ACT_NO, ACT_CANCEL):
        await _answer(ctx, cq)
        logger.info("wizard_declined", sid=s.sid, action=action)
        await close_wizard(ctx, s)
        return

    if action in (ACT_YES, ACT_EDIT_TAGS) or (action == ACT_BACK and s.step == STEP_PREVIEW):
        await _answer(ctx, cq)
        s.step = STEP_TAGS
        text, markup = render_tags(s, await _hashtags(ctx))
        await _edit(ctx, s, text, markup)
        return

    if action == ACT_BACK:
        await _answer(ctx, cq)
        s.step = STEP_DECISION
        text, markup = render_decision(s)
        await _edit(ctx, s, text, markup)
        return

    if action == ACT_TOGGLE and s.step == STEP_TAGS:
        hashtags = await _hashtags(ctx)
        valid = {tag.id for tag in hashtags}
        if arg.isdigit() and int(arg) in valid:
            tag_id = int(arg)
            if tag_id in s.selected:
                s.selected.remove(tag_id)
            else:
                s.selected.append(tag_id)
        s.selected = [tag_id for tag_id in s.selected if tag_id in valid]
        await _answer(ctx, cq)
        text, markup = render_tags(s, hashtags)
        await _edit(ctx, s, text, markup)
        return

    if action == ACT_CONTINUE and s.step == STEP_TAGS:
        hashtags = await _hashtags(ctx)
        names = {tag.id: tag.name for tag in hashtags}
        s.selected = [tag_id for tag_id in s.selected if tag_id in names]
        if not s.selected:
            await _answer(ctx, cq, fa.NEED_ONE_TAG)
            return
        await _answer(ctx, cq)
        s.step = STEP_PREVIEW
        text, markup = render_preview(s, [names[tag_id] for tag_id in s.selected])
        await _edit(ctx, s, text, markup)
        return

    if action == ACT_FINAL and s.step == STEP_PREVIEW:
        await _answer(ctx, cq)
        await _final_confirm(ctx, s)
        return

    await _answer(ctx, cq)


async def _final_confirm(ctx: BotContext, s: WizardSession) -> None:
    s.step = STEP_SAVING
    result = await save_confirmed(ctx, s)
    logger.info("wizard_final", sid=s.sid, outcome=result.outcome.value, post_id=result.post_id)

    if result.outcome is Outcome.SAVED:
        # Nothing is posted in the group: wizard leftovers (incl. a group hint)
        # are removed, the sender and the admins are told in private chat.
        await close_wizard(ctx, s)
        try:
            await ctx.api.send_message(s.user_id, fa.saved_reply(result.hashtag_names))
        except (BaleAPIError, NetworkError) as exc:
            logger.info("saved_notice_skipped", user_id=s.user_id, error=str(exc))
        assert result.post_id is not None
        await ctx.notifier.post_saved(
            fa.admin_saved(
                s.sender_name, s.group.name, s.content_type, result.hashtag_names, result.post_id
            ),
            fa.admin_saved_short(
                s.sender_name, s.group.name, s.content_type, result.hashtag_names, result.post_id
            ),
        )
        return

    if result.outcome is Outcome.DUPLICATE:
        await close_wizard(ctx, s)
        return

    if result.outcome is Outcome.NO_HASHTAG:
        s.step = STEP_TAGS
        s.selected = []
        text, markup = render_tags(s, await _hashtags(ctx))
        await _edit(ctx, s, text, markup)
        return

    if result.outcome is Outcome.FAILED:
        s.step = STEP_PREVIEW
        await _tell_user(ctx, s, fa.SAVE_FAILED)
        return

    if result.outcome is Outcome.TYPE_REJECTED:
        await _tell_user(ctx, s, fa.TYPE_NOT_ALLOWED)
        user_label = f"{s.sender_name} ({s.user_id})"
        await _notify_admins(ctx, fa.admin_check_alert(s.group.name, s.content_type, user_label))
    elif result.outcome is Outcome.PERSON_INACTIVE:
        await _tell_user(ctx, s, fa.PERSON_INACTIVE)
    elif result.outcome is Outcome.GROUP_INACTIVE:
        await _tell_user(ctx, s, fa.GROUP_NOT_ACTIVE)
    await close_wizard(ctx, s)
