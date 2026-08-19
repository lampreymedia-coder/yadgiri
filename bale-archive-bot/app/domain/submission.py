"""Submission lifecycle: the Archive → Persist → Delete → Wizard → Repost flow.

Golden rule: the original group message is NEVER deleted before both the
archive copy and the database row exist. Failing to delete is always better
than losing data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.bale.errors import BaleAPIError, Forbidden, NetworkError
from app.bale.methods import BaleAPI
from app.bale.models import Message
from app.config import Settings
from app.db.models import ContentType, Group, Submission, SubmissionStatus, User
from app.db.repositories.groups import GroupRepository
from app.db.repositories.outbox import OutboxRepository
from app.db.repositories.submissions import SubmissionRepository
from app.db.repositories.users import UserRepository
from app.domain.classify import ClassifiedContent
from app.i18n import fa
from app.observability import metrics
from app.observability.logging import get_logger

logger = get_logger(__name__)

CAPTION_LIMIT = 1024
TEXT_LIMIT = 4096


@dataclass(slots=True)
class IntakeResult:
    """Outcome of the gateway intake for one (possibly multi-media) message."""

    submission: Submission | None
    deleted_original: bool
    archived: bool
    failure_reason: str | None = None


class SubmissionService:
    """Coordinates the archive-first gateway and publication."""

    def __init__(self, session: AsyncSession, api: BaleAPI, settings: Settings) -> None:
        self._session = session
        self._api = api
        self._settings = settings
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
        """Archive + persist + (maybe) delete. Never deletes before steps 2 & 3."""
        primary = messages[0]
        content_type = classified.content_type
        if len(messages) > 1:
            content_type = ContentType.ALBUM

        # Step 2: copy every message to the private archive channel first.
        archive_ids: list[int] = []
        archived = True
        failure_reason: str | None = None
        for message in messages:
            try:
                new_id = await self._api.copy_message(
                    chat_id=self._settings.archive_chat_id,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                )
                archive_ids.append(new_id)
            except (BaleAPIError, NetworkError) as exc:
                archived = False
                failure_reason = f"archive copy failed: {exc}"
                logger.error(
                    "archive_copy_failed",
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    error=str(exc),
                )
                break

        if not archived:
            # Do NOT delete; do NOT proceed. Alert the admin via outbox.
            await self._alert_admin_intake_failure(failure_reason or "archive unavailable")
            return IntakeResult(
                submission=None,
                deleted_original=False,
                archived=False,
                failure_reason=failure_reason,
            )

        # Step 3: persist the draft (failure here also blocks deletion, by
        # construction: an exception aborts the transaction and the caller's
        # error handler leaves the group message untouched).
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
        submission.archive_chat_id = self._settings.archive_chat_id
        submission.archive_message_id = archive_ids[0] if archive_ids else None
        submission.meta = {
            **submission.meta,
            "archive_message_ids": archive_ids,
            "origin_chat_id": primary.chat.id,
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

        # Step 4: delete originals — only now, after archive + DB succeeded.
        deleted = True
        if group is not None:
            for message in messages:
                try:
                    await self._api.delete_message(message.chat.id, message.message_id)
                except Forbidden:
                    deleted = False
                    await self.groups.set_can_delete(group.id, False)
                    logger.warning("delete_forbidden", chat_id=message.chat.id)
                    break
                except (BaleAPIError, NetworkError) as exc:
                    deleted = False
                    logger.warning("delete_failed", chat_id=message.chat.id, error=str(exc))
                    break
            if deleted:
                await self.groups.set_can_delete(group.id, True)

        await self.submissions.set_status(submission, SubmissionStatus.AWAITING_DECISION)
        return IntakeResult(submission=submission, deleted_original=deleted, archived=True)

    async def _alert_admin_intake_failure(self, reason: str) -> None:
        if self._settings.admin_chat_id is not None:
            await self.outbox.enqueue(
                "admin_notify",
                self._settings.admin_chat_id,
                {"text": fa.admin_intake_failure_alert(reason)},
            )

    # ─── Publication ───

    def _published_text(self, submission: Submission, sender_name: str) -> tuple[str, str | None]:
        """Return (caption_or_text, overflow_reply_text)."""
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
        # Over the limit: media goes out with the short header only and the
        # full text follows as a separate reply message.
        return header, combined[:TEXT_LIMIT]

    async def publish_completed(
        self, submission: Submission, group: Group, sender_name: str
    ) -> None:
        """Publish the tagged content back into the group (status=completed)."""
        caption, overflow = self._published_text(submission, sender_name)
        published_id: int
        if submission.content_type in (
            ContentType.TEXT,
            ContentType.LINK,
            ContentType.CONTACT,
            ContentType.LOCATION,
        ):
            sent = await self._api.send_message(group.bale_chat_id, caption, is_group=True)
            published_id = sent.message_id
        else:
            assert submission.archive_message_id is not None
            published_id = await self._api.copy_message(
                chat_id=group.bale_chat_id,
                from_chat_id=submission.archive_chat_id or self._settings.archive_chat_id,
                message_id=submission.archive_message_id,
                caption=caption,
                is_group=True,
            )
            for extra_id in list(submission.meta.get("archive_message_ids", []))[1:]:
                await self._api.copy_message(
                    chat_id=group.bale_chat_id,
                    from_chat_id=submission.archive_chat_id or self._settings.archive_chat_id,
                    message_id=int(extra_id),
                    is_group=True,
                )
        if overflow:
            await self._api.send_message(
                group.bale_chat_id,
                overflow,
                reply_to_message_id=published_id,
                is_group=True,
            )
        submission.published_message_id = published_id
        await self.submissions.set_status(submission, SubmissionStatus.COMPLETED)
        metrics.submissions_total.labels(status=SubmissionStatus.COMPLETED.value).inc()

    async def republish_without_tags(
        self, submission: Submission, group: Group, sender_name: str, status: SubmissionStatus
    ) -> None:
        """Repost the original content with the 📎 prefix (declined/expired)."""
        header = fa.republished_header(sender_name)
        if submission.content_type in (
            ContentType.TEXT,
            ContentType.LINK,
            ContentType.CONTACT,
            ContentType.LOCATION,
        ):
            body = submission.text_content or ""
            text = f"{header}\n\n{body}" if body else header
            sent = await self._api.send_message(
                group.bale_chat_id, text[:TEXT_LIMIT], is_group=True
            )
            submission.published_message_id = sent.message_id
        else:
            assert submission.archive_message_id is not None
            caption_body = submission.caption or ""
            caption = f"{header}\n\n{caption_body}" if caption_body else header
            new_id = await self._api.copy_message(
                chat_id=group.bale_chat_id,
                from_chat_id=submission.archive_chat_id or self._settings.archive_chat_id,
                message_id=submission.archive_message_id,
                caption=caption[:CAPTION_LIMIT],
                is_group=True,
            )
            submission.published_message_id = new_id
            for extra_id in list(submission.meta.get("archive_message_ids", []))[1:]:
                await self._api.copy_message(
                    chat_id=group.bale_chat_id,
                    from_chat_id=submission.archive_chat_id or self._settings.archive_chat_id,
                    message_id=int(extra_id),
                    is_group=True,
                )
        await self.submissions.set_status(submission, status)
        metrics.submissions_total.labels(status=status.value).inc()

    async def cancel_completely(self, submission: Submission) -> None:
        """User chose full cancellation: nothing is reposted."""
        await self.submissions.set_status(submission, SubmissionStatus.CANCELLED)
        metrics.submissions_total.labels(status=SubmissionStatus.CANCELLED.value).inc()

    async def undo(self, submission: Submission, group: Group | None) -> bool:
        """Undo a completed submission inside the undo window."""
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
        if group is not None and submission.published_message_id is not None:
            try:
                await self._api.delete_message(group.bale_chat_id, submission.published_message_id)
            except (BaleAPIError, NetworkError) as exc:
                logger.warning("undo_delete_failed", error=str(exc))
        await self.submissions.set_status(submission, SubmissionStatus.CANCELLED)
        metrics.submissions_total.labels(status="undone").inc()
        return True

    # ─── Admin notification ───

    async def notify_admin_completed(
        self, submission: Submission, user: User, group: Group | None, details: str
    ) -> None:
        if self._settings.admin_chat_id is None:
            return
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
        )
        await self.outbox.enqueue("admin_notify", self._settings.admin_chat_id, {"text": text})


def _split_media(messages: list[Message], classified: ClassifiedContent) -> list[list[Any]]:
    """Map media items back onto their source messages (album support)."""
    if len(messages) <= 1:
        return [classified.media]
    from app.domain.classify import classify

    return [classify(message).media for message in messages]
