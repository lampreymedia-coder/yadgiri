"""Declarative base and portable column types.

Models must run on PostgreSQL, Microsoft SQL Server, and SQLite (tests),
so JSONB / ARRAY stay PostgreSQL-only variants. Other engines get JSON.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, BigInteger, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def PortableJSON() -> Any:  # noqa: N802 - factory named like a type
    """JSONB on PostgreSQL; NVARCHAR JSON on SQL Server; JSON on SQLite."""
    return JSON().with_variant(JSONB(), "postgresql")


def BigIntPK() -> Any:  # noqa: N802 - factory named like a type
    """BIGINT on PostgreSQL; plain INTEGER on SQLite so autoincrement works."""
    return BigInteger().with_variant(Integer(), "sqlite")
