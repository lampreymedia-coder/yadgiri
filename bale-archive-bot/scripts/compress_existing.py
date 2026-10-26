"""Compress/convert files already on disk with the bot's current rules.

    python scripts/compress_existing.py            # dry run (default): report only
    python scripts/compress_existing.py --apply    # really process

Picks files that are not in compression.json yet, or whose entry says
"ffmpeg_missing". Uses the same one-job-at-a-time lock as the bot (also
across processes), under nice. Only existing PostMedia columns are updated.
Run as the balebot user with the bot's env file, e.g.:
    sudo -u balebot env BALEBOT_ENV_FILE=/etc/balebot/balebot.env \
        /opt/balebot/venv/bin/python scripts/compress_existing.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings, get_settings
from app.db import repo
from app.db.session import Database
from app.domain.media_store import compress_stored
from app.domain.video_compress import CompressionLog, ffmpeg_available
from app.mapping import MEDIA_AUDIO, MEDIA_IMAGE, MEDIA_VIDEO

KINDS = {MEDIA_IMAGE: "تصویر", MEDIA_VIDEO: "ویدیو", MEDIA_AUDIO: "صوت"}


@dataclass
class Deps:
    settings: Settings
    db: Database
    compression_log: CompressionLog
    compress_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def select_files(
    rows: list[repo.MediaRow], log: dict[str, dict[str, object]], media_root: Path
) -> list[tuple[repo.MediaRow, Path, int]]:
    """Files on disk (inside media/) that were never compressed, or only skipped for lack of ffmpeg."""
    root = os.path.realpath(media_root)
    picked = []
    for row in rows:
        if row.media_type not in KINDS:
            continue
        entry = log.get(str(row.id))
        if entry is not None and entry.get("reason") != "ffmpeg_missing":
            continue
        real = os.path.realpath(row.storage_path)
        if not real.startswith(root + os.sep) or not os.path.isfile(real):
            continue
        picked.append((row, Path(real), os.path.getsize(real)))
    return picked


async def candidates(deps: Deps) -> list[tuple[repo.MediaRow, Path, int]]:
    async with deps.db.tx() as conn:
        rows = await repo.local_media_rows(conn)
    log = deps.compression_log.entries()
    return await asyncio.to_thread(select_files, rows, log, deps.settings.media_root)


async def run(apply: bool, settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    deps = Deps(
        settings=settings,
        db=Database(settings.database_url, pool_size=1, max_overflow=0),
        compression_log=CompressionLog(settings.data_path / "compression.json"),
    )
    try:
        todo = await candidates(deps)
        total = sum(size for _, _, size in todo)
        print(f"{len(todo)} فایل برای پردازش ({total / 1024 / 1024:.1f} مگابایت)")
        for row, path, _ in todo:
            print(f"  #{row.id} پست {row.post_id} {KINDS[row.media_type]} {path.name}")
        if not apply:
            print("حالت آزمایشی (--dry-run): هیچ تغییری انجام نشد. برای اجرا: --apply")
            return 0
        if not ffmpeg_available():
            print("❌ ffmpeg/ffprobe نصب نیست. اول deploy.sh را اجرا کنید.")
            return 1
        for row, path, _ in todo:
            result = await compress_stored(deps, row.id, path, row.media_type)
            if result is not None:
                print(f"  #{row.id}: {result.reason} ({result.saved_pct}٪)")
        print("✅ تمام شد.")
        return 0
    finally:
        await deps.db.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="only report (default)")
    mode.add_argument("--apply", action="store_true", help="really compress")
    args = parser.parse_args()
    return asyncio.run(run(apply=args.apply))


if __name__ == "__main__":
    sys.exit(main())
