"""Write one row into the owner's existing POST table.

The INSERT text and column order are the query writer's contract. Bot
field names are mapped here; POST column names are not renamed.

IMPORTANT: this feature is incomplete. It only works when table POST lives
in the **same** database as DATABASE_URL (``bale_archive``). It must never
run inside the archive transaction — use
``insert_owner_post_separate_transaction`` so a POST failure cannot roll
back a completed submission.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.models import MediaFile, Submission
from app.observability.logging import get_logger

logger = get_logger(__name__)

# Exact column order from the query writer. :name is the same as @name.
INSERT_POST_SQL = text("""
INSERT INTO POST
(
    post_id,
    media_type,
    bale_file_id,
    file_name,
    file_size,
    mime_type,
    storage_path,
    duration,
    width,
    height,
    created_at
)
VALUES
(
    :post_id,
    :media_type,
    :bale_file_id,
    :file_name,
    :file_size,
    :mime_type,
    :storage_path,
    :duration,
    :width,
    :height,
    GETDATE()
)
""")


def owner_post_values(submission: Submission, media: MediaFile | None) -> dict[str, Any]:
    """Map one completed bot submission onto the owner's POST columns."""
    content_type = submission.content_type
    media_type = content_type.value if hasattr(content_type, "value") else str(content_type)
    return {
        "post_id": submission.id,
        "media_type": media_type,
        "bale_file_id": None if media is None else media.bale_file_id,
        "file_name": None if media is None else media.file_name,
        "file_size": None if media is None else media.file_size_bytes,
        "mime_type": None if media is None else media.mime_type,
        "storage_path": None if media is None else media.storage_key,
        "duration": None if media is None else media.duration_seconds,
        "width": None if media is None else media.width,
        "height": None if media is None else media.height,
    }


async def _first_media(session: AsyncSession, submission: Submission) -> MediaFile | None:
    loaded = submission.__dict__.get("media_files")
    files = [item for item in loaded or [] if isinstance(item, MediaFile)]
    if files:
        return min(files, key=lambda item: item.position)
    result = await session.execute(
        select(MediaFile)
        .where(MediaFile.submission_id == submission.id)
        .order_by(MediaFile.position, MediaFile.id)
        .limit(1)
    )
    return result.scalars().first()


async def insert_owner_post(session: AsyncSession, submission: Submission) -> None:
    """Insert the owner's POST row on the given session (one submission → one row).

    Prefer ``insert_owner_post_separate_transaction`` from production paths so
    archive commits stay isolated from POST failures.
    """
    media = await _first_media(session, submission)
    values = owner_post_values(submission, media)
    await session.execute(INSERT_POST_SQL, values)
    logger.info(
        "owner_post_inserted",
        post_id=values["post_id"],
        media_type=values["media_type"],
        has_file=media is not None,
    )


async def insert_owner_post_separate_transaction(
    bind: AsyncEngine | Engine,
    read_session: AsyncSession,
    submission: Submission,
) -> None:
    """Insert POST in its own transaction on ``bind``.

    Reads media mapping via ``read_session`` (the archive session) but never
    writes through it. Callers must catch failures — this function re-raises.
    """
    media = await _first_media(read_session, submission)
    values = owner_post_values(submission, media)
    factory = async_sessionmaker(bind, expire_on_commit=False, class_=AsyncSession)
    async with factory() as post_session:
        async with post_session.begin():
            await post_session.execute(INSERT_POST_SQL, values)
    logger.info(
        "owner_post_inserted",
        post_id=values["post_id"],
        media_type=values["media_type"],
        has_file=media is not None,
    )
