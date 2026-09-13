"""PortableJSON must bind dict/list as text on SQL Server (pyodbc HY105)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from sqlalchemy import insert, select
from sqlalchemy.dialects import mssql, postgresql, sqlite
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base, PortableJSON, _PortableJSON
from app.db.models import Group


def _uses_portable_json(column_type: object) -> bool:
    if isinstance(column_type, _PortableJSON):
        return True
    impl = getattr(column_type, "impl", None)
    return isinstance(impl, _PortableJSON)


def test_portable_json_still_compiles_to_nvarchar_on_mssql() -> None:
    sql = str(PortableJSON().compile(dialect=mssql.dialect())).upper()
    assert "NVARCHAR" in sql
    assert re.search(r"\bVARCHAR\b", re.sub(r"NVARCHAR", "", sql)) is None


def test_mssql_bind_dumps_dict_and_list_with_persian() -> None:
    col = _PortableJSON()
    dialect = mssql.dialect()
    payload = {"نام": "سنجش ربات"}
    bound = col.process_bind_param(payload, dialect)
    assert isinstance(bound, str)
    assert "سنجش ربات" in bound
    assert "\\u" not in bound  # ensure_ascii=False
    assert json.loads(bound) == payload
    assert col.process_result_value(bound, dialect) == payload

    urls = ["https://a.ir", "https://ب.ir"]
    bound_list = col.process_bind_param(urls, dialect)
    assert isinstance(bound_list, str)
    assert json.loads(bound_list) == urls

    assert col.process_bind_param(None, dialect) is None


def test_mssql_app_settings_scalar_is_isjson_safe() -> None:
    """Bare numbers fail ISJSON on several SQL Server builds; wrap scalars."""
    col = _PortableJSON()
    dialect = mssql.dialect()
    owner_id = 1_290_496_049
    bound = col.process_bind_param(owner_id, dialect)
    assert isinstance(bound, str)
    loaded = json.loads(bound)
    assert isinstance(loaded, dict)
    assert loaded.get("__scalar__") == owner_id
    assert bound.strip()[:1] == "{"
    assert col.process_result_value(bound, dialect) == owner_id


def test_mssql_result_loads_text_back_to_python() -> None:
    col = _PortableJSON()
    dialect = mssql.dialect()
    text = json.dumps({"note": "فارسی"}, ensure_ascii=False)
    assert col.process_result_value(text, dialect) == {"note": "فارسی"}
    assert col.process_result_value(None, dialect) is None
    assert col.process_result_value({"x": 1}, dialect) == {"x": 1}


def test_postgres_and_sqlite_keep_native_python_objects_on_bind() -> None:
    col = _PortableJSON()
    payload = {"a": 1, "نام": "تست"}
    assert col.process_bind_param(payload, postgresql.dialect()) is payload
    assert col.process_bind_param(payload, sqlite.dialect()) is payload
    assert col.process_result_value(payload, postgresql.dialect()) is payload


def test_all_orm_json_columns_use_portable_json() -> None:
    expected = {
        ("groups", "settings"),
        ("submissions", "meta"),
        ("submissions", "raw_update"),
        ("submissions", "urls"),
        ("conversation_states", "history"),
        ("conversation_states", "payload"),
        ("outbox", "payload"),
        ("audit_log", "payload"),
        ("app_settings", "value"),
    }
    missing: list[str] = []
    for table_name, column_name in sorted(expected):
        column = Base.metadata.tables[table_name].c[column_name]
        if not _uses_portable_json(column.type):
            missing.append(f"{table_name}.{column_name}: {type(column.type)!r}")
    assert not missing, "JSON columns must use PortableJSON:\n" + "\n".join(missing)


def test_no_bare_mssql_nvarchar_json_variant_in_models_source() -> None:
    models = (
        Path(__file__).resolve().parents[2] / "app" / "db" / "models.py"
    ).read_text(encoding="utf-8")
    assert 'with_variant(NVARCHAR(None), "mssql")' not in models
    assert "with_variant(NVARCHAR(None), 'mssql')" not in models


@pytest.mark.asyncio
async def test_sqlite_json_roundtrip_still_works() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with factory() as session, session.begin():
        session.add(
            Group(
                bale_chat_id=-1001,
                title="گروه",
                chat_type="group",
                settings={"role": "archive", "tag_slug": "اقتصاد"},
            )
        )

    async with factory() as session:
        group = (
            await session.execute(select(Group).where(Group.bale_chat_id == -1001))
        ).scalar_one()
        assert group.settings["role"] == "archive"
        assert group.settings["tag_slug"] == "اقتصاد"

    await engine.dispose()


def test_groups_settings_bind_processor_for_mssql() -> None:
    col = Group.__table__.c.settings
    bound = col.type.process_bind_param({"role": "main", "fa": "سلام"}, mssql.dialect())
    assert isinstance(bound, str)
    assert "سلام" in bound
    assert json.loads(bound) == {"role": "main", "fa": "سلام"}

    stmt = insert(Group).values(
        bale_chat_id=-1,
        title="t",
        chat_type="group",
        settings={"role": "main"},
        is_active=True,
        bot_can_delete=False,
    )
    sql = str(stmt.compile(dialect=mssql.dialect())).upper()
    assert "INSERT INTO" in sql and "GROUPS" in sql
