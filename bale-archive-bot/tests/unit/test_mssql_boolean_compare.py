"""Boolean filters must not compile to ``IS 1`` / ``IS 0`` on SQL Server."""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects import mssql

from app.db.models import Group, Tag, User


def _compile(statement: object) -> str:
    return str(
        statement.compile(dialect=mssql.dialect(), compile_kwargs={"literal_binds": True})
    )


def test_boolean_filters_compile_without_is_literal_on_mssql() -> None:
    statements = [
        select(User).where(User.is_admin == True),  # noqa: E712
        select(User).where(User.is_admin == False),  # noqa: E712
        select(Tag).where(Tag.is_active == True),  # noqa: E712
        select(Tag).where(Tag.is_active == False),  # noqa: E712
        select(Group).where(Group.is_active == True),  # noqa: E712
        select(Group).where(Group.is_active == False),  # noqa: E712
    ]
    bad: list[str] = []
    for stmt in statements:
        sql = _compile(stmt)
        upper = sql.upper()
        if re.search(r"\bIS\s+1\b", upper) or re.search(r"\bIS\s+0\b", upper):
            bad.append(sql)
    assert bad == [], "MSSQL must not emit IS 1 / IS 0:\n" + "\n".join(bad)

    admin_sql = _compile(select(User).where(User.is_admin == True)).upper()  # noqa: E712
    assert re.search(r"IS_ADMIN\s*=\s*1", admin_sql) or re.search(
        r"IS_ADMIN\s*=\s*TRUE", admin_sql
    ), admin_sql


def test_no_boolean_is_true_false_left_in_app_source() -> None:
    root = Path(__file__).resolve().parents[2] / "app"
    hits: list[str] = []
    pattern = re.compile(r"\.is_\(\s*(True|False)\s*\)")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            hits.append(f"{path.relative_to(root.parent)}:{line_no}: {match.group(0)}")
    assert hits == [], "replace Boolean .is_(True/False) with == True/False:\n" + "\n".join(
        hits
    )


def test_list_admins_style_query_matches_repository() -> None:
    """Mirror UserRepository.list_admins and assert MSSQL-safe SQL."""
    sql = _compile(select(User).where(User.is_admin == True)).upper()  # noqa: E712
    assert "IS 1" not in sql
    assert "IS 0" not in sql
    assert "IS_ADMIN" in sql
