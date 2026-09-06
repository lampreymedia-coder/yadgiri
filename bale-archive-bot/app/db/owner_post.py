"""Write one row into the owner's existing POST table.

The INSERT text and column order are the query writer's contract. Bot
field names are mapped here; POST column names are not renamed.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

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
    """Insert the owner's POST row. One submission → one POST row."""
    media = await _first_media(session, submission)
    values = owner_post_values(submission, media)
    await session.execute(INSERT_POST_SQL, values)
    logger.info(
        "owner_post_inserted",
        post_id=values["post_id"],
        media_type=values["media_type"],
        has_file=media is not None,
    )
