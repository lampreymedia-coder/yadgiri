"""Group upsert without ON CONFLICT (the SQL Server path) still works on SQLite."""

from __future__ import annotations

from app.db.repositories.groups import GroupRepository
from app.db.session import Database


async def test_portable_group_upsert_inserts_and_updates(seeded_db: Database) -> None:
    async with seeded_db.session() as session:
        groups = GroupRepository(session)
        first = await groups._upsert_portable(-9001, "پژوهش", "group")
        second = await groups._upsert_portable(-9001, "پژوهش دو", "group")
        assert first.id == second.id
        assert second.title == "پژوهش دو"
        assert second.is_active is True


async def test_normal_upsert_still_uses_sqlite_on_conflict(seeded_db: Database) -> None:
    async with seeded_db.session() as session:
        groups = GroupRepository(session)
        first = await groups.upsert(-9002, "الف", "group")
        second = await groups.upsert(-9002, "ب", "supergroup")
        assert first.id == second.id
        assert second.title == "ب"
