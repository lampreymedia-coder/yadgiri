"""The tagging wizard: decision → hashtag multi-select → preview → done.

All keyboard updates go through ``safe_edit`` (text + keyboard together).
State lives in Postgres (conversation_states), never in process memory; the back button
pops the history stack and never discards selections.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.bale.errors import BaleAPIError, NetworkError
from app.bale.keyboards import button, grid, keyboard, parse_callback, url_button
from app.bale.models import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from app.core.context import BotContext
from app.core.fsm import Conversation, WizardState
from app.core.locks import advisory_xact_lock
from app.db.models import (
    TERMINAL_STATUSES,
    Group,
    Submission,
    SubmissionStatus,
    Tag,
    User,
)
from app.db.repositories.tags import TagRepository
from app.db.repositories.users import UserRepository
from app.domain.group_roles import try_delete_message
from app.domain.private_chat import META_SUBJECT, settle_private_chat
from app.domain.submission import SubmissionService
from app.i18n import fa
from app.observability.logging import get_logger

logger = get_logger(__name__)

# Callback actions (ASCII, spec section 2-7)
ACT_DECISION_YES = "yes"
ACT_DECISION_NO = "no"
ACT_CANCEL = "cx"
ACT_TAG_COUNT = "cnt"
ACT_TOGGLE_TAG = "tg"
ACT_TAGS_CONTINUE = "ok"
ACT_BACK = "bk"
ACT_FINAL_CONFIRM = "fin"
ACT_EDIT_TAGS = "edt"
ACT_EDIT_NOTE = "nt"
ACT_TAG_PAGE = "pgt"
ACT_PICK_GROUP = "gr"
ACT_NOOP = "noop"

WIZARD_ACTIONS = {
    ACT_DECISION_YES,
    ACT_DECISION_NO,
    ACT_CANCEL,
    ACT_TAG_COUNT,
    ACT_TOGGLE_TAG,
    ACT_TAGS_CONTINUE,
    ACT_BACK,
    ACT_FINAL_CONFIRM,
    ACT_EDIT_TAGS,
    ACT_EDIT_NOTE,
    ACT_TAG_PAGE,
    ACT_PICK_GROUP,
    ACT_NOOP,
}

_TAGS_PER_PAGE = 16
_TWO_COLUMN_THRESHOLD = 8


def media_details(submission: Submission) -> str:
    """Human details: duration for audio, dimensions for image, filename for docs."""
    if not submission.media_files:
        return ""
    first = submission.media_files[0]
    if submission.content_type.value in ("voice", "audio", "video", "animation"):
        duration = fa.format_duration(first.duration_seconds)
        return f"({duration})" if duration else ""
    if submission.content_type.value in ("image", "album"):
        if first.width and first.height:
            return f"({fa.fa_digits(first.width)}×{fa.fa_digits(first.height)})"
        return ""
    if submission.content_type.value == "document" and first.file_name:
        return f"({first.file_name})"
    return ""


def total_size(submission: Submission) -> int:
    return sum(m.file_size_bytes or 0 for m in submission.media_files)


def _group_title(group: Group | None) -> str:
    return (group.title if group else None) or ""


def _wizard_excerpt(submission: Submission) -> str:
    excerpt = (submission.text_content or submission.caption or "").strip()
    if len(excerpt) > 200:
        return excerpt[:200] + "…"
    return excerpt


def _persist_wizard_payload(submission: Submission, conversation: Conversation) -> None:
    """Keep per-submission selections even when another wizard is also open."""
    meta = dict(submission.meta or {})
    meta["selected"] = [int(item) for item in conversation.payload.get("selected", [])]
    meta["note"] = conversation.payload.get("note")
    meta["page"] = conversation.payload.get("page", 1)
    meta["wizard_history"] = list(conversation.history)
    submission.meta = meta


# ─── Rendering ───


def render_decision(
    submission: Submission, user: User, group: Group | None, bot_username: str, in_group: bool
) -> tuple[str, InlineKeyboardMarkup]:
    text = fa.decision_prompt(
        name=user.display_name or user.username or fa.fa_digits(user.bale_user_id),
        content_type=submission.content_type.value,
        group_title=(group.title if group else None) or "",
        dt=datetime.now(UTC),
        short_id=submission.short_id,
        excerpt=_wizard_excerpt(submission),
    )
    rows = [
        [button(fa.BTN_SAVE_YES, ACT_DECISION_YES, submission.short_id)],
        [button(fa.BTN_CANCEL, ACT_CANCEL, submission.short_id)],
    ]
    if in_group and bot_username:
        text = f"{text}\n\n{fa.group_fallback_hint(bot_username)}"
        rows = [[url_button(fa.BTN_OPEN_PRIVATE, f"https://ble.ir/{bot_username}")]]
    return text, keyboard(rows)


def render_group_choice(groups: list[Group], sid: str) -> tuple[str, InlineKeyboardMarkup]:
    rows = [
        [button((g.title or fa.fa_digits(g.bale_chat_id)), ACT_PICK_GROUP, sid, str(g.id))]
        for g in groups
    ]
    rows.append([button(fa.BTN_CANCEL, ACT_CANCEL, sid)])
    return fa.TAG_COUNT_PROMPT, keyboard(rows)


def render_tag_count(
    active_tag_count: int, sid: str, can_back: bool
) -> tuple[str, InlineKeyboardMarkup]:
    # Counts are never hardcoded: offer 1..min(3, n); "all" appears when n>3.
    numeric_buttons: list[InlineKeyboardButton] = []
    for count in range(1, min(3, active_tag_count) + 1):
        numeric_buttons.append(
            button(fa.btn_tag_count(count, active_tag_count), ACT_TAG_COUNT, sid, str(count))
        )
    rows = grid(numeric_buttons, 2)
    if active_tag_count > 3:
        rows.append([button(fa.BTN_TAG_COUNT_ALL, ACT_TAG_COUNT, sid, str(active_tag_count))])
    rows.append([button(fa.BTN_TAG_COUNT_FREE, ACT_TAG_COUNT, sid, "free")])
    if can_back:
        rows.append([button(fa.BTN_BACK, ACT_BACK, sid)])
    return fa.TAG_COUNT_PROMPT, keyboard(rows)


def render_tags(
    tags: list[Tag],
    selected_ids: list[int],
    target: int | None,
    sid: str,
    page: int = 1,
    group_title: str = "",
) -> tuple[str, InlineKeyboardMarkup]:
    text = fa.tag_select_prompt(len(selected_ids), target, group_title, sid)
    total_pages = max(1, (len(tags) + _TAGS_PER_PAGE - 1) // _TAGS_PER_PAGE)
    page = max(1, min(page, total_pages))
    page_tags = tags[(page - 1) * _TAGS_PER_PAGE : page * _TAGS_PER_PAGE]

    tag_buttons: list[InlineKeyboardButton] = []
    for tag in page_tags:
        mark = fa.TAG_CHECKED if tag.id in selected_ids else fa.TAG_UNCHECKED
        emoji = f"{tag.emoji} " if tag.emoji else ""
        tag_buttons.append(
            button(f"{mark} {emoji}{tag.title_fa}", ACT_TOGGLE_TAG, sid, str(tag.id))
        )

    columns = 2 if len(tags) > _TWO_COLUMN_THRESHOLD else 1
    rows = grid(tag_buttons, columns)

    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 1:
            nav.append(button("◀️", ACT_TAG_PAGE, sid, str(page - 1)))
        nav.append(
            InlineKeyboardButton(
                text=f"{fa.fa_digits(page)}/{fa.fa_digits(total_pages)}",
                callback_data=f"1|{ACT_NOOP}|{sid}|",
            )
        )
        if page < total_pages:
            nav.append(button("▶️", ACT_TAG_PAGE, sid, str(page + 1)))
        rows.append(nav)

    complete = bool(selected_ids) and (target is None or len(selected_ids) == target)
    confirm_label = fa.BTN_CONFIRM_CONTINUE if complete else fa.BTN_CONFIRM_CONTINUE_DISABLED
    rows.append([button(confirm_label, ACT_TAGS_CONTINUE, sid)])
    rows.append([button(fa.BTN_BACK, ACT_BACK, sid)])
    return text, keyboard(rows)


def render_preview(
    submission: Submission,
    user: User,
    group: Group | None,
    tags: list[Tag],
    note: str | None,
) -> tuple[str, InlineKeyboardMarkup]:
    hashtags = " ".join(t.hashtag for t in tags) or "—"
    body = note or submission.text_content or submission.caption or ""
    excerpt = body[:200] if body else "—"
    text = fa.preview_prompt(
        sender_name=user.display_name or user.username or fa.fa_digits(user.bale_user_id),
        username=user.username,
        group_title=(group.title if group else None) or "",
        content_type=submission.content_type.value,
        details=media_details(submission),
        size_text=fa.format_bytes(total_size(submission)),
        hashtags=hashtags,
        excerpt=excerpt,
        dt=datetime.now(UTC),
        short_id=submission.short_id,
    )
    sid = submission.short_id
    rows = [
        [button(fa.BTN_FINAL_CONFIRM, ACT_FINAL_CONFIRM, sid)],
        [
            button(fa.BTN_EDIT_TAGS, ACT_EDIT_TAGS, sid),
            button(fa.BTN_EDIT_NOTE, ACT_EDIT_NOTE, sid),
        ],
        [button(fa.BTN_BACK_TO_PREV, ACT_BACK, sid)],
        [button(fa.BTN_CANCEL, ACT_CANCEL, sid)],
    ]
    return text, keyboard(rows)


# ─── Opening the wizard ───


async def _send_subject_copy(
    ctx: BotContext,
    submission: Submission,
    user: User,
    group: Group | None,
    origin: Message | None,
) -> int | None:
    """Copy the original group message into private chat so two wizards cannot mix."""
    dest = user.bale_user_id
    from_chat: int | None = None
    message_id: int | None = None
    if origin is not None and not origin.is_private_message:
        from_chat = origin.chat.id
        message_id = origin.message_id
    elif group is not None and submission.original_message_id:
        from_chat = group.bale_chat_id
        message_id = submission.original_message_id
    if from_chat is not None and message_id is not None:
        try:
            copied_id = await ctx.api.copy_message(dest, from_chat, message_id)
            submission.meta = {**submission.meta, META_SUBJECT: copied_id}
            return copied_id
        except (BaleAPIError, NetworkError) as exc:
            logger.info("subject_copy_failed", error=str(exc))
        try:
            forwarded = await ctx.api.forward_message(dest, from_chat, message_id)
            submission.meta = {**submission.meta, META_SUBJECT: forwarded.message_id}
            return forwarded.message_id
        except (BaleAPIError, NetworkError) as exc:
            logger.info("subject_forward_failed", error=str(exc))
    excerpt = _wizard_excerpt(submission)
    fallback = fa.decision_subject_fallback(
        _group_title(group), submission.content_type.value, excerpt
    )
    try:
        sent = await ctx.api.send_message(dest, fallback)
        submission.meta = {**submission.meta, META_SUBJECT: sent.message_id}
        return sent.message_id
    except (BaleAPIError, NetworkError) as exc:
        logger.warning("subject_fallback_failed", error=str(exc))
    return None


async def _replace_subject_copy(
    ctx: BotContext,
    submission: Submission,
    user: User,
    group: Group | None,
) -> int | None:
    """Drop the stale private copy and post the latest origin text."""
    dest = user.bale_user_id
    meta = dict(submission.meta or {})
    old_id = meta.get(META_SUBJECT)
    if isinstance(old_id, int):
        await try_delete_message(ctx.api, dest, old_id)
    body = (submission.text_content or submission.caption or "").strip()
    if submission.content_type.value in {"text", "link"} and body:
        try:
            sent = await ctx.api.send_message(dest, body)
            submission.meta = {**meta, META_SUBJECT: sent.message_id}
            return sent.message_id
        except (BaleAPIError, NetworkError) as exc:
            logger.info("subject_latest_send_failed", error=str(exc))
    return await _send_subject_copy(ctx, submission, user, group, origin=None)


async def refresh_after_origin_edit(
    ctx: BotContext, session: AsyncSession, submission: Submission
) -> None:
    """Show the latest origin text in the still-open private wizard."""
    if submission.status in TERMINAL_STATUSES:
        return
    owner = await UserRepository(session).get_by_id(submission.user_id)
    if owner is None:
        return
    group = await session.get(Group, submission.group_id) if submission.group_id else None
    new_subject = await _replace_subject_copy(ctx, submission, owner, group)
    chat_id = owner.bale_user_id
    if submission.wizard_message_id is not None:
        await try_delete_message(ctx.api, chat_id, submission.wizard_message_id)
    store = ctx.state_store(session)
    stored = await store.load(chat_id, owner.bale_user_id)
    if stored is not None and stored.payload.get("sid") == submission.short_id:
        conversation = stored
    else:
        conversation = _rebuild_conversation(submission, chat_id, owner.bale_user_id)
    try:
        sent = await ctx.api.send_message(
            chat_id,
            fa.START_RESUME,
            reply_to_message_id=new_subject,
        )
    except (BaleAPIError, NetworkError) as exc:
        logger.warning("wizard_reresend_failed", error=str(exc))
        return
    submission.wizard_chat_id = chat_id
    submission.wizard_message_id = sent.message_id
    tags_repo = TagRepository(session)
    await _render_state(
        ctx,
        session,
        ctx.submission_service(session),
        tags_repo,
        submission,
        owner,
        group,
        conversation,
        conversation.state,
    )


async def _delete_group_hint(ctx: BotContext, submission: Submission) -> None:
    meta = submission.meta if isinstance(submission.meta, dict) else {}
    chat_id = meta.get("group_hint_chat_id")
    message_id = meta.get("group_hint_message_id")
    if isinstance(chat_id, int) and isinstance(message_id, int):
        await try_delete_message(ctx.api, chat_id, message_id)
    submission.meta = {**meta, "group_hint_chat_id": None, "group_hint_message_id": None}


async def open_wizard(
    ctx: BotContext,
    session: AsyncSession,
    submission: Submission,
    user: User,
    group: Group | None,
    origin: Message | None = None,
) -> None:
    """Open the hashtag decision step in a private chat with the sender.

    If the user has never started the bot, a short URL hint is posted in the
    group and deleted as soon as the private conversation continues.
    """
    users_repo = UserRepository(session)
    origin_is_group = origin is not None and not origin.is_private_message
    private_chat = user.bale_user_id

    async def try_send(
        chat_id: int,
        body: str,
        markup: InlineKeyboardMarkup | None,
        *,
        is_group: bool,
        reply: int | None = None,
    ) -> Message | None:
        try:
            return await ctx.api.send_message(
                chat_id, body, markup, reply_to_message_id=reply, is_group=is_group
            )
        except (BaleAPIError, NetworkError) as exc:
            logger.warning("wizard_send_failed", chat_id=chat_id, error=str(exc))
        if markup is not None:
            try:
                return await ctx.api.send_message(
                    chat_id, body, None, reply_to_message_id=reply, is_group=is_group
                )
            except (BaleAPIError, NetworkError) as exc:
                logger.warning("wizard_send_plain_failed", chat_id=chat_id, error=str(exc))
        return None

    subject_id = await _send_subject_copy(ctx, submission, user, group, origin)
    text, markup = render_decision(submission, user, group, ctx.bot_username, in_group=False)
    sent = await try_send(private_chat, text, markup, is_group=False, reply=subject_id)
    if sent is not None:
        await users_repo.set_private_chat(user.id, True)
        submission.wizard_chat_id = private_chat
        submission.wizard_message_id = sent.message_id
        await _delete_group_hint(ctx, submission)
    else:
        await users_repo.set_private_chat(user.id, False)
        submission.wizard_chat_id = private_chat
        submission.wizard_message_id = None
        if origin_is_group and origin is not None and ctx.bot_username:
            hint = fa.group_fallback_hint(ctx.bot_username)
            hint_markup = keyboard(
                [[url_button(fa.BTN_OPEN_PRIVATE, f"https://ble.ir/{ctx.bot_username}")]]
            )
            hint_msg = await try_send(
                origin.chat.id,
                hint,
                hint_markup,
                is_group=True,
                reply=origin.message_id,
            )
            if hint_msg is not None:
                submission.meta = {
                    **submission.meta,
                    "group_hint_chat_id": origin.chat.id,
                    "group_hint_message_id": hint_msg.message_id,
                }

    conversation = Conversation(chat_id=private_chat, user_id=user.bale_user_id)
    conversation.transition(WizardState.AWAITING_DECISION)
    conversation.payload = {"sid": submission.short_id, "selected": [], "target": None}
    _persist_wizard_payload(submission, conversation)
    await ctx.state_store(session).save(conversation, ctx.settings.submission_ttl_minutes)


# ─── Callback handling ───


async def _answer(ctx: BotContext, cq: CallbackQuery, text: str | None = None) -> None:
    if ctx.caps.has("answerCallbackQuery"):
        try:
            await ctx.api.answer_callback_query(cq.id, text)
        except (BaleAPIError, NetworkError) as exc:
            logger.info("answer_callback_failed", error=str(exc))


async def _show_expired(ctx: BotContext, cq: CallbackQuery) -> None:
    await _answer(ctx, cq, fa.ERR_EXPIRED)
    if cq.message is not None:
        try:
            await ctx.api.safe_edit(
                cq.message.chat.id, cq.message.message_id, fa.WIZARD_EXPIRED_FINAL, None
            )
        except (BaleAPIError, NetworkError) as exc:
            logger.info("expired_edit_failed", error=str(exc))


async def handle_wizard_callback(ctx: BotContext, session: AsyncSession, cq: CallbackQuery) -> None:
    """Route one wizard callback. Never raises for stale/foreign clicks."""
    data = parse_callback(cq.data or "")
    if data.action == ACT_NOOP:
        await _answer(ctx, cq)
        return

    service = ctx.submission_service(session)
    submission = await service.submissions.get_by_short_id(data.sid)
    if submission is None or submission.status in TERMINAL_STATUSES:
        await _show_expired(ctx, cq)
        return

    owner = await service.users.get_by_id(submission.user_id)
    if owner is None or owner.bale_user_id != cq.from_user.id:
        await _answer(ctx, cq, fa.ERR_NOT_YOURS)
        return

    # Acknowledge the tap immediately so Bale does not expire the query
    # while we copy/edit. Toasts for validation still use a dedicated answer.
    if data.action != ACT_TAGS_CONTINUE:
        await _answer(ctx, cq)

    chat_id = owner.bale_user_id
    await advisory_xact_lock(session, chat_id, owner.bale_user_id)

    store = ctx.state_store(session)
    stored = await store.load(chat_id, owner.bale_user_id)
    if stored is not None and stored.payload.get("sid") == submission.short_id:
        conversation = stored
    else:
        conversation = _rebuild_conversation(submission, chat_id, owner.bale_user_id)

    group = await session.get(Group, submission.group_id) if submission.group_id else None
    tags_repo = TagRepository(session)

    handled = await _dispatch_action(
        ctx,
        session,
        service,
        tags_repo,
        cq,
        data.action,
        data.arg,
        submission,
        owner,
        group,
        conversation,
    )
    if handled:
        _persist_wizard_payload(submission, conversation)
        if conversation.state is WizardState.IDLE:
            if stored is not None and stored.payload.get("sid") == submission.short_id:
                await store.clear(chat_id, owner.bale_user_id)
        else:
            await store.save(conversation, ctx.settings.submission_ttl_minutes)


def _rebuild_conversation(submission: Submission, chat_id: int, user_id: int) -> Conversation:
    """Rebuild state after a restart from the submission row alone."""
    status_to_state = {
        SubmissionStatus.AWAITING_DECISION: WizardState.AWAITING_DECISION,
        SubmissionStatus.AWAITING_TAG_COUNT: WizardState.AWAITING_TAG_COUNT,
        SubmissionStatus.AWAITING_TAGS: WizardState.AWAITING_TAGS,
        SubmissionStatus.AWAITING_CONFIRM: WizardState.AWAITING_CONFIRM,
        SubmissionStatus.DRAFT: WizardState.AWAITING_DECISION,
    }
    conversation = Conversation(chat_id=chat_id, user_id=user_id)
    conversation.state = status_to_state.get(submission.status, WizardState.AWAITING_DECISION)
    meta = submission.meta if isinstance(submission.meta, dict) else {}
    selected = [t.id for t in submission.tags]
    if not selected:
        raw_selected = meta.get("selected") or []
        selected = [int(item) for item in raw_selected if str(item).lstrip("-").isdigit()]
    history = [str(item) for item in (meta.get("wizard_history") or [])]
    conversation.history = history
    conversation.payload = {
        "sid": submission.short_id,
        "selected": selected,
        "target": meta.get("target_count"),
        "note": meta.get("note"),
        "page": meta.get("page", 1),
    }
    return conversation


async def _edit_wizard(
    ctx: BotContext,
    submission: Submission,
    text: str,
    markup: InlineKeyboardMarkup | None,
) -> None:
    if submission.wizard_chat_id is None or submission.wizard_message_id is None:
        return
    new_id = await ctx.api.safe_edit(
        submission.wizard_chat_id, submission.wizard_message_id, text, markup
    )
    submission.wizard_message_id = new_id


async def _dispatch_action(
    ctx: BotContext,
    session: AsyncSession,
    service: SubmissionService,
    tags_repo: TagRepository,
    cq: CallbackQuery,
    action: str,
    arg: str,
    submission: Submission,
    owner: User,
    group: Group | None,
    conversation: Conversation,
) -> bool:
    selected: list[int] = list(conversation.payload.get("selected", []))

    if action == ACT_PICK_GROUP:
        chosen = await session.get(Group, int(arg)) if arg else None
        if chosen is not None:
            submission.group_id = chosen.id
        conversation.transition(WizardState.AWAITING_DECISION)
        text, markup = render_decision(submission, owner, chosen, ctx.bot_username, False)
        await _edit_wizard(ctx, submission, text, markup)
        await _answer(ctx, cq)
        return True

    if action == ACT_DECISION_YES:
        conversation.payload["target"] = None
        submission.meta = {**submission.meta, "target_count": None}
        await service.submissions.set_status(submission, SubmissionStatus.AWAITING_TAGS)
        conversation.transition(WizardState.AWAITING_TAGS)
        active = await tags_repo.list_active()
        text, markup = render_tags(
            active, selected, None, submission.short_id, group_title=_group_title(group)
        )
        await _edit_wizard(ctx, submission, text, markup)
        await _answer(ctx, cq)
        return True

    if action == ACT_DECISION_NO:
        sender = owner.display_name or owner.username or fa.fa_digits(owner.bale_user_id)
        if group is not None:
            await service.republish_without_tags(
                submission, group, sender, SubmissionStatus.DECLINED
            )
        else:
            await service.submissions.set_status(submission, SubmissionStatus.DECLINED)
        await _delete_group_hint(ctx, submission)
        await settle_private_chat(ctx, submission, fa.DECLINED_MESSAGE)
        conversation.state = WizardState.IDLE
        await _answer(ctx, cq)
        return True

    if action == ACT_CANCEL:
        await service.cancel_completely(submission)
        await _delete_group_hint(ctx, submission)
        await settle_private_chat(ctx, submission, fa.CANCELLED_MESSAGE)
        conversation.state = WizardState.IDLE
        await _answer(ctx, cq)
        return True

    if action == ACT_TAG_COUNT:
        # Older keyboards still send a count; ignore it and show all hashtags.
        conversation.payload["target"] = None
        submission.meta = {**submission.meta, "target_count": None}
        await service.submissions.set_status(submission, SubmissionStatus.AWAITING_TAGS)
        conversation.transition(WizardState.AWAITING_TAGS)
        active = await tags_repo.list_active()
        text, markup = render_tags(
            active, selected, None, submission.short_id, group_title=_group_title(group)
        )
        await _edit_wizard(ctx, submission, text, markup)
        await _answer(ctx, cq)
        return True

    if action == ACT_TOGGLE_TAG:
        tag_id = int(arg)
        active = await tags_repo.list_active()
        if tag_id in selected:
            selected.remove(tag_id)
        else:
            selected.append(tag_id)
        conversation.payload["selected"] = selected
        page = int(conversation.payload.get("page", 1))
        text, markup = render_tags(
            active,
            selected,
            None,
            submission.short_id,
            page,
            group_title=_group_title(group),
        )
        await _edit_wizard(ctx, submission, text, markup)
        await _answer(ctx, cq)
        return True

    if action == ACT_TAG_PAGE:
        page = int(arg) if arg else 1
        conversation.payload["page"] = page
        active = await tags_repo.list_active()
        text, markup = render_tags(
            active,
            selected,
            None,
            submission.short_id,
            page,
            group_title=_group_title(group),
        )
        await _edit_wizard(ctx, submission, text, markup)
        await _answer(ctx, cq)
        return True

    if action == ACT_TAGS_CONTINUE:
        if not selected:
            await _answer(ctx, cq, fa.TOAST_NO_TAG_SELECTED)
            return False
        await service.submissions.set_tags(submission, selected)
        await service.submissions.set_status(submission, SubmissionStatus.AWAITING_CONFIRM)
        conversation.transition(WizardState.AWAITING_CONFIRM)
        chosen_tags = [t for t in await tags_repo.list_active() if t.id in selected]
        note = conversation.payload.get("note")
        text, markup = render_preview(submission, owner, group, chosen_tags, note)
        await _edit_wizard(ctx, submission, text, markup)
        await _answer(ctx, cq)
        return True

    if action == ACT_EDIT_TAGS:
        conversation.transition(WizardState.AWAITING_TAGS)
        active = await tags_repo.list_active()
        text, markup = render_tags(
            active, selected, None, submission.short_id, group_title=_group_title(group)
        )
        await _edit_wizard(ctx, submission, text, markup)
        await _answer(ctx, cq)
        return True

    if action == ACT_EDIT_NOTE:
        conversation.transition(WizardState.AWAITING_NOTE)
        rows = [[button(fa.BTN_BACK, ACT_BACK, submission.short_id)]]
        await _edit_wizard(ctx, submission, fa.NOTE_PROMPT, keyboard(rows))
        await _answer(ctx, cq)
        return True

    if action == ACT_BACK:
        previous = conversation.go_back()
        while previous is WizardState.AWAITING_TAG_COUNT:
            previous = conversation.go_back()
        await _render_state(
            ctx,
            session,
            service,
            tags_repo,
            submission,
            owner,
            group,
            conversation,
            previous or WizardState.AWAITING_DECISION,
        )
        await _answer(ctx, cq)
        return True

    if action == ACT_FINAL_CONFIRM:
        note = conversation.payload.get("note")
        if note:
            submission.meta = {**submission.meta, "note": note}
            if submission.caption:
                submission.caption = f"{submission.caption}\n{note}"
            else:
                submission.caption = str(note)
        if selected:
            await service.submissions.set_tags(submission, selected)
        sender = owner.display_name or owner.username or fa.fa_digits(owner.bale_user_id)
        refreshed = await service.submissions.get_by_short_id(submission.short_id)
        assert refreshed is not None
        missing = await service.complete_into_tag_archives(refreshed, sender)
        await _delete_group_hint(ctx, refreshed)
        submission.wizard_chat_id = refreshed.wizard_chat_id = submission.wizard_chat_id
        submission.wizard_message_id = refreshed.wizard_message_id = submission.wizard_message_id
        await settle_private_chat(ctx, submission, fa.user_saved(missing))
        refreshed.wizard_chat_id = submission.wizard_chat_id
        refreshed.wizard_message_id = submission.wizard_message_id
        refreshed.meta = submission.meta
        await service.notify_admin_completed(
            refreshed, owner, group, media_details(refreshed), missing_archives=missing
        )
        conversation.state = WizardState.IDLE
        await _answer(ctx, cq)
        return True

    logger.warning("unknown_wizard_action", action=action)
    await _answer(ctx, cq)
    return False


async def _render_state(
    ctx: BotContext,
    session: AsyncSession,
    service: SubmissionService,
    tags_repo: TagRepository,
    submission: Submission,
    owner: User,
    group: Group | None,
    conversation: Conversation,
    state: WizardState,
) -> None:
    """Render the wizard message for ``state`` (used by back and /resume)."""
    selected: list[int] = list(conversation.payload.get("selected", []))

    if state is WizardState.AWAITING_DECISION:
        await service.submissions.set_status(submission, SubmissionStatus.AWAITING_DECISION)
        text, markup = render_decision(submission, owner, group, ctx.bot_username, False)
    elif state is WizardState.AWAITING_TAGS or state is WizardState.AWAITING_TAG_COUNT:
        conversation.payload["target"] = None
        await service.submissions.set_status(submission, SubmissionStatus.AWAITING_TAGS)
        conversation.state = WizardState.AWAITING_TAGS
        active = await tags_repo.list_active()
        text, markup = render_tags(
            active, selected, None, submission.short_id, group_title=_group_title(group)
        )
    else:  # AWAITING_CONFIRM / AWAITING_NOTE render the preview
        await service.submissions.set_status(submission, SubmissionStatus.AWAITING_CONFIRM)
        conversation.state = WizardState.AWAITING_CONFIRM
        active = await tags_repo.list_active()
        chosen = [t for t in active if t.id in selected]
        note = conversation.payload.get("note")
        text, markup = render_preview(submission, owner, group, chosen, note)
    await _edit_wizard(ctx, submission, text, markup)


async def handle_note_input(
    ctx: BotContext, session: AsyncSession, message: Message, conversation: Conversation
) -> None:
    """A text message arriving while state == AWAITING_NOTE becomes the note."""
    note = (message.text or "").strip()
    sid = str(conversation.payload.get("sid", ""))
    service = ctx.submission_service(session)
    submission = await service.submissions.get_by_short_id(sid)
    if submission is None or submission.status in TERMINAL_STATUSES:
        await ctx.api.send_message(message.chat.id, fa.ERR_EXPIRED)
        conversation.state = WizardState.IDLE
        await ctx.state_store(session).clear(conversation.chat_id, conversation.user_id)
        return
    if note:
        conversation.payload["note"] = note[:1000]
    # Return to the preview.
    conversation.state = WizardState.AWAITING_CONFIRM
    owner = await service.users.get_by_id(submission.user_id)
    assert owner is not None
    group = await session.get(Group, submission.group_id) if submission.group_id else None
    tags_repo = TagRepository(session)
    selected = list(conversation.payload.get("selected", []))
    chosen = [t for t in await tags_repo.list_active() if t.id in selected]
    text, markup = render_preview(
        submission, owner, group, chosen, conversation.payload.get("note")
    )
    await _edit_wizard(ctx, submission, text, markup)
    # Best-effort: remove the raw note message to keep the private chat clean.
    try:
        await ctx.api.delete_message(message.chat.id, message.message_id)
    except (BaleAPIError, NetworkError) as exc:
        logger.info("note_message_delete_failed", error=str(exc))
    await ctx.state_store(session).save(conversation, ctx.settings.submission_ttl_minutes)


async def resume_wizard(ctx: BotContext, session: AsyncSession, message: Message) -> bool:
    """Rebuild the wizard message after /resume; True when something resumed."""
    if message.from_user is None:
        return False
    store = ctx.state_store(session)
    conversation = await store.load(message.chat.id, message.from_user.id)
    if conversation is None or conversation.state is WizardState.IDLE:
        return False
    sid = str(conversation.payload.get("sid", ""))
    service = ctx.submission_service(session)
    submission = await service.submissions.get_by_short_id(sid)
    if submission is None or submission.status in TERMINAL_STATUSES:
        await store.clear(message.chat.id, message.from_user.id)
        return False
    owner = await service.users.get_by_id(submission.user_id)
    if owner is None:
        return False
    group = await session.get(Group, submission.group_id) if submission.group_id else None
    # Send a fresh wizard message and continue from the stored state.
    sent = await ctx.api.send_message(message.chat.id, fa.RESUME_HEADER)
    submission.wizard_chat_id = message.chat.id
    submission.wizard_message_id = sent.message_id
    tags_repo = TagRepository(session)
    await _render_state(
        ctx,
        session,
        service,
        tags_repo,
        submission,
        owner,
        group,
        conversation,
        conversation.state,
    )
    await store.save(conversation, ctx.settings.submission_ttl_minutes)
    return True
