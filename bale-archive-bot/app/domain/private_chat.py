"""Keep the user-bot private chat uncluttered after a decision.

Decided items drop the subject copy and wizard prompt. A short summary is
shown, then deleted after ``PRIVATE_SUMMARY_TTL_SECONDS``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.bale.errors import BaleAPIError, NetworkError
from app.core.context import BotContext
from app.db.models import Submission
from app.domain.group_roles import try_delete_message
from app.observability.logging import get_logger

logger = get_logger(__name__)

META_SUBJECT = "subject_message_id"
META_REMINDER = "reminder_message_id"
META_REMINDERS = "reminder_message_ids"
META_EPHEMERAL_CHAT = "ephemeral_chat_id"
META_EPHEMERAL_IDS = "ephemeral_message_ids"
META_EPHEMERAL_AT = "ephemeral_delete_at"


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return None


def _as_int_list(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    found: list[int] = []
    for item in value:
        parsed = _as_int(item)
        if parsed is not None:
            found.append(parsed)
    return found


def parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def meta_of(submission: Submission) -> dict[str, Any]:
    raw = submission.meta
    return dict(raw) if isinstance(raw, dict) else {}


def private_residue_ids(submission: Submission) -> list[int]:
    """Message ids the bot posted in the private wizard thread."""
    meta = meta_of(submission)
    ids: list[int] = []
    for key in (META_SUBJECT, META_REMINDER):
        parsed = _as_int(meta.get(key))
        if parsed is not None:
            ids.append(parsed)
    ids.extend(_as_int_list(meta.get(META_REMINDERS)))
    ids.extend(_as_int_list(meta.get(META_EPHEMERAL_IDS)))
    if submission.wizard_message_id is not None:
        ids.append(int(submission.wizard_message_id))
    # Preserve order, drop duplicates.
    seen: set[int] = set()
    unique: list[int] = []
    for item in ids:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def private_chat_id(submission: Submission) -> int | None:
    meta = meta_of(submission)
    ephemeral = _as_int(meta.get(META_EPHEMERAL_CHAT))
    if ephemeral is not None:
        return ephemeral
    if submission.wizard_chat_id is not None:
        return int(submission.wizard_chat_id)
    return None


def clear_private_message_meta(submission: Submission) -> dict[str, Any]:
    meta = meta_of(submission)
    meta[META_SUBJECT] = None
    meta[META_REMINDER] = None
    meta[META_REMINDERS] = []
    submission.wizard_message_id = None
    return meta


async def delete_private_ids(ctx: BotContext, chat_id: int | None, message_ids: list[int]) -> None:
    for message_id in message_ids:
        await try_delete_message(ctx.api, chat_id, message_id)


async def settle_private_chat(ctx: BotContext, submission: Submission, summary: str) -> None:
    """Delete leftover wizard traffic and leave a short, time-limited summary."""
    chat_id = private_chat_id(submission)
    residue = private_residue_ids(submission)
    await delete_private_ids(ctx, chat_id, residue)
    meta = clear_private_message_meta(submission)
    if chat_id is None:
        meta[META_EPHEMERAL_CHAT] = None
        meta[META_EPHEMERAL_IDS] = []
        meta[META_EPHEMERAL_AT] = None
        submission.meta = meta
        return
    try:
        sent = await ctx.api.send_message(chat_id, summary)
    except (BaleAPIError, NetworkError) as exc:
        logger.info("private_summary_failed", error=str(exc), short_id=submission.short_id)
        meta[META_EPHEMERAL_CHAT] = None
        meta[META_EPHEMERAL_IDS] = []
        meta[META_EPHEMERAL_AT] = None
        submission.meta = meta
        return
    ttl = max(0, int(ctx.settings.private_summary_ttl_seconds))
    delete_at = datetime.now(UTC) + timedelta(seconds=ttl)
    meta[META_EPHEMERAL_CHAT] = chat_id
    meta[META_EPHEMERAL_IDS] = [sent.message_id]
    meta[META_EPHEMERAL_AT] = delete_at.isoformat()
    submission.wizard_chat_id = chat_id
    submission.meta = meta


async def sweep_private_ephemeral(ctx: BotContext, *, max_submissions: int = 5) -> int:
    """Delete due summaries and leftover private messages of decided items.

    Bounded per run so a large backlog cannot occupy the process for minutes.
    """
    deleted = 0
    now = datetime.now(UTC)
    async with ctx.db.session() as session:
        service = ctx.submission_service(session)
        rows = await service.submissions.list_terminal_private_residue()
        for submission in rows[:max_submissions]:
            meta = meta_of(submission)
            chat_id = private_chat_id(submission)
            due_at = parse_utc(meta.get(META_EPHEMERAL_AT))
            ephemeral_ids = _as_int_list(meta.get(META_EPHEMERAL_IDS))
            residue = private_residue_ids(submission)
            leftover = [mid for mid in residue if mid not in set(ephemeral_ids)]
            if leftover:
                await delete_private_ids(ctx, chat_id, leftover)
                deleted += len(leftover)
                meta = clear_private_message_meta(submission)
                meta[META_EPHEMERAL_CHAT] = meta.get(META_EPHEMERAL_CHAT) or chat_id
                meta[META_EPHEMERAL_IDS] = ephemeral_ids
                meta[META_EPHEMERAL_AT] = meta.get(META_EPHEMERAL_AT)
                submission.meta = meta
            if ephemeral_ids and (due_at is None or due_at <= now):
                await delete_private_ids(ctx, chat_id, ephemeral_ids)
                deleted += len(ephemeral_ids)
                meta = meta_of(submission)
                meta[META_EPHEMERAL_CHAT] = None
                meta[META_EPHEMERAL_IDS] = []
                meta[META_EPHEMERAL_AT] = None
                submission.meta = meta
                submission.wizard_message_id = None
    return deleted
