"""Indexed text columns must not be NVARCHAR(max) on SQL Server."""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects import mssql
from sqlalchemy.schema import CreateTable

import app.db.models  # noqa: F401 — register metadata
from app.db.base import Base


def _mssql_type_sql(column: object) -> str:
    return str(column.type.compile(dialect=mssql.dialect())).upper()  # type: ignore[attr-defined]


def _is_unbounded_unicode(sql: str) -> bool:
    """True when SQL Server cannot use the type as an index/unique/PK key."""
    normalized = re.sub(r"\s+", "", sql)
    if "NVARCHAR(MAX)" in normalized or "VARCHAR(MAX)" in normalized:
        return True
    if normalized in {"NVARCHAR", "VARCHAR", "NTEXT", "TEXT"}:
        return True
    return False


def _indexed_column_names(table: object) -> set[str]:
    names: set[str] = {c.name for c in table.primary_key.columns}  # type: ignore[attr-defined]
    for column in table.columns:  # type: ignore[attr-defined]
        if column.unique:
            names.add(column.name)
    for constraint in table.constraints:  # type: ignore[attr-defined]
        if isinstance(constraint, UniqueConstraint):
            names.update(c.name for c in constraint.columns)
    for index in table.indexes:  # type: ignore[attr-defined]
        names.update(c.name for c in index.columns)
    return names


def test_orm_indexed_text_columns_have_bounded_nvarchar() -> None:
    """No UNIQUE / PK / Index text column may compile to NVARCHAR(max)."""
    bad: list[str] = []
    for table in Base.metadata.sorted_tables:
        for col_name in _indexed_column_names(table):
            column = table.c[col_name]
            sql = _mssql_type_sql(column)
            if not any(token in sql for token in ("NVARCHAR", "VARCHAR", "NCHAR", "CHAR", "TEXT")):
                continue
            if _is_unbounded_unicode(sql):
                bad.append(f"{table.name}.{col_name} -> {sql}")
            else:
                assert re.search(r"NVARCHAR\(\d+\)", sql), (
                    f"{table.name}.{col_name} must stay NVARCHAR(n), got {sql}"
                )
    assert bad == [], "indexed text columns must have explicit length:\n" + "\n".join(bad)


def test_known_key_columns_match_expected_lengths() -> None:
    expected = {
        ("tags", "slug"): 255,
        ("tags", "hashtag"): 255,
        ("submissions", "short_id"): 32,
        ("media_files", "sha256"): 64,
        ("app_settings", "key"): 128,
    }
    for (table_name, col_name), length in expected.items():
        column = Base.metadata.tables[table_name].c[col_name]
        sql = _mssql_type_sql(column)
        assert sql == f"NVARCHAR({length})", f"{table_name}.{col_name}: {sql}"


def test_create_table_ddl_has_no_indexed_nvarchar_max() -> None:
    dialect = mssql.dialect()
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=dialect)).upper()
        for col_name in _indexed_column_names(table):
            pattern = rf"\b{re.escape(col_name.upper())}\b\s+NVARCHAR\s*\(\s*MAX\s*\)"
            assert re.search(pattern, ddl) is None, (
                f"{table.name}.{col_name} is NVARCHAR(max) in CREATE TABLE DDL"
            )


def test_migration_uses_bounded_types_for_indexed_text() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0001_initial_schema.py"
    )
    source = path.read_text(encoding="utf-8")
    assert "indexed_text = NVARCHAR(255)" in source
    assert "short_id_col = NVARCHAR(32)" in source
    assert "sha256_col = NVARCHAR(64)" in source
    assert "settings_key_col = NVARCHAR(128)" in source
    assert 'sa.Column("slug", indexed_text' in source
    assert 'sa.Column("hashtag", indexed_text' in source
    assert 'sa.Column("short_id", short_id_col' in source
    assert 'sa.Column("sha256", sha256_col' in source
    assert 'sa.Column("key", settings_key_col' in source
    assert not re.search(
        r'sa\.Column\("(slug|hashtag|short_id|sha256|key)",\s*text_col',
        source,
    )
    assert "text_col = NVARCHAR(None)" in source
