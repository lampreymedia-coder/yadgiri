"""Seed the three initial tags. Idempotent: existing slugs are skipped.

Usage: DATABASE_URL=... python scripts/seed_tags.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.repositories.tags import TagRepository
from app.i18n.fa import SEED_TAGS


async def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        repo = TagRepository(session)
        created = 0
        for slug, title_fa, hashtag in SEED_TAGS:
            if await repo.get_by_slug(slug) is None:
                await repo.create(slug=slug, title_fa=title_fa, hashtag=hashtag)
                created += 1
                print(f"created tag: {slug} {hashtag}")
            else:
                print(f"exists, skipped: {slug}")
    await engine.dispose()
    print(f"done; created {created} tag(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
