"""Build the full archive Excel file (same as the admin panel's export).

    python scripts/export_excel.py --output /path/file.xlsx
    python scripts/export_excel.py --output -        # bytes to stdout

Read-only (SELECT). Use scripts/export_excel.sh as root to get
/root/bale-archive.xlsx (mode 600) while the query runs as user balebot.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings, get_settings
from app.db.session import Database
from app.domain.excel import build_export
from app.domain.reports import PostFilter


async def build(settings: Settings) -> tuple[bytes, int]:
    db = Database(settings.database_url, pool_size=1, max_overflow=0)
    try:
        async with db.tx() as conn:
            return await build_export(conn, PostFilter(), settings)
    finally:
        await db.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="/root/bale-archive.xlsx")
    args = parser.parse_args()
    data, count = asyncio.run(build(get_settings()))
    if args.output == "-":
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    else:
        target = Path(args.output)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(target, 0o600)
    print(f"✅ {count} پست در اکسل.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
