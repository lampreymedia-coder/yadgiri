"""2-6 and section 3 item 6: ffmpeg is mocked; only PostMedia.storage_path/file_size change."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest

from app.domain import video_compress
from tests.bot.harness import GROUP, MB, USER, Harness
from tests.conftest import EXECUTED_SQL


def fake_ffmpeg(output: bytes | None, calls: list[Path] | None = None):  # type: ignore[no-untyped-def]
    async def run(src: Path, dst: Path) -> None:
        if calls is not None:
            calls.append(src)
        if output is None:
            raise RuntimeError("ffmpeg exit 1: broken")
        dst.write_bytes(output)

    return run


@pytest.fixture
def ffmpeg_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(video_compress, "ffmpeg_available", lambda: True)


async def _save_video(h: Harness, size: int = 100) -> None:
    h.register_group()
    await h.send(GROUP, USER, video={"file_id": "vid", "file_size": size, "mime_type": "video/mp4"})
    await h.confirm([1])
    await h.settle()


def _media_updates(since: int) -> list[str]:
    return [s for s in EXECUTED_SQL[since:] if re.match(r"\s*UPDATE\s+PostMedia", s, re.I)]


async def test_good_savings_replace_file_and_update_only_existing_columns(
    h: Harness, monkeypatch: pytest.MonkeyPatch, ffmpeg_present: None
) -> None:
    monkeypatch.setattr(video_compress, "run_ffmpeg", fake_ffmpeg(b"small"))  # 15 → 5 bytes
    start = len(EXECUTED_SQL)
    await _save_video(h)
    (path, size, mtype), = h.root.rows("SELECT storage_path, file_size, media_type FROM PostMedia")
    assert mtype == 2 and size == 5 and path.endswith(".mp4")
    assert Path(path).read_bytes() == b"small"
    updates = _media_updates(start)
    assert updates == ["UPDATE PostMedia SET storage_path = %s, file_size = %s WHERE id = %s"]
    log = json.loads((h.settings.data_path / "compression.json").read_text())
    (entry,) = log.values()
    assert entry["original_size"] == 15 and entry["new_size"] == 5 and entry["replaced"] is True


async def test_small_savings_keep_the_original(
    h: Harness, monkeypatch: pytest.MonkeyPatch, ffmpeg_present: None
) -> None:
    monkeypatch.setattr(video_compress, "run_ffmpeg", fake_ffmpeg(b"x" * 14))  # 6.7 %
    start = len(EXECUTED_SQL)
    await _save_video(h)
    (path, size), = h.root.rows("SELECT storage_path, file_size FROM PostMedia")
    assert size == 100  # unchanged (value reported by Bale)
    assert Path(path).read_bytes() == b"fake-file-bytes"
    assert _media_updates(start) == []
    assert list(Path(path).parent.glob("*.c.mp4")) == []


async def test_ffmpeg_error_keeps_the_original(
    h: Harness, monkeypatch: pytest.MonkeyPatch, ffmpeg_present: None
) -> None:
    monkeypatch.setattr(video_compress, "run_ffmpeg", fake_ffmpeg(None))
    await _save_video(h)
    (path,), = h.root.rows("SELECT storage_path FROM PostMedia")
    assert Path(path).read_bytes() == b"fake-file-bytes"
    assert h.count("Post") == 1


async def test_missing_ffmpeg_skips(h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Path] = []
    monkeypatch.setattr(video_compress, "ffmpeg_available", lambda: False)
    monkeypatch.setattr(video_compress, "run_ffmpeg", fake_ffmpeg(b"s", calls))
    await _save_video(h)
    assert calls == []


async def test_big_video_is_not_compressed(
    h: Harness, monkeypatch: pytest.MonkeyPatch, ffmpeg_present: None
) -> None:
    calls: list[Path] = []
    monkeypatch.setattr(video_compress, "run_ffmpeg", fake_ffmpeg(b"s", calls))
    await _save_video(h, size=50 * MB)
    (path,), = h.root.rows("SELECT storage_path FROM PostMedia")
    assert path.startswith("bale:") and calls == []


async def test_only_one_ffmpeg_at_a_time(
    h: Harness, monkeypatch: pytest.MonkeyPatch, ffmpeg_present: None, tmp_path: Path
) -> None:
    from app.domain.media_store import compress_stored_video

    running = 0
    peak = 0

    async def slow(src: Path, dst: Path) -> None:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.05)
        dst.write_bytes(b"s")
        running -= 1

    monkeypatch.setattr(video_compress, "run_ffmpeg", slow)
    files = []
    for index in range(3):
        path = tmp_path / f"v{index}.mp4"
        path.write_bytes(b"0123456789")
        files.append(path)
    await asyncio.gather(*(compress_stored_video(h.ctx, 900 + i, p) for i, p in enumerate(files)))
    assert peak == 1


def test_ffmpeg_settings() -> None:
    command = " ".join(video_compress.ffmpeg_command(Path("in"), Path("out.mp4")))
    for part in ("-c:v libx264", "-crf 24", "-preset veryfast", "min(720,ih)", "-c:a aac", "-b:a 96k"):
        assert part in command
    assert command.startswith("nice -n 19 ffmpeg")
