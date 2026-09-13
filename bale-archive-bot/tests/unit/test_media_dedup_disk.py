"""Media worker dedup-before-write and /disk reporting."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.bale.capabilities import Capabilities
from app.config import Settings
from app.core.context import BotContext
from app.core.dispatcher import Dispatcher
from app.db.base import Base
from app.db.models import ContentType, MediaFile, StorageStatus, Submission, SubmissionStatus
from app.db.repositories.misc import MediaRepository
from app.db.repositories.users import UserRepository
from app.db.session import Database
from app.domain.disk_report import build_disk_report
from app.domain.media import LocalStorage, MediaProcessResult
from app.i18n import fa
from app.workers import media_worker
from tests.e2e.test_commands import _private
from tests.e2e.test_wizard_flow import USER_ID
from tests.fakes.fake_bale import FakeBaleServer


@pytest.mark.asyncio
async def test_worker_dedup_skips_storage_put(tmp_path: Path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    store = LocalStorage(tmp_path)
    put_calls: list[str] = []
    real_put = store.put

    async def tracking_put(key: str, data: bytes, content_type: str) -> str:
        put_calls.append(key)
        return await real_put(key, data, content_type)

    store.put = tracking_put  # type: ignore[method-assign]

    payload = b"identical-video-bytes-12345"
    import hashlib

    sha = hashlib.sha256(payload).hexdigest()

    async with factory() as session, session.begin():
        user = await UserRepository(session).upsert_from_bale(1, None, "a", None)
        submission = Submission(
            short_id="abc123",
            user_id=user.id,
            status=SubmissionStatus.DRAFT,
            content_type=ContentType.VIDEO,
        )
        session.add(submission)
        await session.flush()
        stored_path = await store.put("aa/first.mp4", payload, "video/mp4")
        put_calls.clear()
        first = MediaFile(
            submission_id=submission.id,
            bale_file_id="f-first",
            mime_type="video/mp4",
            file_name="a.mp4",
            storage_status=StorageStatus.STORED,
            sha256=sha,
            storage_key=stored_path,
            original_size_bytes=len(payload),
            stored_size_bytes=len(payload),
            is_compressed=False,
        )
        second = MediaFile(
            submission_id=submission.id,
            bale_file_id="f-second",
            mime_type="video/mp4",
            file_name="b.mp4",
            storage_status=StorageStatus.PENDING,
        )
        session.add_all([first, second])
        await session.flush()
        second_id = second.id

    settings = Settings(
        _env_file=None,
        BALE_BOT_TOKEN="test-token",
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        MEDIA_DOWNLOAD_ENABLED=True,
        VIDEO_COMPRESSION_ENABLED=False,
        ADMIN_USER_IDS=[USER_ID],
    )

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _session_cm():
        async with factory() as session:
            async with session.begin():
                yield session

    class _DB:
        def session(self):  # noqa: ANN201
            return _session_cm()

    caps = Capabilities()
    caps.probed = True
    ctx = BotContext(
        settings=settings, api=MagicMock(), db=_DB(), caps=caps  # type: ignore[arg-type]
    )

    async def fake_prepare(*_a: object, **_k: object) -> MediaProcessResult:
        return MediaProcessResult(
            status=StorageStatus.STORED,
            sha256=sha,
            original_size_bytes=len(payload),
            stored_size_bytes=len(payload),
            is_compressed=False,
            payload=payload,
        )

    with patch.object(media_worker, "prepare_media_bytes", side_effect=fake_prepare):
        handled = await media_worker.run_media_once(ctx, store)

    assert handled == 1
    assert put_calls == [], "duplicate must not call Storage.put"

    async with factory() as session:
        second = await session.get(MediaFile, second_id)
        assert second is not None
        assert second.storage_status is StorageStatus.DUPLICATE
        assert second.sha256 == sha
        assert second.stored_size_bytes == 0
        assert second.original_size_bytes == len(payload)
        assert second.storage_key == stored_path

    await engine.dispose()


@pytest.mark.asyncio
async def test_disk_report_counts_savings(tmp_path: Path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with factory() as session, session.begin():
        user = await UserRepository(session).upsert_from_bale(9, None, "u", None)
        submission = Submission(
            short_id="disk01",
            user_id=user.id,
            status=SubmissionStatus.COMPLETED,
            content_type=ContentType.VIDEO,
        )
        session.add(submission)
        await session.flush()
        session.add_all(
            [
                MediaFile(
                    submission_id=submission.id,
                    bale_file_id="a",
                    storage_status=StorageStatus.STORED,
                    original_size_bytes=10_000,
                    stored_size_bytes=4_000,
                    is_compressed=True,
                    storage_key="aa/a.mp4",
                    file_name="a.mp4",
                    sha256="a" * 64,
                ),
                MediaFile(
                    submission_id=submission.id,
                    bale_file_id="b",
                    storage_status=StorageStatus.DUPLICATE,
                    original_size_bytes=10_000,
                    stored_size_bytes=0,
                    is_compressed=False,
                    storage_key="aa/a.mp4",
                    sha256="a" * 64,
                ),
            ]
        )

    async with factory() as session:
        report = await build_disk_report(session, tmp_path)
    assert report.stored_bytes == 4_000
    assert report.compression_saved_bytes == 6_000
    assert report.dedup_saved_bytes == 10_000
    assert report.compressed_count == 1
    assert report.duplicate_count == 1
    assert report.largest

    await engine.dispose()


def test_format_bytes_persian() -> None:
    text = fa.format_bytes(2048)
    assert "KB" in text


async def test_disk_command_sends_report(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    ctx.runtime_admin_ids = {USER_ID}
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(_private("/disk"))
    body = "\n".join(fake_bale.sent_texts(USER_ID))
    assert fa.DISK_HEADER in body
