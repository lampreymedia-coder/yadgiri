"""Print whether DATABASE_URL accepts a connection. Never prints secrets."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.config import Settings
from app.db.dialect import engine_kind_from_url
from app.db.session import Database


async def _main() -> int:
    settings = Settings()
    kind = engine_kind_from_url(settings.database_url)
    print(f"engine={kind}")
    database = Database(settings.database_url)
    try:
        async with database.session() as session:
            value = await session.scalar(text("SELECT 1"))
        if value != 1:
            print("database_unexpected_result")
            return 1
    except Exception as exc:
        print(f"database_error={type(exc).__name__}")
        return 1
    finally:
        await database.dispose()
    print("database_ok")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
