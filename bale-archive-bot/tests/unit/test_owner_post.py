"""Owner POST insert: column map, isolation from archive commits."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.bale.methods import BaleAPI
from app.config import Settings
from app.db.base import Base
from app.db.models import ContentType, MediaFile, OutboxItem, Submission, SubmissionStatus, User
from app.db.owner_post import INSERT_POST_SQL, owner_post_values
from app.domain.submission import SubmissionService
from app.i18n import fa


def test_insert_sql_uses_query_writer_column_order() -> None:
    sql = str(INSERT_POST_SQL)
    assert sql.index("post_id") < sql.index("media_type") < sql.index("bale_file_id")
    assert sql.index("file_name") < sql.index("file_size") < sql.index("mime_type")
    assert sql.index("storage_path") < sql.index("duration") < sql.index("width")
    assert sql.index("width") < sql.index("height") < sql.index("created_at")
    assert "GETDATE()" in sql
    assert "INSERT INTO POST" in sql


def test_owner_post_values_map_bot_fields_without_renaming_columns() -> None:
    submission = Submission(id=41, content_type=ContentType.DOCUMENT)
    media = MediaFile(
        submission_id=41,
        position=0,
        bale_file_id="AgAD123",
        file_name="report.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        file_size_bytes=18506,
        duration_seconds=None,
        width=None,
        height=None,
        storage_key=r"data\media\41\file.xlsx",
    )
    values = owner_post_values(submission, media)
    assert values == {
        "post_id": 41,
        "media_type": "document",
        "bale_file_id": "AgAD123",
        "file_name": "report.xlsx",
        "file_size": 18506,
        "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "storage_path": r"data\media\41\file.xlsx",
        "duration": None,
        "width": None,
        "height": None,
    }


def test_text_post_sends_null_file_columns() -> None:
    submission = Submission(id=7, content_type=ContentType.TEXT)
    values = owner_post_values(submission, None)
    assert values["post_id"] == 7
    assert values["media_type"] == "text"
    assert values["bale_file_id"] is None
    assert values["storage_path"] is None


def test_admin_owner_post_sync_failed_message_is_persian() -> None:
    text_msg = fa.admin_owner_post_sync_failed("ab12cd")
    assert "POST" in text_msg
    assert "ab12cd" in text_msg
    assert "سالم" in text_msg


@pytest.mark.asyncio
async def test_owner_post_failure_does_not_rollback_completed_archive() -> None:
    """POST insert failure must leave the completed submission committed.

    No POST table exists → separate-transaction INSERT fails → archive stays
    COMPLETED and an admin_notify outbox row is queued.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    settings = Settings(
        _env_file=None,
        BALE_BOT_TOKEN="test-token",
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        ADMIN_CHAT_ID=-600,
        OWNER_POST_SYNC=True,
    )
    api = AsyncMock(spec=BaleAPI)

    async with factory() as session, session.begin():
        user = User(bale_user_id=42, first_name="فاطمه", locale="fa")
        session.add(user)
        await session.flush()
        submission = Submission(
            short_id="ab12cd",
            user_id=user.id,
            status=SubmissionStatus.DRAFT,
            content_type=ContentType.TEXT,
            text_content="سلام",
        )
        session.add(submission)
        await session.flush()

        submission.status = SubmissionStatus.COMPLETED
        service = SubmissionService(session, api, settings, admin_chat_id=-600)
        await service.sync_owner_post(submission)

        assert submission.status is SubmissionStatus.COMPLETED
        notify = (
            await session.execute(select(OutboxItem).where(OutboxItem.kind == "admin_notify"))
        ).scalars().all()
        assert len(notify) == 1
        assert notify[0].target_chat_id == -600
        assert "ab12cd" in str(notify[0].payload.get("text", ""))

    # After the archive transaction commits, the row is still COMPLETED.
    async with factory() as session:
        loaded = (
            await session.execute(select(Submission).where(Submission.short_id == "ab12cd"))
        ).scalar_one()
        assert loaded.status is SubmissionStatus.COMPLETED

    # POST was never created — failure path really hit a missing table.
    async with engine.connect() as conn:
        exists = await conn.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='POST'")
        )
        assert exists.scalar() is None

    await engine.dispose()
