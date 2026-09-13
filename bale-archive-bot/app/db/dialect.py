"""Dialect helpers for PostgreSQL, SQLite, and Microsoft SQL Server.

Report SQL, advisory locks, and upserts branch on these names. The ORM
column types stay portable (JSONB/ARRAY only on PostgreSQL).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

_POSTGRES = "postgresql"
_SQLITE = "sqlite"
_MSSQL = "mssql"


def dialect_name(session: AsyncSession) -> str:
    """SQLAlchemy dialect name (``postgresql``, ``sqlite``, ``mssql``, …)."""
    return session.get_bind().dialect.name


def engine_kind_from_url(url: str) -> str:
    """Map a SQLAlchemy URL to ``postgres``, ``sqlite``, ``mssql``, or ``unknown``."""
    lowered = url.strip().lower()
    if lowered.startswith("postgresql"):
        return "postgres"
    if lowered.startswith("sqlite"):
        return "sqlite"
    if lowered.startswith("mssql"):
        return "mssql"
    return "unknown"


def is_postgres(session: AsyncSession) -> bool:
    return dialect_name(session) == _POSTGRES


def is_sqlite(session: AsyncSession) -> bool:
    return dialect_name(session) == _SQLITE


def is_mssql(session: AsyncSession) -> bool:
    return dialect_name(session) == _MSSQL


def supports_on_conflict(session: AsyncSession) -> bool:
    """True when INSERT … ON CONFLICT is available (PostgreSQL and SQLite)."""
    return dialect_name(session) in {_POSTGRES, _SQLITE}
