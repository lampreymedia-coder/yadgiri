"""Shrink downloaded videos with ffmpeg, one job at a time (the server has 2 GB RAM).

ffmpeg -c:v libx264 -crf 24 -preset veryfast, max 720p, audio aac 96k, run
under ``nice``. The original stays when ffmpeg is missing, fails, or saves
less than 15 %. On success only PostMedia.storage_path and PostMedia.file_size
(both columns of the staff schema) are updated. Sizes and savings are kept in
``<DATA_DIR>/compression.json`` — never in the database.
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


def ffmpeg_command(src: Path, dst: Path) -> list[str]:
    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
        "-c:v", "libx264", "-crf", "24", "-preset", "veryfast",
        "-vf", "scale=-2:'min(720,ih)'",
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart", str(dst),
    ]  # fmt: skip
    if shutil.which("nice"):
        command = ["nice", "-n", "19", *command]
    return command


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


async def run_ffmpeg(src: Path, dst: Path) -> None:
    """Run ffmpeg; raises RuntimeError on a non-zero exit or timeout."""
    process = await asyncio.create_subprocess_exec(
        *ffmpeg_command(src, dst),
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
class CompressResult:
    replaced: bool
    path: Path
    original_size: int
    new_size: int
    reason: str

    @property
    def saved_pct(self) -> float:
        if not self.original_size:
            return 0.0
        return round(100 * (self.original_size - self.new_size) / self.original_size, 1)


async def compress_video(src: Path) -> CompressResult:
    original = (await asyncio.to_thread(src.stat)).st_size
    if not ffmpeg_available():
        return CompressResult(False, src, original, original, "ffmpeg_missing")
    dst = src.with_name(src.stem + ".c.mp4")
    try:
        await run_ffmpeg(src, dst)
        new_size = (await asyncio.to_thread(dst.stat)).st_size
    except (OSError, RuntimeError) as exc:
        await asyncio.to_thread(dst.unlink, missing_ok=True)
        logger.warning("video_compress_failed", path=str(src), error=str(exc))
        return CompressResult(False, src, original, original, "error")
    if new_size <= 0 or (original - new_size) / original < MIN_SAVINGS:
        await asyncio.to_thread(dst.unlink, missing_ok=True)
        return CompressResult(False, src, original, new_size, "savings_below_15pct")
    final = src.with_suffix(".mp4")
    await asyncio.to_thread(_swap, src, dst, final)
    return CompressResult(True, final, original, new_size, "ok")


def _swap(src: Path, dst: Path, final: Path) -> None:
    if final != src:
        src.unlink(missing_ok=True)
    os.replace(dst, final)


class CompressionLog:
    """compression.json: media id → original size, new size, percent saved."""

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
