"""Video compression safety and media dedup-before-write."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.models import MediaFile, StorageStatus
from app.domain.media import (
    LocalStorage,
    VideoCompressionSettings,
    prepare_media_bytes,
    storage_key_for,
)
from app.domain.video_compress import (
    VideoCompressResult,
    compress_video,
    ffmpeg_available,
    is_video_media,
)


def test_is_video_media_detects_mime_and_extension() -> None:
    assert is_video_media(mime_type="video/mp4", file_name=None) is True
    assert is_video_media(mime_type="image/jpeg", file_name="x.mp4") is True
    assert is_video_media(mime_type="image/jpeg", file_name="x.jpg") is False


@pytest.mark.asyncio
async def test_compress_keeps_original_when_ffmpeg_missing() -> None:
    original = b"fake-video-bytes-" + (b"x" * 1000)
    with patch("app.domain.video_compress.ffmpeg_available", return_value=False):
        result = await compress_video(original, crf=24, max_height=720)
    assert result.used_compressed is False
    assert result.data is original
    assert result.reason == "ffmpeg_missing"


@pytest.mark.asyncio
async def test_compress_keeps_original_on_ffmpeg_error() -> None:
    original = b"fake-video-bytes-" + (b"y" * 2000)

    def _boom(*_a: object, **_k: object) -> bytes:
        raise RuntimeError("encoder failed")

    with (
        patch("app.domain.video_compress.ffmpeg_available", return_value=True),
        patch("app.domain.video_compress._run_ffmpeg_sync", side_effect=_boom),
    ):
        result = await compress_video(original)
    assert result.used_compressed is False
    assert result.data == original
    assert result.reason.startswith("error:")


@pytest.mark.asyncio
async def test_compress_rejects_when_not_enough_savings() -> None:
    original = b"o" * 10_000
    # Only 5% smaller → must keep original and discard compressed.
    tiny_gain = original[:9500]

    with (
        patch("app.domain.video_compress.ffmpeg_available", return_value=True),
        patch("app.domain.video_compress._run_ffmpeg_sync", return_value=tiny_gain),
    ):
        result = await compress_video(original)
    assert result.used_compressed is False
    assert result.data == original
    assert result.reason == "savings_below_15pct"


@pytest.mark.asyncio
async def test_compress_rejects_when_larger_than_original() -> None:
    original = b"o" * 1000
    larger = b"z" * 1500
    with (
        patch("app.domain.video_compress.ffmpeg_available", return_value=True),
        patch("app.domain.video_compress._run_ffmpeg_sync", return_value=larger),
    ):
        result = await compress_video(original)
    assert result.used_compressed is False
    assert result.data == original
    assert result.reason == "larger_or_equal"


@pytest.mark.asyncio
async def test_compress_accepts_worthwhile_result() -> None:
    original = b"o" * 10_000
    smaller = b"c" * 5_000
    with (
        patch("app.domain.video_compress.ffmpeg_available", return_value=True),
        patch("app.domain.video_compress._run_ffmpeg_sync", return_value=smaller),
    ):
        result = await compress_video(original)
    assert result.used_compressed is True
    assert result.data == smaller
    assert result.reason == "ok"


@pytest.mark.asyncio
async def test_prepare_media_applies_compression_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media = MediaFile(
        id=1,
        submission_id=1,
        bale_file_id="f1",
        mime_type="video/mp4",
        file_name="clip.mp4",
    )
    raw = b"V" * 8_000

    class _Info:
        file_size = len(raw)
        file_path = "files/x"

    api = MagicMock()
    api.get_file = AsyncMock(return_value=_Info())
    api.client.download_file = AsyncMock(return_value=raw)

    async def _fake_compress(data: bytes, **_kwargs: object) -> VideoCompressResult:
        return VideoCompressResult(True, b"C" * 3_000, "ok")

    monkeypatch.setattr("app.domain.media.compress_video", _fake_compress)
    prepared = await prepare_media_bytes(
        api,
        media,
        max_download_bytes=20_000_000,
        compression=VideoCompressionSettings(enabled=True),
    )
    assert prepared.status is StorageStatus.STORED
    assert prepared.is_compressed is True
    assert prepared.original_size_bytes == 8_000
    assert prepared.stored_size_bytes == 3_000
    assert prepared.payload == b"C" * 3_000
    assert prepared.sha256 is not None


@pytest.mark.asyncio
async def test_prepare_keeps_original_payload_when_compress_disabled() -> None:
    media = MediaFile(
        id=2,
        submission_id=1,
        bale_file_id="f2",
        mime_type="video/mp4",
        file_name="clip.mp4",
    )
    raw = b"V" * 4_000

    class _Info:
        file_size = len(raw)
        file_path = "files/y"

    api = MagicMock()
    api.get_file = AsyncMock(return_value=_Info())
    api.client.download_file = AsyncMock(return_value=raw)

    with patch("app.domain.media.compress_video") as mocked:
        prepared = await prepare_media_bytes(
            api,
            media,
            max_download_bytes=20_000_000,
            compression=VideoCompressionSettings(enabled=False),
        )
        mocked.assert_not_called()
    assert prepared.is_compressed is False
    assert prepared.payload == raw


@pytest.mark.asyncio
async def test_local_storage_delete(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path)
    path = await store.put("aa/test.bin", b"hello", "application/octet-stream")
    assert Path(path).is_file()
    await store.delete("aa/test.bin")
    assert not Path(path).exists()


def test_ffmpeg_available_is_bool() -> None:
    assert isinstance(ffmpeg_available(), bool)


def test_storage_key_still_short() -> None:
    media = MediaFile(submission_id=1, bale_file_id="f1", file_name="a.mp4")
    assert storage_key_for(media).endswith(".mp4")
