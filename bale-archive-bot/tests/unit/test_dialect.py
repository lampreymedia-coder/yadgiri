"""Dialect helpers and SQL Server programming-error markers."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import OperationalError

from app.core.locks import advisory_xact_lock
from app.db.dialect import (
    dialect_name,
    engine_kind_from_url,
    is_mssql,
    is_postgres,
    is_sqlite,
    supports_on_conflict,
)
from app.db.session import Database, is_connectivity_error, is_sql_programming_error


class _Dialect:
    def __init__(self, name: str) -> None:
        self.name = name


class _Bind:
    def __init__(self, name: str) -> None:
        self.dialect = _Dialect(name)


class _Session:
    def __init__(self, name: str) -> None:
        self._bind = _Bind(name)
        self.bind = self._bind
        self.executed: list[tuple[str, object]] = []

    def get_bind(self) -> _Bind:
        return self._bind

    async def execute(self, stmt: object, params: object = None) -> None:
        self.executed.append((str(stmt), params))


def test_supported_database_url_validator() -> None:
    from app.config import Settings

    assert Settings._supported_database_url("mssql+aioodbc://x") == "mssql+aioodbc://x"
    assert Settings._supported_database_url("postgresql+asyncpg://x") == "postgresql+asyncpg://x"
    with pytest.raises(ValueError, match="DATABASE_URL"):
        Settings._supported_database_url("mysql://localhost/x")


def test_engine_kind_from_url() -> None:
    assert engine_kind_from_url("postgresql+asyncpg://x") == "postgres"
    assert engine_kind_from_url("sqlite+aiosqlite:///:memory:") == "sqlite"
    assert (
        engine_kind_from_url(
            "mssql+aioodbc://u:p@localhost:1433/db?driver=ODBC+Driver+18+for+SQL+Server"
        )
        == "mssql"
    )
    assert engine_kind_from_url("mysql+aiomysql://x") == "unknown"


def test_session_dialect_helpers() -> None:
    pg = _Session("postgresql")
    sqlite = _Session("sqlite")
    mssql = _Session("mssql")
    assert is_postgres(pg) is True  # type: ignore[arg-type]
    assert is_sqlite(sqlite) is True  # type: ignore[arg-type]
    assert is_mssql(mssql) is True  # type: ignore[arg-type]
    assert supports_on_conflict(pg) is True  # type: ignore[arg-type]
    assert supports_on_conflict(sqlite) is True  # type: ignore[arg-type]
    assert supports_on_conflict(mssql) is False  # type: ignore[arg-type]
    assert dialect_name(mssql) == "mssql"  # type: ignore[arg-type]


def test_mssql_invalid_column_is_not_connectivity() -> None:
    orig = Exception("Invalid column name 'display_name'")
    exc = OperationalError("(pyodbc.ProgrammingError) Invalid column name 'display_name'", {}, orig)
    assert is_sql_programming_error(exc) is True
    assert is_connectivity_error(exc) is False


def test_mssql_invalid_object_is_not_connectivity() -> None:
    orig = Exception("Invalid object name 'users'")
    exc = OperationalError("(pyodbc.ProgrammingError) Invalid object name 'users'", {}, orig)
    assert is_sql_programming_error(exc) is True
    assert is_connectivity_error(exc) is False


async def test_advisory_lock_uses_sp_getapplock_on_mssql() -> None:
    session = _Session("mssql")
    await advisory_xact_lock(session, 10, 20)  # type: ignore[arg-type]
    assert session.executed
    sql, params = session.executed[0]
    assert "sp_getapplock" in sql
    assert params == {"key": "10:20"}


async def test_advisory_lock_is_noop_on_sqlite() -> None:
    session = _Session("sqlite")
    await advisory_xact_lock(session, 1, 2)  # type: ignore[arg-type]
    assert session.executed == []


def test_mssql_engine_requires_optional_extra() -> None:
    try:
        import aioodbc  # noqa: F401
    except ImportError:
        try:
            Database("mssql+aioodbc://u:p@localhost/db")
        except RuntimeError as exc:
            assert "mssql" in str(exc).lower()
        else:
            raise AssertionError("expected RuntimeError when aioodbc is missing")
    else:
        # Driver extra is present; constructing the engine must not crash.
        database = Database(
            "mssql+aioodbc://u:p@localhost:1433/db"
            "?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
        )
        assert database.engine is not None
