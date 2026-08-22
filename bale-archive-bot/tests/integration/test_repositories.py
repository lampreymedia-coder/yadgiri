"""Repository tests against the in-memory database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.idempotency import claim_update
from app.db.models import ContentType, StorageStatus, SubmissionStatus
from app.db.repositories.misc import MediaRepository, ProcessedUpdateRepository
from app.db.repositories.outbox import OutboxRepository
from app.db.repositories.submissions import SubmissionRepository
from app.db.repositories.tags import TagRepository
from app.db.repositories.users import UserRepository
from app.db.session import Database


async def test_idempotency_claim(db: Database) -> None:
    async with db.session() as session:
        assert await claim_update(session, 42) is True
    async with db.session() as session:
        assert await claim_update(session, 42) is False
    async with db.session() as session:
        repo = ProcessedUpdateRepository(session)
        assert await repo.last_update_id() == 42


async def test_submission_lifecycle(seeded_db: Database) -> None:
    async with seeded_db.session() as session:
        users = UserRepository(session)
        user = await users.upsert_from_bale(12345, "ali", "علی", "احمدی")
        subs = SubmissionRepository(session)
        submission = await subs.create_draft(
            user_id=user.id,
            group_id=None,
            content_type=ContentType.TEXT,
            content_subtype=None,
            text_content="متن",
            text_normalized="متن",
            caption=None,
            urls=[],
            is_forwarded=False,
            forward_source=None,
            original_message_id=10,
            raw_update=None,
            ttl_minutes=30,
        )
        short_id = submission.short_id
        assert len(short_id) == 6
        from app.i18n.fa import SEED_TAGS

        tags = TagRepository(session)
        active = await tags.list_active()
        assert len(active) == len(SEED_TAGS)
        await subs.set_tags(submission, [active[0].id, active[2].id])
        await subs.set_status(submission, SubmissionStatus.COMPLETED)

    async with seeded_db.session() as session:
        subs = SubmissionRepository(session)
        loaded = await subs.get_by_short_id(short_id)
        assert loaded is not None
        assert loaded.status is SubmissionStatus.COMPLETED
        assert {t.slug for t in loaded.tags} == {"learning", "content"}
        assert loaded.completed_at is not None


async def test_user_display_name_and_forget(db: Database) -> None:
    async with db.session() as session:
        users = UserRepository(session)
        user = await users.upsert_from_bale(1, "u", "علی", "احمدی")
        assert user.display_name == "علی احمدی"
        await users.forget(user.id)
    async with db.session() as session:
        users = UserRepository(session)
        reloaded = await users.get_by_bale_id(1)
        assert reloaded is not None
        assert reloaded.first_name is None
        assert reloaded.is_blocked is True


async def test_outbox_retry_and_permanent_failure(db: Database) -> None:
    async with db.session() as session:
        outbox = OutboxRepository(session)
        item = await outbox.enqueue("admin_notify", -600, {"text": "سلام"})
        item_id = item.id
        assert await outbox.pending_count() == 1

    async with db.session() as session:
        outbox = OutboxRepository(session)
        due = await outbox.due_items()
        assert [i.id for i in due] == [item_id]
        await outbox.mark_retry(item_id, "err", attempts=1, max_attempts=10)

    async with db.session() as session:
        outbox = OutboxRepository(session)
        # Backoff pushed next_retry_at into the future — not due any more.
        assert await outbox.due_items() == []
        await outbox.mark_retry(item_id, "fatal", attempts=10, max_attempts=10)
        assert await outbox.pending_count() == 0


async def test_media_backlog_and_dedup(seeded_db: Database) -> None:
    async with seeded_db.session() as session:
        users = UserRepository(session)
        user = await users.upsert_from_bale(2, None, "x", None)
        subs = SubmissionRepository(session)
        submission = await subs.create_draft(
            user_id=user.id,
            group_id=None,
            content_type=ContentType.DOCUMENT,
            content_subtype="pdf",
            text_content=None,
            text_normalized=None,
            caption=None,
            urls=[],
            is_forwarded=False,
            forward_source=None,
            original_message_id=None,
            raw_update=None,
            ttl_minutes=30,
        )
        media = await subs.add_media(submission, "file-1", file_size_bytes=100)
        media_id = media.id

    async with seeded_db.session() as session:
        repo = MediaRepository(session)
        backlog = await repo.backlog()
        assert [m.id for m in backlog] == [media_id]
        await repo.update_status(
            media_id, StorageStatus.STORED, sha256="abc", storage_key="media/x"
        )

    async with seeded_db.session() as session:
        repo = MediaRepository(session)
        assert await repo.backlog() == []
        found = await repo.find_by_sha("abc")
        assert found is not None and found.id == media_id


async def test_expired_and_reminder_queries(seeded_db: Database) -> None:
    async with seeded_db.session() as session:
        users = UserRepository(session)
        user = await users.upsert_from_bale(3, None, "y", None)
        subs = SubmissionRepository(session)
        submission = await subs.create_draft(
            user_id=user.id,
            group_id=None,
            content_type=ContentType.TEXT,
            content_subtype=None,
            text_content="x",
            text_normalized="x",
            caption=None,
            urls=[],
            is_forwarded=False,
            forward_source=None,
            original_message_id=None,
            raw_update=None,
            ttl_minutes=30,
        )
        # Force it into the past.
        submission.created_at = datetime.now(UTC) - timedelta(minutes=45)
        submission.expires_at = datetime.now(UTC) - timedelta(minutes=15)

    async with seeded_db.session() as session:
        subs = SubmissionRepository(session)
        needing = await subs.list_needing_reminder(timedelta(minutes=10), datetime.now(UTC))
        assert len(needing) == 1
        expired = await subs.list_expired_in_progress(datetime.now(UTC))
        assert len(expired) == 1
