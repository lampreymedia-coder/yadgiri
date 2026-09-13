"""Declarative base and portable column types.

Models must run on PostgreSQL, Microsoft SQL Server, and SQLite (tests).
On SQL Server every textual column must be NVARCHAR (never VARCHAR) so
Persian survives. ``UnicodeText`` / ``Unicode`` map to NVARCHAR there;
plain ``Text`` / ``String`` would become VARCHAR and corrupt فارسی.

SQL Server also rejects some referential actions (error 1785): self-referencing
FOREIGN KEY with ON DELETE/UPDATE CASCADE, SET NULL, or SET DEFAULT. Those
must be NO ACTION in DDL; application code clears children before delete.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, BigInteger, ForeignKey, Integer, Unicode, UnicodeText
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def PortableText() -> Any:  # noqa: N802 - factory named like a type
    """Unlimited unicode text: NVARCHAR(max) on SQL Server, TEXT elsewhere."""
    return UnicodeText().with_variant(NVARCHAR(None), "mssql")


def PortableString(length: int) -> Any:  # noqa: N802 - factory named like a type
    """Bounded unicode string: NVARCHAR(n) on SQL Server."""
    return Unicode(length).with_variant(NVARCHAR(length), "mssql")


def PortableJSON() -> Any:  # noqa: N802 - factory named like a type
    """JSONB on PostgreSQL; NVARCHAR(max) JSON text on SQL Server; JSON elsewhere."""
    return (
        JSON()
        .with_variant(JSONB(), "postgresql")
        .with_variant(NVARCHAR(None), "mssql")
    )


def BigIntPK() -> Any:  # noqa: N802 - factory named like a type
    """BIGINT on PostgreSQL/MSSQL; plain INTEGER on SQLite so autoincrement works."""
    return BigInteger().with_variant(Integer(), "sqlite")


def SelfReferentialFK(column: str) -> ForeignKey:  # noqa: N802 - factory named like a type
    """Self-referential FK without ON DELETE/UPDATE actions.

    SQL Server forbids CASCADE / SET NULL / SET DEFAULT on self-referencing
    keys. Alembic still adds ON DELETE SET NULL on PostgreSQL/SQLite where
    supported; ORM metadata stays MSSQL-safe for ``create_all`` / DDL compile.
    """
    return ForeignKey(column)
