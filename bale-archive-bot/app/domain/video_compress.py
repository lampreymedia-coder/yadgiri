"""Optional ffmpeg-based video compression for the media worker.

Runs only in the background media backlog — never on the wizard path.
Safety rules are hard: missing ffmpeg, failures, or weak savings keep the original.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.observability.logging import get_logger

logger = get_logger(__name__)

# Keep original unless compressed is at least this much smaller.
_MIN_SAVINGS_RATIO = 0.15


@dataclass(slots=True, frozen=True)
class VideoCompressResult:
    """Outcome of an attempted compression."""

    used_compressed: bool
    data: bytes
    reason: str


def ffmpeg_available() -> bool:
    """True when an ``ffmpeg`` executable is on PATH."""
    return shutil.which("ffmpeg") is not None


def is_video_media(*, mime_type: str | None, file_name: str | None) -> bool:
    mime = (mime_type or "").lower()
    if mime.startswith("video/"):
        return True
    name = (file_name or "").lower()
    return any(
        name.endswith(ext)
        for ext in (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpeg", ".mpg")
    )


async def compress_video(
    data: bytes,
    *,
    crf: int = 24,
    max_height: int = 720,
    audio_bitrate: str = "96k",
    preset: str = "veryfast",
) -> VideoCompressResult:
    """Compress ``data`` with ffmpeg or return the original unchanged.

    Never raises for expected operational failures — callers always get bytes.
    """
    if not data:
        return VideoCompressResult(False, data, "empty")
    if not ffmpeg_available():
        logger.info("video_compress_skipped", reason="ffmpeg_missing")
        return VideoCompressResult(False, data, "ffmpeg_missing")

    original_size = len(data)
    try:
        compressed = await asyncio.to_thread(
            _run_ffmpeg_sync,
            data,
            crf=crf,
            max_height=max_height,
            audio_bitrate=audio_bitrate,
            preset=preset,
        )
    except (OSError, RuntimeError, ValueError, TimeoutError) as exc:
        logger.warning("video_compress_failed", error=str(exc), original_size=original_size)
        return VideoCompressResult(False, data, f"error:{exc}")

    if not compressed:
        return VideoCompressResult(False, data, "empty_output")

    compressed_size = len(compressed)
    if compressed_size >= original_size:
        logger.info(
            "video_compress_rejected",
            reason="larger_or_equal",
            original_size=original_size,
            compressed_size=compressed_size,
        )
        return VideoCompressResult(False, data, "larger_or_equal")

    savings = (original_size - compressed_size) / original_size
    if savings < _MIN_SAVINGS_RATIO:
        logger.info(
            "video_compress_rejected",
            reason="savings_below_15pct",
            original_size=original_size,
            compressed_size=compressed_size,
            savings=round(savings, 3),
        )
        return VideoCompressResult(False, data, "savings_below_15pct")

    logger.info(
        "video_compress_ok",
        original_size=original_size,
        compressed_size=compressed_size,
        savings=round(savings, 3),
    )
    return VideoCompressResult(True, compressed, "ok")


def _run_ffmpeg_sync(
    data: bytes,
    *,
    crf: int,
    max_height: int,
    audio_bitrate: str,
    preset: str,
) -> bytes:
    """Write temp files, run ffmpeg, return compressed bytes. Raises on failure."""
    import subprocess

    with tempfile.TemporaryDirectory(prefix="bale-vid-") as tmp:
        root = Path(tmp)
        src = root / "input.bin"
        dst = root / "output.mp4"
        src.write_bytes(data)
        # Scale down only: never upscale smaller videos (min(ih, max_height)).
        scale = f"scale=-2:'min({int(max_height)},ih)'"
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(int(crf)),
            "-vf",
            scale,
            "-c:a",
            "aac",
            "-b:a",
            audio_bitrate,
            "-movflags",
            "+faststart",
            str(dst),
        ]
        try:
            completed = subprocess.run(  # noqa: S603 — fixed argv, no shell
                cmd,
                check=False,
                capture_output=True,
                timeout=600,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("ffmpeg timed out") from exc
        if completed.returncode != 0:
            err = (completed.stderr or b"").decode("utf-8", errors="replace")[:500]
            raise RuntimeError(err or f"ffmpeg exit {completed.returncode}")
        if not dst.is_file():
            raise RuntimeError("ffmpeg produced no output file")
        return dst.read_bytes()
