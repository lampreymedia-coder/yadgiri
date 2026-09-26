"""Disk usage report for archived media (admin /disk)."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MediaFile, StorageStatus


@dataclass(slots=True, frozen=True)
class LargestMediaRow:
    media_id: int
    size_bytes: int
    storage_key: str | None
    file_name: str | None
    is_compressed: bool
    status: str


@dataclass(slots=True, frozen=True)
class DiskReport:
    free_bytes: int
    total_disk_bytes: int
    media_root: str
    stored_bytes: int
    compression_saved_bytes: int
    dedup_saved_bytes: int
    stored_count: int
    duplicate_count: int
    compressed_count: int
    largest: list[LargestMediaRow]


async def build_disk_report(session: AsyncSession, media_root: Path) -> DiskReport:
    root = media_root.resolve() if media_root.exists() else media_root
    try:
        usage = shutil.disk_usage(str(root if root.exists() else root.parent))
        free_bytes = int(usage.free)
        total_disk_bytes = int(usage.total)
    except OSError:
        free_bytes = 0
        total_disk_bytes = 0

    stored_bytes = int(
        await session.scalar(
            select(func.coalesce(func.sum(MediaFile.stored_size_bytes), 0)).where(
                MediaFile.storage_status == StorageStatus.STORED
            )
        )
        or 0
    )
    compression_saved = int(
        await session.scalar(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (
                                MediaFile.is_compressed == True,  # noqa: E712
                                MediaFile.original_size_bytes - MediaFile.stored_size_bytes,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                )
            ).where(MediaFile.storage_status == StorageStatus.STORED)
        )
        or 0
    )
    # Dedup savings: bytes we would have written again for DUPLICATE rows.
    dedup_saved = int(
        await session.scalar(
            select(func.coalesce(func.sum(MediaFile.original_size_bytes), 0)).where(
                MediaFile.storage_status == StorageStatus.DUPLICATE
            )
        )
        or 0
    )
    stored_count = int(
        await session.scalar(
            select(func.count()).select_from(MediaFile).where(
                MediaFile.storage_status == StorageStatus.STORED
            )
        )
        or 0
    )
    duplicate_count = int(
        await session.scalar(
            select(func.count()).select_from(MediaFile).where(
                MediaFile.storage_status == StorageStatus.DUPLICATE
            )
        )
        or 0
    )
    compressed_count = int(
        await session.scalar(
            select(func.count())
            .select_from(MediaFile)
            .where(
                MediaFile.storage_status == StorageStatus.STORED,
                MediaFile.is_compressed == True,  # noqa: E712
            )
        )
        or 0
    )

    largest_rows = (
        await session.execute(
            select(MediaFile)
            .where(
                MediaFile.storage_status.in_([StorageStatus.STORED, StorageStatus.DUPLICATE]),
                MediaFile.stored_size_bytes.is_not(None),
            )
            .order_by(MediaFile.stored_size_bytes.desc())
            .limit(5)
        )
    ).scalars().all()

    # For duplicates stored_size may be 0 — rank by original_size instead for top list.
    if len(largest_rows) < 5:
        largest_rows = (
            await session.execute(
                select(MediaFile)
                .where(
                    MediaFile.storage_status.in_(
                        [StorageStatus.STORED, StorageStatus.DUPLICATE]
                    ),
                    MediaFile.original_size_bytes.is_not(None),
                )
                .order_by(
                    func.coalesce(MediaFile.stored_size_bytes, MediaFile.original_size_bytes).desc()
                )
                .limit(5)
            )
        ).scalars().all()

    largest = [
        LargestMediaRow(
            media_id=row.id,
            size_bytes=int(
                row.stored_size_bytes
                or row.original_size_bytes
                or row.file_size_bytes
                or 0
            ),
            storage_key=row.storage_key,
            file_name=row.file_name,
            is_compressed=bool(row.is_compressed),
            status=row.storage_status.value
            if hasattr(row.storage_status, "value")
            else str(row.storage_status),
        )
        for row in largest_rows
    ]

    return DiskReport(
        free_bytes=free_bytes,
        total_disk_bytes=total_disk_bytes,
        media_root=str(root),
        stored_bytes=max(stored_bytes, 0),
        compression_saved_bytes=max(compression_saved, 0),
        dedup_saved_bytes=max(dedup_saved, 0),
        stored_count=stored_count,
        duplicate_count=duplicate_count,
        compressed_count=compressed_count,
        largest=largest,
    )
