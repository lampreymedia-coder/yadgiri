"""Submission lifecycle: persist in SQL, then copy into per-hashtag archives.

The original message in the research group is never deleted and never
republished. Bot prompts live in a private chat with the sender. Confirmed
items are copied into each selected hashtag's private archive group. SQL is
the source of truth even when an archive chat is not bound yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.bale.errors import BaleAPIError, NetworkError
from app.bale.methods import BaleAPI
from app.bale.models import Message
from app.config import Settings
from app.db.models import ContentType, Group, Submission, SubmissionStatus, User
from app.db.repositories.groups import GroupRepository
from app.db.repositories.outbox import OutboxRepository
from app.db.repositories.submissions import SubmissionRepository
from app.db.repositories.users import UserRepository
from app.domain.classify import ClassifiedContent
from app.domain.group_roles import resolve_archive_chat_id, try_delete_message
from app.i18n import fa
from app.observability import metrics
from app.observability.logging import get_logger

logger = get_logger(__name__)

CAPTION_LIMIT = 1024
TEXT_LIMIT = 4096
_SEND_STORED_TEXT = {ContentType.TEXT, ContentType.LINK}


@dataclass(slots=True)
class IntakeResult:
    """Outcome of the gateway intake for one (possibly multi-media) message."""

    submission: Submission | None
    deleted_original: bool
    archived: bool
    failure_reason: str | None = None


class SubmissionService:
    """Coordinates the archive-first gateway and publication."""

    def __init__(
        self,
        session: AsyncSession,
        api: BaleAPI,
        settings: Settings,
        archive_chat_id: int | None = None,
        admin_chat_id: int | None = None,
        extra_admin_ids: set[int] | None = None,
    ) -> None:
        self._session = session
        self._api = api
        self._settings = settings
        self._archive_chat_id = (
            archive_chat_id if archive_chat_id is not None else settings.archive_chat_id
        )
        self._admin_chat_id = admin_chat_id if admin_chat_id is not None else settings.admin_chat_id
        self._extra_admin_ids = set(extra_admin_ids or ())
        self.submissions = SubmissionRepository(session)
        self.users = UserRepository(session)
        self.groups = GroupRepository(session)
        self.outbox = OutboxRepository(session)

    # ─── Intake ───

    async def intake(
        self,
        messages: list[Message],
        classified: ClassifiedContent,
        user: User,
        group: Group | None,
        raw_update: dict[str, Any] | None,
    ) -> IntakeResult:
        """Persist a draft. The original group message is left in place."""
        primary = messages[0]
        content_type = classified.content_type
        if len(messages) > 1:
            content_type = ContentType.ALBUM

        submission = await self.submissions.create_draft(
            user_id=user.id,
            group_id=group.id if group else None,
            content_type=content_type,
            content_subtype=classified.content_subtype,
            text_content=classified.text_content,
            text_normalized=classified.text_normalized,
            caption=classified.caption,
            urls=classified.urls,
            is_forwarded=classified.is_forwarded,
            forward_source=classified.forward_source,
            original_message_id=primary.message_id,
            raw_update=raw_update,
            ttl_minutes=self._settings.submission_ttl_minutes,
        )
        submission.meta = {
            **submission.meta,
            "origin_chat_id": primary.chat.id,
            "origin_message_ids": [message.message_id for message in messages],
        }
        for position, (_message, media_list) in enumerate(
            zip(messages, _split_media(messages, classified), strict=False)
        ):
            for info in media_list:
                await self.submissions.add_media(
                    submission,
                    bale_file_id=info.file_id,
                    position=position,
                    bale_file_unique=info.file_unique_id,
                    file_name=info.file_name,
                    mime_type=info.mime_type,
                    file_size_bytes=info.file_size,
                    duration_seconds=info.duration,
                    width=info.width,
                    height=info.height,
                )

        await self.submissions.set_status(submission, SubmissionStatus.AWAITING_DECISION)
        return IntakeResult(submission=submission, deleted_original=False, archived=True)

    def apply_content_update(
        self,
        submission: Submission,
        classified: ClassifiedContent,
        raw_update: dict[str, Any] | None,
    ) -> None:
        """Overwrite stored text/caption with the latest origin edit."""
        if (
            classified.content_type in _SEND_STORED_TEXT
            and submission.content_type in _SEND_STORED_TEXT
        ):
            submission.content_type = classified.content_type
        submission.text_content = classified.text_content
        submission.text_normalized = classified.text_normalized
        submission.caption = classified.caption
        submission.urls = list(classified.urls)
        if raw_update is not None:
            submission.raw_update = raw_update
        submission.updated_at = datetime.now(UTC)
        submission.meta = {**submission.meta, "origin_edited": True}
        if classified.media and submission.media_files:
            first = classified.media[0]
            media = submission.media_files[0]
            media.bale_file_id = first.file_id
            if first.file_unique_id:
                media.bale_file_unique = first.file_unique_id
            if first.file_name:
                media.file_name = first.file_name
            if first.mime_type:
                media.mime_type = first.mime_type

    async def _alert_admin_intake_failure(self, reason: str) -> None:
        await self._notify_admins(fa.admin_intake_failure_alert(reason))

    async def _admin_destinations(self) -> set[int]:
        destinations: set[int] = set(self._extra_admin_ids)
        if self._admin_chat_id is not None:
            destinations.add(self._admin_chat_id)
        for admin in await self.users.list_admins():
            destinations.add(admin.bale_user_id)
        return destinations

    async def _notify_admins(self, text: str) -> None:
        for dest in await self._admin_destinations():
            await self.outbox.enqueue("admin_notify", dest, {"text": text})

    # ─── Archive copies (on confirm) ───

    def _archive_footer(self, submission: Submission, sender_name: str) -> str:
        hashtags = " ".join(tag.hashtag for tag in submission.tags) or "—"
        return fa.archive_footer(
            sender_name, hashtags, submission.content_type.value, submission.short_id
        )

    def _origin_message_ids(self, submission: Submission) -> list[int]:
        stored = submission.meta.get("origin_message_ids")
        if isinstance(stored, list) and stored:
            return [int(item) for item in stored]
        if submission.original_message_id is not None:
            return [submission.original_message_id]
        return []

    async def complete_into_tag_archives(
        self, submission: Submission, sender_name: str
    ) -> list[str]:
        """Copy origin content into each selected tag's archive group.

        Returns hashtags that had no archive group (SQL is still saved).
        """
        origin_chat = submission.meta.get("origin_chat_id")
        origin_ids = self._origin_message_ids(submission)
        footer = self._archive_footer(submission, sender_name)
        copies: dict[str, list[int]] = {}
        missing: list[str] = []

        for tag in submission.tags:
            dest = await resolve_archive_chat_id(self._session, tag.slug)
            if dest is None:
                missing.append(tag.hashtag)
                continue
            copied_ids = await self._copy_origin_to_archive(
                dest, origin_chat, origin_ids, footer, submission, sender_name
            )
            if copied_ids:
                copies[tag.slug] = copied_ids

        if copies:
            first_slug = next(iter(copies))
            first_ids = copies[first_slug]
            submission.archive_chat_id = await resolve_archive_chat_id(self._session, first_slug)
            submission.archive_message_id = first_ids[0] if first_ids else None
        submission.meta = {
            **submission.meta,
            "tag_archive_copies": copies,
            "missing_archives": missing,
        }
        await self.submissions.set_status(submission, SubmissionStatus.COMPLETED)
        metrics.submissions_total.labels(status=SubmissionStatus.COMPLETED.value).inc()
        return missing

    async def refresh_archive_copies(self, submission: Submission, sender_name: str) -> None:
        """Replace already-archived copies with the latest stored content."""
        copies = submission.meta.get("tag_archive_copies") or {}
        if not isinstance(copies, dict):
            copies = {}
        for slug, ids in copies.items():
            dest = await resolve_archive_chat_id(self._session, str(slug))
            if dest is None:
                continue
            for message_id in ids or []:
                await try_delete_message(self._api, dest, int(message_id))
        origin_chat = submission.meta.get("origin_chat_id")
        origin_ids = self._origin_message_ids(submission)
        footer = self._archive_footer(submission, sender_name)
        new_copies: dict[str, list[int]] = {}
        missing: list[str] = []
        for tag in submission.tags:
            dest = await resolve_archive_chat_id(self._session, tag.slug)
            if dest is None:
                missing.append(tag.hashtag)
                continue
            copied_ids = await self._copy_origin_to_archive(
                dest, origin_chat, origin_ids, footer, submission, sender_name
            )
            if copied_ids:
                new_copies[tag.slug] = copied_ids
        if new_copies:
            first_slug = next(iter(new_copies))
            first_ids = new_copies[first_slug]
            submission.archive_chat_id = await resolve_archive_chat_id(self._session, first_slug)
            submission.archive_message_id = first_ids[0] if first_ids else None
        submission.meta = {
            **submission.meta,
            "tag_archive_copies": new_copies,
            "missing_archives": missing,
        }

    async def _copy_origin_to_archive(
        self,
        dest_chat_id: int,
        origin_chat: Any,
        origin_ids: list[int],
        footer: str,
        submission: Submission,
        sender_name: str,
    ) -> list[int]:
        copied: list[int] = []
        use_stored_text = submission.content_type in _SEND_STORED_TEXT
        if use_stored_text:
            fallback_id = await self._send_archive_fallback(dest_chat_id, submission, sender_name)
            if fallback_id is not None:
                copied.append(fallback_id)
        elif isinstance(origin_chat, int) and origin_ids:
            caption_override = None
            caption = submission.caption or ""
            if submission.meta.get("origin_edited") and 0 < len(caption) <= CAPTION_LIMIT:
                caption_override = caption
            for message_id in origin_ids:
                try:
                    new_id = await self._api.copy_message(
                        chat_id=dest_chat_id,
                        from_chat_id=origin_chat,
                        message_id=message_id,
                        caption=caption_override,
                        is_group=True,
                    )
                    copied.append(new_id)
                except (BaleAPIError, NetworkError) as exc:
                    logger.warning(
                        "tag_archive_copy_failed",
                        dest=dest_chat_id,
                        origin=origin_chat,
                        message_id=message_id,
                        error=str(exc),
                    )
        if not copied:
            fallback_id = await self._send_archive_fallback(dest_chat_id, submission, sender_name)
            if fallback_id is not None:
                copied.append(fallback_id)
        if copied:
            try:
                await self._api.send_message(
                    dest_chat_id,
                    footer,
                    reply_to_message_id=copied[0],
                    is_group=True,
                )
            except (BaleAPIError, NetworkError) as exc:
                logger.info("archive_footer_failed", dest=dest_chat_id, error=str(exc))
        return copied

    async def _send_archive_fallback(
        self, dest_chat_id: int, submission: Submission, sender_name: str
    ) -> int | None:
        caption, overflow = self._published_text(submission, sender_name)
        try:
            sent = await self._api.send_message(dest_chat_id, caption, is_group=True)
        except (BaleAPIError, NetworkError) as exc:
            logger.warning("archive_fallback_send_failed", dest=dest_chat_id, error=str(exc))
            return None
        if overflow:
            try:
                await self._api.send_message(
                    dest_chat_id,
                    overflow,
                    reply_to_message_id=sent.message_id,
                    is_group=True,
                )
            except (BaleAPIError, NetworkError) as exc:
                logger.info("archive_fallback_overflow_failed", error=str(exc))
        return sent.message_id

    def _published_text(self, submission: Submission, sender_name: str) -> tuple[str, str | None]:
        """Return (caption_or_text, overflow_reply_text) for fallback sends."""
        hashtags = " ".join(tag.hashtag for tag in submission.tags)
        header = fa.published_header(sender_name, hashtags)
        body = submission.text_content or submission.caption or ""
        is_text_only = submission.content_type in (
            ContentType.TEXT,
            ContentType.LINK,
            ContentType.CONTACT,
            ContentType.LOCATION,
        )
        limit = TEXT_LIMIT if is_text_only else CAPTION_LIMIT
        combined = f"{header}\n\n{body}" if body else header
        if len(combined) <= limit:
            return combined, None
        return header, combined[:TEXT_LIMIT]

    async def publish_completed(
        self, submission: Submission, group: Group, sender_name: str
    ) -> None:
        """Complete into per-tag archive groups. ``group`` is the source research chat."""
        del group
        await self.complete_into_tag_archives(submission, sender_name)

    async def republish_without_tags(
        self, submission: Submission, group: Group, sender_name: str, status: SubmissionStatus
    ) -> None:
        """Leave the original in the research group; do not duplicate it."""
        del group, sender_name
        await self.submissions.set_status(submission, status)
        metrics.submissions_total.labels(status=status.value).inc()

    async def cancel_completely(self, submission: Submission) -> None:
        """User cancelled tagging. The original group message stays."""
        await self.submissions.set_status(submission, SubmissionStatus.CANCELLED)
        metrics.submissions_total.labels(status=SubmissionStatus.CANCELLED.value).inc()

    async def undo(self, submission: Submission, group: Group | None) -> bool:
        """Undo a completed submission inside the undo window."""
        del group
        if submission.status is not SubmissionStatus.COMPLETED:
            return False
        if submission.completed_at is None:
            return False
        completed_at = submission.completed_at
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=UTC)
        age_minutes = (datetime.now(UTC) - completed_at).total_seconds() / 60.0
        if age_minutes > self._settings.undo_window_minutes:
            return False
        copies = submission.meta.get("tag_archive_copies") or {}
        if isinstance(copies, dict):
            for slug, ids in copies.items():
                dest = await resolve_archive_chat_id(self._session, str(slug))
                if dest is None:
                    continue
                for message_id in ids or []:
                    await try_delete_message(self._api, dest, int(message_id))
        await self.submissions.set_status(submission, SubmissionStatus.CANCELLED)
        metrics.submissions_total.labels(status="undone").inc()
        return True

    # ─── Admin notification ───

    async def notify_admin_completed(
        self,
        submission: Submission,
        user: User,
        group: Group | None,
        details: str,
        missing_archives: list[str] | None = None,
    ) -> None:
        hashtags = " ".join(tag.hashtag for tag in submission.tags)
        today_total = await self.submissions.count_completed_today()
        text = fa.admin_new_submission(
            name=user.display_name or (user.username or str(user.bale_user_id)),
            bale_user_id=user.bale_user_id,
            group_title=(group.title if group else None) or "",
            content_type=submission.content_type.value,
            details=details,
            hashtags=hashtags,
            short_id=submission.short_id,
            dt=datetime.now(UTC),
            today_total=today_total,
            missing_archives=missing_archives or [],
        )
        await self._notify_admins(text)
        if missing_archives:
            await self._notify_admins(fa.missing_archive_howto(missing_archives))


def _split_media(messages: list[Message], classified: ClassifiedContent) -> list[list[Any]]:
    """Map media items back onto their source messages (album support)."""
    if len(messages) <= 1:
        return [classified.media]
    from app.domain.classify import classify

    return [classify(message).media for message in messages]
