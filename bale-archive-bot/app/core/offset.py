"""Last Bale update offset, kept in a small local file (never the database)."""

from __future__ import annotations

import os
from pathlib import Path

from app.observability.logging import get_logger

logger = get_logger(__name__)


class OffsetStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> int | None:
        try:
            raw = self.path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None
        except OSError as exc:
            logger.warning("offset_read_failed", error=str(exc))
            return None
        try:
            value = int(raw)
        except ValueError:
            logger.warning("offset_file_invalid", content=raw[:40])
            return None
        return value if value > 0 else None

    def save(self, offset: int) -> None:
        """Atomic write: a crash never leaves a half-written file."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(str(offset), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as exc:
            logger.warning("offset_write_failed", error=str(exc))
