"""Video/audio compression: decisions with mocked ffmpeg, plus real ffmpeg checks."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.domain import video_compress
from app.domain.video_compress import Probe
from tests.bot.harness import GROUP, MB, USER, Harness
from tests.conftest import EXECUTED_SQL

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg not installed"
)


def fake_run(output_size: int | None, calls: list[list[str]]):  # type: ignore[no-untyped-def]
    async def run(command: list[str]) -> None:
        calls.append(command)
        if output_size is None:
            raise RuntimeError("ffmpeg exit 1: broken")
        Path(command[-1]).write_bytes(b"o" * output_size)

    return run


def fake_probe(info: Probe):  # type: ignore[no-untyped-def]
    async def run(path: Path) -> Probe:
        return info

    return run


H264 = Probe("mov,mp4,m4a,3gp,3g2,mj2", 9.0, "h264", "yuv420p", 640, 360, "aac")
HEVC = Probe("mov,mp4,m4a,3gp,3g2,mj2", 9.0, "hevc", "yuv420p10le", 1920, 1080, "aac")


@pytest.fixture
def tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(video_compress, "ffmpeg_available", lambda: True)


async def _save_video(h: Harness, size: int = 100) -> None:
    h.register_group()
    await h.send(GROUP, USER, video={"file_id": "vid", "file_size": size, "mime_type": "video/mp4"})
    await h.confirm([1])
    await h.settle()


def _media_updates(since: int) -> list[str]:
    return [s for s in EXECUTED_SQL[since:] if re.match(r"\s*UPDATE\s+PostMedia", s, re.I)]


def _log(h: Harness) -> dict:  # type: ignore[type-arg]
    return next(iter(json.loads((h.settings.data_path / "compression.json").read_text()).values()))


async def test_good_savings_use_transcoded_file(h: Harness, monkeypatch, tools) -> None:  # type: ignore[no-untyped-def]
    calls: list[list[str]] = []
    monkeypatch.setattr(video_compress, "probe", fake_probe(H264))
    monkeypatch.setattr(video_compress, "run_ffmpeg", fake_run(5, calls))  # 15 → 5 bytes
    start = len(EXECUTED_SQL)
    await _save_video(h)
    (path, size, mime), = h.root.rows("SELECT storage_path, file_size, mime_type FROM PostMedia")
    assert size == 5 and path.endswith(".mp4") and mime == "video/mp4"
    assert len(calls) == 1 and "libx264" in calls[0]
    assert len(_media_updates(start)) == 1
    assert _log(h)["reason"] == "transcoded"


async def test_incompatible_video_replaced_even_with_small_savings(h: Harness, monkeypatch, tools) -> None:  # type: ignore[no-untyped-def]
    calls: list[list[str]] = []
    monkeypatch.setattr(video_compress, "probe", fake_probe(HEVC))
    monkeypatch.setattr(video_compress, "run_ffmpeg", fake_run(14, calls))  # only 6.7 % smaller
    await _save_video(h)
    (size,), = h.root.rows("SELECT file_size FROM PostMedia")
    assert size == 14
    assert _log(h)["reason"] == "transcoded_for_compatibility"


async def test_compatible_video_with_small_savings_is_only_remuxed(h: Harness, monkeypatch, tools) -> None:  # type: ignore[no-untyped-def]
    calls: list[list[str]] = []
    monkeypatch.setattr(video_compress, "probe", fake_probe(H264))
    monkeypatch.setattr(video_compress, "run_ffmpeg", fake_run(14, calls))
    await _save_video(h)
    assert len(calls) == 2
    remux = " ".join(calls[1])
    assert "-c copy" in remux and "+faststart" in remux and "libx264" not in remux
    assert _log(h)["reason"] == "remuxed_faststart"


async def test_ffmpeg_error_keeps_original(h: Harness, monkeypatch, tools) -> None:  # type: ignore[no-untyped-def]
    start_len = len(EXECUTED_SQL)
    monkeypatch.setattr(video_compress, "probe", fake_probe(HEVC))
    monkeypatch.setattr(video_compress, "run_ffmpeg", fake_run(None, []))
    await _save_video(h)
    (path, size), = h.root.rows("SELECT storage_path, file_size FROM PostMedia")
    assert Path(path).read_bytes() == b"fake-file-bytes" and size == 100
    assert _media_updates(start_len) == []
    assert list(Path(path).parent.glob("*.c.mp4")) == []


async def test_missing_ffmpeg_skips(h: Harness, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[list[str]] = []
    monkeypatch.setattr(video_compress, "ffmpeg_available", lambda: False)
    monkeypatch.setattr(video_compress, "run_ffmpeg", fake_run(1, calls))
    await _save_video(h)
    assert calls == [] and _log(h)["reason"] == "ffmpeg_missing"


async def test_big_video_is_not_compressed(h: Harness, monkeypatch, tools) -> None:  # type: ignore[no-untyped-def]
    calls: list[list[str]] = []
    monkeypatch.setattr(video_compress, "run_ffmpeg", fake_run(1, calls))
    await _save_video(h, size=50 * MB)
    (path,), = h.root.rows("SELECT storage_path FROM PostMedia")
    assert path.startswith("bale:") and calls == []


async def test_document_is_left_alone(h: Harness, monkeypatch, tools) -> None:  # type: ignore[no-untyped-def]
    calls: list[list[str]] = []
    monkeypatch.setattr(video_compress, "run_ffmpeg", fake_run(1, calls))
    h.register_group()
    await h.send(GROUP, USER, document={"file_id": "doc", "file_name": "a.pdf", "file_size": 15})
    await h.confirm([1])
    await h.settle()
    (path,), = h.root.rows("SELECT storage_path FROM PostMedia")
    assert Path(path).read_bytes() == b"fake-file-bytes" and calls == []


async def test_only_one_job_at_a_time(h: Harness, monkeypatch, tools, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from app.domain.media_store import compress_stored

    running = peak = 0

    async def slow(command: list[str]) -> None:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.05)
        Path(command[-1]).write_bytes(b"s")
        running -= 1

    monkeypatch.setattr(video_compress, "probe", fake_probe(H264))
    monkeypatch.setattr(video_compress, "run_ffmpeg", slow)
    files = []
    for index in range(3):
        path = tmp_path / f"v{index}.mp4"
        path.write_bytes(b"0123456789")
        files.append(path)
    await asyncio.gather(*(compress_stored(h.ctx, 900 + i, p, 2) for i, p in enumerate(files)))
    assert peak == 1


def test_ffmpeg_settings() -> None:
    video = " ".join(video_compress.transcode_video_command(Path("in"), Path("out.mp4")))
    for part in (
        "-c:v libx264", "-pix_fmt yuv420p", "-profile:v main", "-crf 24", "-preset veryfast",
        "min(720", "-c:a aac", "-b:a 96k", "-movflags +faststart",
    ):  # fmt: skip
        assert part in video
    audio = " ".join(video_compress.audio_command(Path("in.ogg"), Path("out.m4a")))
    assert "-c:a aac" in audio and "-b:a 64k" in audio
    if shutil.which("nice"):
        assert video_compress.with_nice(["ffmpeg"])[:3] == ["nice", "-n", "19"]


def _make(args: list[str], out: Path) -> bytes:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args, str(out)], check=True)
    return out.read_bytes()


def _ffprobe(path: str, stream: str, entries: str) -> str:
    return subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries", f"stream={entries}",
         "-of", "csv=p=0", path],
        check=True, capture_output=True, text=True,
    ).stdout.strip()  # fmt: skip


@needs_ffmpeg
async def test_real_ffmpeg_makes_video_play_everywhere(h: Harness, tmp_path: Path) -> None:
    data = _make(
        ["-f", "lavfi", "-i", "testsrc=size=1080x1920:rate=25", "-f", "lavfi", "-i", "sine",
         "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv444p", "-crf", "30", "-c:a", "aac"],
        tmp_path / "portrait.mp4",
    )  # fmt: skip
    h.fake.file_bytes["vid"] = data
    await _save_video(h, size=len(data))
    (path, width, height), = h.root.rows("SELECT storage_path, width, height FROM PostMedia")
    assert set(_ffprobe(path, "v:0", "codec_name,pix_fmt,profile").split(",")) == {"h264", "yuv420p", "Main"}
    assert (width, height) == (720, 1280)  # portrait: short side 720, aspect kept


@needs_ffmpeg
async def test_real_ffmpeg_voice_becomes_m4a(h: Harness, tmp_path: Path) -> None:
    data = _make(
        ["-f", "lavfi", "-i", "sine=frequency=300", "-t", "2", "-c:a", "libopus"],
        tmp_path / "voice.ogg",
    )
    h.register_group()
    h.fake.file_bytes["voice1"] = data
    await h.send(GROUP, USER, voice={"file_id": "voice1", "file_size": len(data), "mime_type": "audio/ogg"})
    await h.confirm([1])
    await h.settle()
    (path, mime, mtype), = h.root.rows("SELECT storage_path, mime_type, media_type FROM PostMedia")
    assert mtype == 3 and path.endswith(".m4a") and mime == "audio/mp4"
    assert _ffprobe(path, "a:0", "codec_name") == "aac"
