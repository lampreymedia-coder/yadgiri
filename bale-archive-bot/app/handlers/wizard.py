"""The tagging wizard: decision → tag count → tag selection → preview → done.

All keyboard updates go through ``safe_edit`` (text + keyboard together).
State lives in Redis/Postgres, never in process memory; the back button
pops the history stack and never discards selections.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.bale.errors import BaleAPIError, Forbidden, NetworkError
from app.bale.keyboards import button, grid, keyboard, parse_callback, url_button
from app.bale.models import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from app.core.context import BotContext
from app.core.fsm import Conversation, WizardState
from app.core.locks import advisory_xact_lock
from app.db.models import Group, Submission, SubmissionStatus, Tag, User
from app.db.repositories.tags import TagRepository
from app.db.repositories.users import UserRepository
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

TERMINAL_STATUSES = (
    SubmissionStatus.COMPLETED,
    SubmissionStatus.DECLINED,
    SubmissionStatus.CANCELLED,
    SubmissionStatus.EXPIRED,
    SubmissionStatus.FAILED,
)


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


# ─── Rendering ───


def render_decision(
    submission: Submission, user: User, group: Group | None, bot_username: str, in_group: bool
) -> tuple[str, InlineKeyboardMarkup]:
    text = fa.decision_prompt(
        name=user.display_name or user.username or fa.fa_digits(user.bale_user_id),
        content_type=submission.content_type.value,
        group_title=(group.title if group else None) or "",
        dt=datetime.now(UTC),
    )
    rows = [
        [button(fa.BTN_SAVE_YES, ACT_DECISION_YES, submission.short_id)],
        [button(fa.BTN_SAVE_NO, ACT_DECISION_NO, submission.short_id)],
        [button(fa.BTN_CANCEL_DELETE, ACT_CANCEL, submission.short_id)],
    ]
    if in_group and bot_username:
        text = f"{text}\n\n{fa.group_fallback_hint(bot_username)}"
        rows.append([url_button(fa.BTN_OPEN_PRIVATE, f"https://ble.ir/{bot_username}")])
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
) -> tuple[str, InlineKeyboardMarkup]:
    text = fa.tag_select_prompt(len(selected_ids), target)
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


async def open_wizard(
    ctx: BotContext,
    session: AsyncSession,
    submission: Submission,
    user: User,
    group: Group | None,
) -> None:
    """Open the decision step in the user's private chat, falling back to
    an in-group single-message wizard when the user never started the bot."""
    text, markup = render_decision(submission, user, group, ctx.bot_username, in_group=False)
    users_repo = UserRepository(session)
    wizard_chat_id: int | None = None
    wizard_message_id: int | None = None
    in_group = False

    try:
        sent = await ctx.api.send_message(user.bale_user_id, text, markup)
        wizard_chat_id, wizard_message_id = user.bale_user_id, sent.message_id
        await users_repo.set_private_chat(user.id, True)
    except Forbidden:
        await users_repo.set_private_chat(user.id, False)
        in_group = True
    except (BaleAPIError, NetworkError) as exc:
        logger.warning("wizard_private_open_failed", error=str(exc))
        in_group = True

    if in_group and group is not None:
        group_text, group_markup = render_decision(
            submission, user, group, ctx.bot_username, in_group=True
        )
        sent = await ctx.api.send_message(
            group.bale_chat_id, group_text, group_markup, is_group=True
        )
        wizard_chat_id, wizard_message_id = group.bale_chat_id, sent.message_id

    if wizard_chat_id is None or wizard_message_id is None:
        logger.error("wizard_open_failed_completely", short_id=submission.short_id)
        return

    submission.wizard_chat_id = wizard_chat_id
    submission.wizard_message_id = wizard_message_id

    conversation = Conversation(chat_id=wizard_chat_id, user_id=user.bale_user_id)
    conversation.transition(WizardState.AWAITING_DECISION)
    conversation.payload = {"sid": submission.short_id, "selected": [], "target": None}
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

    service = SubmissionService(session, ctx.api, ctx.settings)
    submission = await service.submissions.get_by_short_id(data.sid)
    if submission is None or submission.status in TERMINAL_STATUSES:
        await _show_expired(ctx, cq)
        return

    owner = await service.users.get_by_id(submission.user_id)
    if owner is None or owner.bale_user_id != cq.from_user.id:
        await _answer(ctx, cq, fa.ERR_NOT_YOURS)
        return

    chat_id = submission.wizard_chat_id or cq.from_user.id
    await advisory_xact_lock(session, chat_id, owner.bale_user_id)

    store = ctx.state_store(session)
    conversation = await store.load(chat_id, owner.bale_user_id)
    if conversation is None:
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
        if conversation.state is WizardState.IDLE:
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
    conversation.payload = {
        "sid": submission.short_id,
        "selected": [t.id for t in submission.tags],
        "target": submission.meta.get("target_count"),
        "note": submission.meta.get("note"),
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
    target_raw = conversation.payload.get("target")
    target: int | None = int(target_raw) if target_raw is not None else None

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
        await service.submissions.set_status(submission, SubmissionStatus.AWAITING_TAG_COUNT)
        conversation.transition(WizardState.AWAITING_TAG_COUNT)
        active = await tags_repo.list_active()
        text, markup = render_tag_count(len(active), submission.short_id, conversation.can_go_back)
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
        await _edit_wizard(ctx, submission, fa.DECLINED_MESSAGE, None)
        conversation.state = WizardState.IDLE
        await _answer(ctx, cq)
        return True

    if action == ACT_CANCEL:
        await service.cancel_completely(submission)
        await _edit_wizard(ctx, submission, fa.CANCELLED_MESSAGE, None)
        conversation.state = WizardState.IDLE
        await _answer(ctx, cq)
        return True

    if action == ACT_TAG_COUNT:
        active = await tags_repo.list_active()
        new_target = None if arg == "free" else max(1, min(int(arg), len(active)))
        conversation.payload["target"] = new_target
        submission.meta = {**submission.meta, "target_count": new_target}
        # Preserve previous selections but trim overflow against a lower target.
        if new_target is not None and len(selected) > new_target:
            selected = selected[:new_target]
            conversation.payload["selected"] = selected
        await service.submissions.set_status(submission, SubmissionStatus.AWAITING_TAGS)
        conversation.transition(WizardState.AWAITING_TAGS)
        text, markup = render_tags(active, selected, new_target, submission.short_id)
        await _edit_wizard(ctx, submission, text, markup)
        await _answer(ctx, cq)
        return True

    if action == ACT_TOGGLE_TAG:
        tag_id = int(arg)
        active = await tags_repo.list_active()
        if tag_id in selected:
            selected.remove(tag_id)
        else:
            if target is not None and len(selected) >= target:
                # Limit reached: toast only, message unchanged.
                await _answer(ctx, cq, fa.toast_tag_limit(target))
                return False
            selected.append(tag_id)
        conversation.payload["selected"] = selected
        page = int(conversation.payload.get("page", 1))
        text, markup = render_tags(active, selected, target, submission.short_id, page)
        await _edit_wizard(ctx, submission, text, markup)
        await _answer(ctx, cq)
        return True

    if action == ACT_TAG_PAGE:
        page = int(arg) if arg else 1
        conversation.payload["page"] = page
        active = await tags_repo.list_active()
        text, markup = render_tags(active, selected, target, submission.short_id, page)
        await _edit_wizard(ctx, submission, text, markup)
        await _answer(ctx, cq)
        return True

    if action == ACT_TAGS_CONTINUE:
        if not selected:
            await _answer(ctx, cq, fa.TOAST_NO_TAG_SELECTED)
            return False
        if target is not None and len(selected) != target:
            await _answer(ctx, cq, fa.TOAST_NEED_FULL_COUNT)
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
        text, markup = render_tags(active, selected, target, submission.short_id)
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
        if group is not None:
            await service.publish_completed(refreshed, group, sender)
        else:
            await service.submissions.set_status(refreshed, SubmissionStatus.COMPLETED)
        hashtags = " ".join(t.hashtag for t in refreshed.tags)
        success = fa.success_message(
            refreshed.short_id,
            hashtags,
            (group.title if group else None) or "",
            ctx.settings.undo_window_minutes,
        )
        submission.wizard_chat_id = refreshed.wizard_chat_id = submission.wizard_chat_id
        await _edit_wizard(ctx, submission, success, None)
        await service.notify_admin_completed(refreshed, owner, group, media_details(refreshed))
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
    target_raw = conversation.payload.get("target")
    target: int | None = int(target_raw) if target_raw is not None else None

    if state is WizardState.AWAITING_DECISION:
        await service.submissions.set_status(submission, SubmissionStatus.AWAITING_DECISION)
        text, markup = render_decision(submission, owner, group, ctx.bot_username, False)
    elif state is WizardState.AWAITING_TAG_COUNT:
        await service.submissions.set_status(submission, SubmissionStatus.AWAITING_TAG_COUNT)
        active = await tags_repo.list_active()
        text, markup = render_tag_count(len(active), submission.short_id, conversation.can_go_back)
    elif state is WizardState.AWAITING_TAGS:
        await service.submissions.set_status(submission, SubmissionStatus.AWAITING_TAGS)
        active = await tags_repo.list_active()
        text, markup = render_tags(active, selected, target, submission.short_id)
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
    service = SubmissionService(session, ctx.api, ctx.settings)
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
    service = SubmissionService(session, ctx.api, ctx.settings)
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
