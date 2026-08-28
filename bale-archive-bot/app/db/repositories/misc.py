"""Small repositories: idempotency, audit log, runtime settings, media backlog."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import AppSetting, AuditLog, MediaFile, ProcessedUpdate, StorageStatus


class ProcessedUpdateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def try_mark(self, update_id: int) -> bool:
        """INSERT ... ON CONFLICT DO NOTHING; False means already processed."""
        if self._session.bind is not None and self._session.bind.dialect.name == "postgresql":
            stmt = (
                pg_insert(ProcessedUpdate)
                .values(update_id=update_id)
                .on_conflict_do_nothing(index_elements=["update_id"])
            )
            result = await self._session.execute(stmt)
            return bool(getattr(result, "rowcount", 0))
        # Non-Postgres fallback: a savepoint absorbs the duplicate-key race.
        try:
            async with self._session.begin_nested():
                self._session.add(ProcessedUpdate(update_id=update_id))
                await self._session.flush()
        except IntegrityError:
            return False
        return True

    async def purge_older_than(self, days: int = 7) -> int:
        threshold = datetime.now(UTC) - timedelta(days=days)
        result = await self._session.execute(
            delete(ProcessedUpdate).where(ProcessedUpdate.processed_at < threshold)
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def last_update_id(self) -> int | None:
        result = await self._session.scalar(select(func.max(ProcessedUpdate.update_id)))
        return int(result) if result is not None else None


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        action: str,
        actor_user_id: int | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._session.add(
            AuditLog(
                action=action,
                actor_user_id=actor_user_id,
                entity_type=entity_type,
                entity_id=entity_id,
                payload=payload or {},
            )
        )


class AppSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key: str, default: Any = None) -> Any:
        setting = await self._session.get(AppSetting, key)
        return setting.value if setting is not None else default

    async def set(self, key: str, value: Any, updated_by: int | None = None) -> None:
        setting = await self._session.get(AppSetting, key)
        if setting is None:
            self._session.add(AppSetting(key=key, value=value, updated_by=updated_by))
        else:
            setting.value = value
            setting.updated_by = updated_by

    async def all(self) -> dict[str, Any]:
        result = await self._session.execute(select(AppSetting))
        return {row.key: row.value for row in result.scalars().all()}


class MediaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def backlog(self, limit: int = 10) -> list[MediaFile]:
        result = await self._session.execute(
            select(MediaFile)
            .options(selectinload(MediaFile.submission))
            .where(MediaFile.storage_status.in_([StorageStatus.PENDING, StorageStatus.FAILED]))
            .where(MediaFile.storage_attempts < 5)
            .order_by(MediaFile.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def backlog_count(self) -> int:
        result = await self._session.scalar(
            select(func.count())
            .select_from(MediaFile)
            .where(MediaFile.storage_status.in_([StorageStatus.PENDING, StorageStatus.FAILED]))
        )
        return int(result or 0)

    async def find_by_sha(self, sha256: str) -> MediaFile | None:
        result = await self._session.execute(
            select(MediaFile)
            .where(MediaFile.sha256 == sha256, MediaFile.storage_status == StorageStatus.STORED)
            .limit(1)
        )
        return result.scalars().first()

    async def update_status(
        self,
        media_id: int,
        status: StorageStatus,
        sha256: str | None = None,
        storage_bucket: str | None = None,
        storage_key: str | None = None,
        error: str | None = None,
        increment_attempts: bool = True,
    ) -> None:
        values: dict[str, Any] = {"storage_status": status}
        if sha256 is not None:
            values["sha256"] = sha256
        if storage_bucket is not None:
            values["storage_bucket"] = storage_bucket
        if storage_key is not None:
            values["storage_key"] = storage_key
        if error is not None:
            values["last_error"] = error[:2000]
        if status is StorageStatus.STORED:
            values["stored_at"] = datetime.now(UTC)
        if increment_attempts:
            values["storage_attempts"] = MediaFile.storage_attempts + 1
        await self._session.execute(
            update(MediaFile).where(MediaFile.id == media_id).values(**values)
        )
