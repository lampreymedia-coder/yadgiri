"""Submission lifecycle persistence."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    IN_PROGRESS_STATUSES,
    TERMINAL_STATUSES,
    ContentType,
    MediaFile,
    Submission,
    SubmissionStatus,
    SubmissionTag,
    utcnow,
)

_BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def generate_short_id() -> str:
    """6-char base36 id used in callback_data and as the tracking code."""
    return "".join(random.choice(_BASE36) for _ in range(6))


class SubmissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_draft(
        self,
        user_id: int,
        group_id: int | None,
        content_type: ContentType,
        content_subtype: str | None,
        text_content: str | None,
        text_normalized: str | None,
        caption: str | None,
        urls: list[str],
        is_forwarded: bool,
        forward_source: str | None,
        original_message_id: int | None,
        raw_update: dict[str, Any] | None,
        ttl_minutes: int,
    ) -> Submission:
        short_id = generate_short_id()
        # Regenerate on the (rare) collision.
        while await self.get_by_short_id(short_id) is not None:
            short_id = generate_short_id()
        submission = Submission(
            short_id=short_id,
            user_id=user_id,
            group_id=group_id,
            content_type=content_type,
            content_subtype=content_subtype,
            text_content=text_content,
            text_normalized=text_normalized,
            caption=caption,
            urls=urls,
            is_forwarded=is_forwarded,
            forward_source=forward_source,
            original_message_id=original_message_id,
            raw_update=raw_update,
            expires_at=datetime.now(UTC) + timedelta(minutes=ttl_minutes),
        )
        self._session.add(submission)
        await self._session.flush()
        return submission

    async def get_by_short_id(self, short_id: str) -> Submission | None:
        result = await self._session.execute(
            select(Submission)
            .options(selectinload(Submission.tags), selectinload(Submission.media_files))
            .where(Submission.short_id == short_id)
        )
        return result.scalar_one_or_none()

    async def get(self, submission_id: int) -> Submission | None:
        result = await self._session.execute(
            select(Submission)
            .options(selectinload(Submission.tags), selectinload(Submission.media_files))
            .where(Submission.id == submission_id)
        )
        return result.scalar_one_or_none()

    async def set_status(self, submission: Submission, status: SubmissionStatus) -> None:
        submission.status = status
        submission.updated_at = utcnow()
        if status is SubmissionStatus.COMPLETED:
            submission.completed_at = utcnow()

    async def set_tags(self, submission: Submission, tag_ids: list[int]) -> None:
        await self._session.execute(
            delete(SubmissionTag).where(SubmissionTag.submission_id == submission.id)
        )
        for tag_id in tag_ids:
            self._session.add(SubmissionTag(submission_id=submission.id, tag_id=tag_id))
        await self._session.flush()

    async def add_media(
        self,
        submission: Submission,
        bale_file_id: str,
        position: int = 0,
        bale_file_unique: str | None = None,
        file_name: str | None = None,
        mime_type: str | None = None,
        file_size_bytes: int | None = None,
        duration_seconds: int | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> MediaFile:
        media = MediaFile(
            submission_id=submission.id,
            position=position,
            bale_file_id=bale_file_id,
            bale_file_unique=bale_file_unique,
            file_name=file_name,
            mime_type=mime_type,
            file_size_bytes=file_size_bytes,
            duration_seconds=duration_seconds,
            width=width,
            height=height,
        )
        self._session.add(media)
        await self._session.flush()
        return media

    async def count_recent_by_user(self, user_id: int, minutes: int = 60) -> int:
        threshold = datetime.now(UTC) - timedelta(minutes=minutes)
        result = await self._session.scalar(
            select(func.count())
            .select_from(Submission)
            .where(Submission.user_id == user_id, Submission.created_at >= threshold)
        )
        return int(result or 0)

    async def count_completed_today(self) -> int:
        threshold = datetime.now(UTC) - timedelta(days=1)
        result = await self._session.scalar(
            select(func.count())
            .select_from(Submission)
            .where(
                Submission.status == SubmissionStatus.COMPLETED,
                Submission.completed_at >= threshold,
            )
        )
        return int(result or 0)

    async def latest_in_progress_for_user(self, user_id: int) -> Submission | None:
        result = await self._session.execute(
            select(Submission)
            .options(selectinload(Submission.tags), selectinload(Submission.media_files))
            .where(
                Submission.user_id == user_id,
                Submission.status.in_(IN_PROGRESS_STATUSES),
            )
            .order_by(Submission.created_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def list_recent_by_user(self, user_id: int, limit: int = 10) -> list[Submission]:
        result = await self._session.execute(
            select(Submission)
            .options(selectinload(Submission.tags))
            .where(Submission.user_id == user_id)
            .order_by(Submission.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_expired_in_progress(self, now: datetime) -> list[Submission]:
        result = await self._session.execute(
            select(Submission)
            .options(selectinload(Submission.tags), selectinload(Submission.media_files))
            .where(
                Submission.status.in_(IN_PROGRESS_STATUSES),
                Submission.expires_at.is_not(None),
                Submission.expires_at <= now,
            )
        )
        return list(result.scalars().all())

    async def list_needing_reminder(
        self, reminder_after: timedelta, now: datetime
    ) -> list[Submission]:
        threshold = now - reminder_after
        result = await self._session.execute(
            select(Submission).where(
                Submission.status.in_(IN_PROGRESS_STATUSES),
                Submission.reminded_at.is_(None),
                Submission.created_at <= threshold,
            )
        )
        return list(result.scalars().all())

    async def find_by_origin_for_user(
        self, user_id: int, chat_id: int, message_id: int
    ) -> Submission | None:
        """Match an origin group/private message to its submission."""
        recent = datetime.now(UTC) - timedelta(days=2)
        result = await self._session.execute(
            select(Submission)
            .options(selectinload(Submission.tags), selectinload(Submission.media_files))
            .where(
                Submission.user_id == user_id,
                (Submission.status.in_(IN_PROGRESS_STATUSES) | (Submission.updated_at >= recent)),
            )
            .order_by(Submission.created_at.desc())
            .limit(200)
        )
        for submission in result.scalars():
            meta = submission.meta if isinstance(submission.meta, dict) else {}
            origin = meta.get("origin_chat_id")
            raw_ids = meta.get("origin_message_ids") or []
            origin_ids = [int(item) for item in raw_ids if str(item).lstrip("-").isdigit()]
            if origin != chat_id:
                continue
            if message_id in origin_ids or submission.original_message_id == message_id:
                return submission
        return None

    async def list_terminal_private_residue(self, limit: int = 300) -> list[Submission]:
        """Decided submissions that may still have leftover private-chat messages."""
        result = await self._session.execute(
            select(Submission)
            .where(Submission.status.in_(TERMINAL_STATUSES))
            .order_by(Submission.updated_at.desc())
            .limit(limit)
        )
        found: list[Submission] = []
        for submission in result.scalars():
            meta = submission.meta if isinstance(submission.meta, dict) else {}
            if submission.wizard_message_id is not None:
                found.append(submission)
                continue
            if meta.get("subject_message_id") or meta.get("ephemeral_message_ids"):
                found.append(submission)
        return found

    async def find_duplicate_by_sha(self, sha256: str) -> Submission | None:
        result = await self._session.execute(
            select(Submission)
            .join(MediaFile, MediaFile.submission_id == Submission.id)
            .where(
                MediaFile.sha256 == sha256,
                Submission.status == SubmissionStatus.COMPLETED,
            )
            .order_by(Submission.completed_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def paginate_by_tag(
        self, tag_id: int, page: int, per_page: int = 10
    ) -> tuple[list[Submission], int]:
        total = int(
            await self._session.scalar(
                select(func.count())
                .select_from(SubmissionTag)
                .join(Submission, Submission.id == SubmissionTag.submission_id)
                .where(
                    SubmissionTag.tag_id == tag_id,
                    Submission.status == SubmissionStatus.COMPLETED,
                )
            )
            or 0
        )
        result = await self._session.execute(
            select(Submission)
            .options(selectinload(Submission.tags))
            .join(SubmissionTag, SubmissionTag.submission_id == Submission.id)
            .where(
                SubmissionTag.tag_id == tag_id,
                Submission.status == SubmissionStatus.COMPLETED,
            )
            .order_by(Submission.completed_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(result.scalars().all()), total
