"""Final save of one confirmed wizard: the ONLY code that writes Post rows.

Called only after the sender pressed «بله»، picked at least one hashtag and
pressed «تأیید نهایی». Post + PostHashtag + PostMedia are one transaction.
The user's original message is never deleted or re-posted.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from app.bale.errors import BaleAPIError, NetworkError
from app.core.context import BotContext
from app.core.wizard_store import WizardSession
from app.db import repo
from app.domain.classify import classify
from app.domain.media_store import PendingDownload, bale_ref, download_all, local_path
from app.i18n import fa
from app.mapping import media_type
from app.observability.logging import get_logger

logger = get_logger(__name__)


class Outcome(enum.StrEnum):
    SAVED = "saved"
    DUPLICATE = "duplicate"
    TYPE_REJECTED = "type_rejected"
    GROUP_INACTIVE = "group_inactive"
    PERSON_INACTIVE = "person_inactive"
    NO_HASHTAG = "no_hashtag"
    FAILED = "failed"


@dataclass(slots=True)
class SaveResult:
    outcome: Outcome
    post_id: int | None = None
    hashtag_names: list[str] = field(default_factory=list)


async def _copy_to_archive(ctx: BotContext, session: WizardSession) -> dict[int, int]:
    """Backup copy inside Bale (ARCHIVE_CHAT_ID). Returns origin id → copy id."""
    archive = ctx.archive_chat_id
    copies: dict[int, int] = {}
    if archive is None:
        return copies
    for message_id in session.origin_message_ids:
        try:
            copies[message_id] = await ctx.api.copy_message(
                archive, session.origin_chat_id, message_id, is_group=True
            )
        except (BaleAPIError, NetworkError) as exc:
            logger.warning("archive_copy_failed", message_id=message_id, error=str(exc))
    return copies


async def _drop_archive_copies(ctx: BotContext, copies: dict[int, int]) -> None:
    if ctx.archive_chat_id is None:
        return
    for copy_id in copies.values():
        try:
            await ctx.api.delete_message(ctx.archive_chat_id, copy_id)
        except (BaleAPIError, NetworkError) as exc:
            logger.info("archive_copy_cleanup_failed", error=str(exc))


def _build_media(
    ctx: BotContext, session: WizardSession, copies: dict[int, int]
) -> tuple[list[repo.NewMedia], list[tuple[int, str, object, str]]]:
    """Rows for PostMedia plus the downloads to start after the commit."""
    rows: list[repo.NewMedia] = []
    planned: list[tuple[int, str, object, str]] = []  # (row index, file_id, path, fallback)
    for message in session.messages:
        classified = classify(message)
        code = media_type(classified.content_type)
        if code is None:
            continue
        copy_id = copies.get(message.message_id)
        if copy_id is not None and ctx.archive_chat_id is not None:
            ref = bale_ref(ctx.archive_chat_id, copy_id)
        else:
            ref = bale_ref(session.origin_chat_id, message.message_id)
        for info in classified.media:
            small = info.file_size is None or info.file_size <= ctx.settings.max_download_bytes
            if ctx.settings.media_download_enabled and small:
                path = local_path(ctx.settings.media_root, classified.content_type, info)
                storage = str(path)
                planned.append((len(rows), info.file_id, path, ref))
            else:
                storage = ref
            rows.append(
                repo.NewMedia(
                    media_type=code,
                    storage_path=storage,
                    bale_file_id=info.file_id,
                    file_name=info.file_name,
                    file_size=info.file_size,
                    mime_type=info.mime_type,
                    duration=info.duration,
                    width=info.width,
                    height=info.height,
                )
            )
    return rows, planned


async def save_confirmed(ctx: BotContext, session: WizardSession) -> SaveResult:
    if not session.selected:
        return SaveResult(Outcome.NO_HASHTAG)

    async with ctx.db.tx() as conn:
        group = await repo.get_active_group(conn, session.group.bale_group_id)
        if group is None:
            return SaveResult(Outcome.GROUP_INACTIVE)
        person = await repo.get_person(conn, session.user_id)
        if person is None or not person.is_active:
            return SaveResult(Outcome.PERSON_INACTIVE)
        if await repo.post_exists(conn, group.id, session.primary_message_id):
            return SaveResult(Outcome.DUPLICATE)
        active = {tag.id: tag.name for tag in await repo.active_hashtags(conn)}
    chosen = [tag_id for tag_id in session.selected if tag_id in active]
    if not chosen:
        return SaveResult(Outcome.NO_HASHTAG)
    names = [active[tag_id] for tag_id in chosen]

    copies = await _copy_to_archive(ctx, session)
    media_rows, planned = _build_media(ctx, session, copies)
    new_post = repo.NewPost(
        person_id=person.id,
        ehya_group_id=group.id,
        bale_message_id=session.primary_message_id,
        content_type=session.content_type,
        content_text=session.content_text or "",
        posted_at=session.posted_at,
        hashtag_ids=chosen,
        media=media_rows,
    )
    try:
        async with ctx.db.tx() as conn:
            post_id, media_ids = await repo.insert_post(conn, new_post)
    except repo.DuplicatePost:
        await _drop_archive_copies(ctx, copies)
        return SaveResult(Outcome.DUPLICATE)
    except repo.ContentTypeRejected as exc:
        logger.error("post_check_rejected", error=str(exc), content_type=session.content_type)
        await _drop_archive_copies(ctx, copies)
        return SaveResult(Outcome.TYPE_REJECTED)
    except Exception:
        logger.exception("post_save_failed", sid=session.sid)
        await _drop_archive_copies(ctx, copies)
        return SaveResult(Outcome.FAILED)

    logger.info("post_saved", post_id=post_id, group=group.id, tags=chosen, files=len(media_ids))
    if copies and ctx.archive_chat_id is not None:
        first_copy = copies[min(copies)]
        try:
            await ctx.api.send_message(
                ctx.archive_chat_id,
                fa.archive_footer(session.sender_name, group.name, names, post_id),
                reply_to_message_id=first_copy,
                is_group=True,
            )
        except (BaleAPIError, NetworkError) as exc:
            logger.info("archive_footer_failed", error=str(exc))

    jobs = [
        PendingDownload(media_ids[index], file_id, path, fallback)  # type: ignore[arg-type]
        for index, file_id, path, fallback in planned
    ]
    if jobs:
        ctx.spawn(download_all(ctx, jobs))
    return SaveResult(Outcome.SAVED, post_id, names)
