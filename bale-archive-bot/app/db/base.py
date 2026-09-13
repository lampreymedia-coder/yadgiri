"""Declarative base and portable column types.

Models must run on PostgreSQL, Microsoft SQL Server, and SQLite (tests).
On SQL Server every textual column must be NVARCHAR (never VARCHAR) so
Persian survives. ``UnicodeText`` / ``Unicode`` map to NVARCHAR there;
plain ``Text`` / ``String`` would become VARCHAR and corrupt فارسی.

SQL Server also rejects some referential actions (error 1785): self-referencing
FOREIGN KEY with ON DELETE/UPDATE CASCADE, SET NULL, or SET DEFAULT. Those
must be NO ACTION in DDL; application code clears children before delete.

JSON columns are NVARCHAR(max) on SQL Server; pyodbc cannot bind a raw ``dict``
or ``list``, so ``PortableJSON`` serializes with ``json.dumps`` on that dialect.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import JSON, BigInteger, ForeignKey, Integer, Unicode, UnicodeText
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


def PortableText() -> Any:  # noqa: N802 - factory named like a type
    """Unlimited unicode text: NVARCHAR(max) on SQL Server, TEXT elsewhere."""
    return UnicodeText().with_variant(NVARCHAR(None), "mssql")


def PortableString(length: int) -> Any:  # noqa: N802 - factory named like a type
    """Bounded unicode string: NVARCHAR(n) on SQL Server."""
    return Unicode(length).with_variant(NVARCHAR(length), "mssql")


class _PortableJSON(TypeDecorator):
    """JSON document type that binds as NVARCHAR text on SQL Server.

    PostgreSQL uses JSONB; SQLite/other use SQLAlchemy ``JSON`` (native
    dict/list bind). MSSQL stores JSON in NVARCHAR(max) and needs explicit
    dumps/loads so pyodbc never sees a raw ``dict``.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        if dialect.name == "mssql":
            return dialect.type_descriptor(NVARCHAR(None))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        if dialect.name == "mssql":
            return json.dumps(value, ensure_ascii=False)
        return value

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        if dialect.name != "mssql":
            return value
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8")
        if isinstance(value, str):
            return json.loads(value)
        return value


def PortableJSON() -> Any:  # noqa: N802 - factory named like a type
    """JSONB on PostgreSQL; JSON text (NVARCHAR) on SQL Server; JSON elsewhere."""
    return _PortableJSON()


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
