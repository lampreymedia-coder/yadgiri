"""Shrink downloaded pictures with Pillow (same one-job-at-a-time queue as videos).

* EXIF rotation is applied first, then all metadata is dropped.
* Longest side above 1920 px → scaled down to 1920, aspect ratio kept.
* Pictures are saved as JPEG quality 85, optimize=True — except transparent
  PNGs, which stay PNG (optimize=True).
* The original stays when saving is below 15 % or anything fails.
Only PostMedia columns of the staff schema change (storage_path, file_size,
width, height, mime_type); the log goes to compression.json.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

from app.domain.video_compress import MIN_SAVINGS, CompressResult
from app.observability.logging import get_logger

logger = get_logger(__name__)

MAX_SIDE = 1920
JPEG_QUALITY = 85


@dataclass(slots=True)
class ImageResult(CompressResult):
    width: int | None = None
    height: int | None = None
    mime_type: str | None = None


def _has_alpha(image: Image.Image) -> bool:
    if image.mode in ("RGBA", "LA"):
        return image.getchannel("A").getextrema()[0] < 255
    return image.mode == "P" and "transparency" in image.info


def _compress_sync(src: Path) -> ImageResult:
    original = src.stat().st_size
    with Image.open(src) as opened:
        source_format = opened.format
        image = ImageOps.exif_transpose(opened)
        keep_png = source_format == "PNG" and _has_alpha(image)
        if max(image.size) > MAX_SIDE:
            image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
        if keep_png:
            final, fmt, mime = src.with_suffix(".png"), "PNG", "image/png"
            if image.mode not in ("RGBA", "LA", "P"):
                image = image.convert("RGBA")
            options: dict[str, object] = {"optimize": True}
        else:
            final, fmt, mime = src.with_suffix(".jpg"), "JPEG", "image/jpeg"
            if image.mode != "RGB":
                image = image.convert("RGB")
            options = {"quality": JPEG_QUALITY, "optimize": True}
        width, height = image.size
        tmp = src.with_name(src.stem + ".c" + final.suffix)
        # Pillow writes no EXIF/ICC/text unless asked: metadata is dropped.
        image.save(tmp, fmt, **options)
    new_size = tmp.stat().st_size
    if new_size <= 0 or (original - new_size) / original < MIN_SAVINGS:
        tmp.unlink(missing_ok=True)
        return ImageResult(False, src, original, new_size, "savings_below_15pct")
    if final != src:
        src.unlink(missing_ok=True)
    os.replace(tmp, final)
    return ImageResult(True, final, original, new_size, "ok", width, height, mime)


def _cleanup_after_error(src: Path) -> int:
    for leftover in src.parent.glob(src.stem + ".c.*"):
        leftover.unlink(missing_ok=True)
    return src.stat().st_size if src.exists() else 0


async def compress_image(src: Path) -> ImageResult:
    try:
        return await asyncio.to_thread(_compress_sync, src)
    except Exception as exc:  # noqa: BLE001 — any Pillow/OS error keeps the original
        logger.warning("image_compress_failed", path=str(src), error=str(exc))
        size = await asyncio.to_thread(_cleanup_after_error, src)
        return ImageResult(False, src, size, size, "error")
