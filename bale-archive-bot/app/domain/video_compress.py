"""Make stored videos and audio small and playable everywhere (Windows, Android, iPhone).

Video (ffmpeg under ``nice``):
    -c:v libx264 -pix_fmt yuv420p -profile:v main -crf 24 -preset veryfast,
    short side at most 720 px (aspect kept), -c:a aac -b:a 96k -movflags +faststart, .mp4
    * saves ≥ 15 %                  → the transcoded file replaces the original
    * saves < 15 %, original is not H.264/yuv420p → transcoded file anyway (compatibility)
    * saves < 15 %, original is compatible → only rewritten with -c copy +faststart
    * any error                     → the original stays untouched
Audio / voice: anything that is not already AAC-in-MP4 becomes .m4a (aac 64k).

Sizes and reasons go to ``<DATA_DIR>/compression.json`` — never to the database.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.observability.logging import get_logger

logger = get_logger(__name__)

MIN_SAVINGS = 0.15
TIMEOUT_SECONDS = 30 * 60

# Short side ≤ 720 px, aspect ratio kept, even dimensions for yuv420p.
SCALE_720 = (
    "scale='if(gt(iw,ih),-2,min(720,trunc(iw/2)*2))':'if(gt(iw,ih),min(720,trunc(ih/2)*2),-2)'"
)


def _base(src: Path) -> list[str]:
    return ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src)]


def transcode_video_command(src: Path, dst: Path) -> list[str]:
    return [
        *_base(src),
        "-map", "0:v:0", "-map", "0:a:0?",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "main",
        "-crf", "24", "-preset", "veryfast",
        "-vf", SCALE_720,
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart", str(dst),
    ]  # fmt: skip


def remux_command(src: Path, dst: Path) -> list[str]:
    return [*_base(src), "-map", "0", "-c", "copy", "-movflags", "+faststart", str(dst)]


def audio_command(src: Path, dst: Path) -> list[str]:
    return [
        *_base(src), "-vn", "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(dst),
    ]  # fmt: skip


def with_nice(command: list[str]) -> list[str]:
    return ["nice", "-n", "19", *command] if shutil.which("nice") else command


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


async def run_ffmpeg(command: list[str]) -> None:
    """Run one ffmpeg command (under nice); RuntimeError on failure or timeout."""
    process = await asyncio.create_subprocess_exec(
        *with_nice(command),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=TIMEOUT_SECONDS)
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        raise RuntimeError("ffmpeg timeout") from exc
    if process.returncode != 0:
        raise RuntimeError(
            f"ffmpeg exit {process.returncode}: {stderr.decode(errors='replace')[-300:]}"
        )


@dataclass(slots=True)
class Probe:
    format_name: str = ""
    duration: float | None = None
    video_codec: str | None = None
    pix_fmt: str | None = None
    width: int | None = None
    height: int | None = None
    audio_codec: str | None = None

    @property
    def has_video(self) -> bool:
        return self.video_codec is not None

    @property
    def has_audio(self) -> bool:
        return self.audio_codec is not None

    @property
    def video_compatible(self) -> bool:
        return self.video_codec == "h264" and self.pix_fmt == "yuv420p"


async def probe(path: Path) -> Probe | None:
    """ffprobe summary, or None when ffprobe is missing or the file is unreadable."""
    if shutil.which("ffprobe") is None:
        return None
    process = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )  # fmt: skip
    try:
        out, _ = await asyncio.wait_for(process.communicate(), timeout=120)
    except TimeoutError:
        process.kill()
        await process.wait()
        return None
    if process.returncode != 0:
        return None
    try:
        data = json.loads(out or b"{}")
    except ValueError:
        return None
    result = Probe(format_name=str(data.get("format", {}).get("format_name", "")))
    try:
        result.duration = float(data.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        result.duration = None
    for stream in data.get("streams", []):
        kind = stream.get("codec_type")
        if kind == "video" and result.video_codec is None:
            if (stream.get("disposition") or {}).get("attached_pic"):
                continue  # album art inside an audio file
            result.video_codec = stream.get("codec_name")
            result.pix_fmt = stream.get("pix_fmt")
            result.width = stream.get("width")
            result.height = stream.get("height")
        elif kind == "audio" and result.audio_codec is None:
            result.audio_codec = stream.get("codec_name")
    return result


@dataclass(slots=True)
class CompressResult:
    replaced: bool
    path: Path
    original_size: int
    new_size: int
    reason: str
    width: int | None = None
    height: int | None = None
    mime_type: str | None = None

    @property
    def saved_pct(self) -> float:
        if not self.original_size:
            return 0.0
        return round(100 * (self.original_size - self.new_size) / self.original_size, 1)


def _swap(src: Path, tmp: Path, final: Path) -> None:
    os.replace(tmp, final)
    if final != src:
        src.unlink(missing_ok=True)


async def _size(path: Path) -> int:
    return (await asyncio.to_thread(path.stat)).st_size


async def _unlink(path: Path) -> None:
    await asyncio.to_thread(path.unlink, missing_ok=True)


async def compress_video(src: Path) -> CompressResult:
    original = await _size(src)
    if not ffmpeg_available():
        return CompressResult(False, src, original, original, "ffmpeg_missing")
    info = await probe(src)
    if info is None or not info.has_video:
        return CompressResult(False, src, original, original, "probe_failed")
    final = src.with_suffix(".mp4")
    tmp = src.with_name(src.stem + ".c.mp4")
    try:
        await run_ffmpeg(transcode_video_command(src, tmp))
        new_size = await _size(tmp)
        if new_size <= 0:
            raise RuntimeError("empty output")
    except (OSError, RuntimeError) as exc:
        await _unlink(tmp)
        logger.warning("video_compress_failed", path=str(src), error=str(exc))
        return CompressResult(False, src, original, original, "error")

    saved = (original - new_size) / original if original else 0.0
    if saved >= MIN_SAVINGS or not info.video_compatible:
        after = await probe(tmp)
        await asyncio.to_thread(_swap, src, tmp, final)
        reason = "transcoded" if saved >= MIN_SAVINGS else "transcoded_for_compatibility"
        return CompressResult(
            True, final, original, new_size, reason,
            after.width if after else None, after.height if after else None, "video/mp4",
        )  # fmt: skip

    # Already H.264/yuv420p and little to gain: keep the streams, just add faststart.
    await _unlink(tmp)
    remuxed = src.with_name(src.stem + ".r.mp4")
    try:
        await run_ffmpeg(remux_command(src, remuxed))
        remux_size = await _size(remuxed)
        if remux_size <= 0:
            raise RuntimeError("empty output")
    except (OSError, RuntimeError) as exc:
        await _unlink(remuxed)
        logger.warning("video_remux_failed", path=str(src), error=str(exc))
        return CompressResult(False, src, original, original, "error")
    await asyncio.to_thread(_swap, src, remuxed, final)
    return CompressResult(
        True, final, original, remux_size, "remuxed_faststart", info.width, info.height, "video/mp4"
    )


async def convert_audio(src: Path) -> CompressResult:
    original = await _size(src)
    if not ffmpeg_available():
        return CompressResult(False, src, original, original, "ffmpeg_missing")
    info = await probe(src)
    if info is None or not info.has_audio:
        return CompressResult(False, src, original, original, "probe_failed")
    if info.audio_codec == "aac" and ("mp4" in info.format_name or "m4a" in info.format_name):
        return CompressResult(False, src, original, original, "already_aac")
    final = src.with_suffix(".m4a")
    tmp = src.with_name(src.stem + ".c.m4a")
    try:
        await run_ffmpeg(audio_command(src, tmp))
        new_size = await _size(tmp)
        if new_size <= 0:
            raise RuntimeError("empty output")
    except (OSError, RuntimeError) as exc:
        await _unlink(tmp)
        logger.warning("audio_convert_failed", path=str(src), error=str(exc))
        return CompressResult(False, src, original, original, "error")
    await asyncio.to_thread(_swap, src, tmp, final)
    return CompressResult(True, final, original, new_size, "audio_m4a", None, None, "audio/mp4")


class CompressionLog:
    """compression.json: media id → original size, new size, percent saved, reason."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> dict[str, dict[str, object]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict[str, dict[str, object]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def entries(self) -> dict[str, dict[str, object]]:
        return self._read()

    def record(self, media_id: int, result: CompressResult) -> None:
        data = self._read()
        data[str(media_id)] = {
            "path": str(result.path),
            "original_size": result.original_size,
            "new_size": result.new_size,
            "saved_pct": result.saved_pct,
            "replaced": result.replaced,
            "reason": result.reason,
        }
        self._write(data)

    def forget_paths(self, paths: list[str]) -> None:
        data = self._read()
        kept = {key: value for key, value in data.items() if value.get("path") not in set(paths)}
        if len(kept) != len(data):
            self._write(kept)

    def totals(self) -> tuple[int, int]:
        """(bytes before, bytes after) over successful compressions."""
        rows = [v for v in self._read().values() if v.get("replaced")]
        return (
            sum(int(v.get("original_size", 0)) for v in rows),  # type: ignore[call-overload]
            sum(int(v.get("new_size", 0)) for v in rows),  # type: ignore[call-overload]
        )
