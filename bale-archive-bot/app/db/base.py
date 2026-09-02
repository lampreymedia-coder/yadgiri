"""Declarative base and portable column types.

Models must run both on PostgreSQL (production) and SQLite (fast tests),
so JSONB / ARRAY get dialect variants that behave identically from Python.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, BigInteger, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def PortableJSON() -> Any:  # noqa: N802 - factory named like a type
    """JSONB on PostgreSQL, plain JSON elsewhere."""
    return JSON().with_variant(JSONB(), "postgresql")


def BigIntPK() -> Any:  # noqa: N802 - factory named like a type
    """BIGINT on PostgreSQL; plain INTEGER on SQLite so autoincrement works."""
    return BigInteger().with_variant(Integer(), "sqlite")
