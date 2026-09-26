"""NVARCHAR / Persian text safety for SQL Server."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import mssql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateTable

from app.db.base import Base, PortableJSON, PortableString, PortableText
from app.db.models import Tag, User


def _load_migration_module() -> object:
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0001_initial_schema.py"
    )
    spec = importlib.util.spec_from_file_location("alembic_0001_nvarchar", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_portable_text_compiles_to_nvarchar_on_mssql() -> None:
    dialect = mssql.dialect()
    text_sql = str(PortableText().compile(dialect=dialect)).upper()
    string_sql = str(PortableString(30).compile(dialect=dialect)).upper()
    json_sql = str(PortableJSON().compile(dialect=dialect)).upper()
    assert "NVARCHAR" in text_sql
    assert "NVARCHAR" in string_sql
    assert "NVARCHAR" in json_sql
    assert re.search(r"\bVARCHAR\b", re.sub(r"NVARCHAR", "", text_sql)) is None


def test_orm_tables_use_nvarchar_not_varchar_on_mssql() -> None:
    """Every textual ORM column must DDL to NVARCHAR on SQL Server."""
    dialect = mssql.dialect()
    varchar_hits: list[str] = []
    nvarchar_hits = 0
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=dialect)).upper()
        stripped = re.sub(r"NVARCHAR\s*(\(\s*(MAX|\d+)\s*\))?", "", ddl)
        if re.search(r"\bVARCHAR\b", stripped):
            varchar_hits.append(table.name)
        nvarchar_hits += len(re.findall(r"NVARCHAR", ddl))
    assert varchar_hits == [], f"VARCHAR found in MSSQL DDL for: {varchar_hits}"
    assert nvarchar_hits > 0


def test_mssql_migration_string_literals_use_n_prefix() -> None:
    migration = _load_migration_module()
    n_fa = migration._n_literal("فاطمه", is_mssql=True)  # type: ignore[attr-defined]
    plain = migration._n_literal("فاطمه", is_mssql=False)  # type: ignore[attr-defined]
    assert str(n_fa) == "N'فاطمه'"
    assert str(plain) == "'فاطمه'"
    listed = migration._nvarchar_in_list(("draft", "completed"))  # type: ignore[attr-defined]
    assert listed == "N'draft', N'completed'"


@pytest.mark.asyncio
async def test_persian_text_roundtrip_survives_write_and_read() -> None:
    """Write فارسی through the ORM and read it back unchanged."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    persian_title = "یادگیری اقتصاد ایران — گزارش فصلی"
    persian_hashtag = "#یادگیری"
    persian_name = "فاطمه رضایی"

    async with session_factory() as session, session.begin():
        user = User(
            bale_user_id=9_001,
            first_name=persian_name,
            last_name="آزمون",
            locale="fa",
        )
        session.add(user)
        await session.flush()
        tag = Tag(
            slug="yadgiri-test",
            title_fa=persian_title,
            hashtag=persian_hashtag,
            description="متن توضیحی با حروف ی و ک فارسی",
            emoji="📚",
            created_by=user.id,
        )
        session.add(tag)

    async with session_factory() as session:
        loaded_tag = (
            await session.execute(select(Tag).where(Tag.slug == "yadgiri-test"))
        ).scalar_one()
        loaded_user = (
            await session.execute(select(User).where(User.bale_user_id == 9_001))
        ).scalar_one()
        assert loaded_tag.title_fa == persian_title
        assert loaded_tag.hashtag == persian_hashtag
        assert "ی" in loaded_tag.title_fa
        assert "?" not in loaded_tag.title_fa
        assert loaded_user.first_name == persian_name
        assert loaded_user.display_name.startswith("فاطمه")

    await engine.dispose()
