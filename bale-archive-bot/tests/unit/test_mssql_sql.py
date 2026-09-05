"""SQL Server report SQL must not use Postgres/SQLite-only syntax."""

from __future__ import annotations

from app.domain import reports


def _sql(clause: object) -> str:
    return str(clause).upper()


def test_mssql_top_users_uses_fetch_and_concat() -> None:
    sql = _sql(reports._TOP_USERS_MSSQL)
    assert "FETCH NEXT" in sql
    assert "LIMIT" not in sql
    assert "CONCAT" in sql
    assert "||" not in str(reports._TOP_USERS_MSSQL)
    assert "DISPLAY_NAME" in sql
    assert "GROUP BY U.ID, U.FIRST_NAME" in sql


def test_mssql_search_uses_like_and_top() -> None:
    sql = _sql(reports._SEARCH_MSSQL)
    assert "TOP 20" in sql
    assert "ILIKE" not in sql
    assert "LIMIT" not in sql
    assert "LIKE" in sql
    assert "':' + :Q" not in sql
    assert "%' + :q + '%" in str(reports._SEARCH_MSSQL)


def test_mssql_export_uses_string_agg() -> None:
    sql = _sql(reports._EXPORT_MSSQL)
    assert "STRING_AGG" in sql
    assert "GROUP_CONCAT" not in sql
    assert "CONCAT" in sql


def test_mssql_health_uses_sys_database_files() -> None:
    sql = _sql(reports._HEALTH_MSSQL)
    assert "SYS.DATABASE_FILES" in sql
    assert "PG_DATABASE_SIZE" not in sql
    assert "PRAGMA" not in sql


def test_mssql_trend_casts_date() -> None:
    sql = _sql(reports._TREND_MSSQL)
    assert "CAST(COMPLETED_AT AS DATE)" in sql
    assert "DATE_TRUNC" not in sql
    assert "DATE(COMPLETED_AT)" not in sql


def test_postgres_sql_is_unchanged() -> None:
    sql = _sql(reports._OVERALL_SQL)
    assert "FILTER" in sql
    assert "LATERAL" in sql
    assert "PG_DATABASE_SIZE" in _sql(reports._HEALTH_SQL)
