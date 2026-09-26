"""SQL Server rejects illegal FK referential actions (error 1785).

Compile Alembic 0001 and ORM DDL for the mssql dialect and assert none of
the forbidden patterns appear: self-referencing ON DELETE/UPDATE CASCADE,
SET NULL, or SET DEFAULT; and multiple cascade paths to the same table.
"""

from __future__ import annotations

import importlib.util
import re
from collections import defaultdict, deque
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import ForeignKeyConstraint, create_mock_engine
from sqlalchemy.dialects import mssql
from sqlalchemy.schema import CreateTable

import app.db.models  # noqa: F401 — register metadata
from app.db.base import Base

_CASCADE_ACTIONS = frozenset({"CASCADE", "SET NULL", "SET_NULL", "SET DEFAULT", "SET_DEFAULT"})


def _normalize_action(action: str | None) -> str | None:
    if action is None:
        return None
    return re.sub(r"\s+", "_", action.strip().upper())


def _is_cascading(action: str | None) -> bool:
    normalized = _normalize_action(action)
    return normalized in _CASCADE_ACTIONS if normalized else False


def _load_migration():
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0001_initial_schema.py"
    )
    spec = importlib.util.spec_from_file_location("alembic_0001_fk", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _capture_mssql_migration_ddl() -> list[str]:
    """Run ``upgrade()`` against a mock MSSQL engine and collect DDL text."""
    statements: list[str] = []
    dialect = mssql.dialect()

    def dump(sql, *multiparams, **params) -> None:  # noqa: ANN001
        text = str(sql.compile(dialect=dialect))
        if text.strip():
            statements.append(text)

    engine = create_mock_engine("mssql+pyodbc://localhost/bale_archive", dump)
    conn = engine.connect()
    context = MigrationContext.configure(conn)
    with Operations.context(context):
        _load_migration().upgrade()
    return statements


_FK_REF_RE = re.compile(
    r"FOREIGN\s+KEY\s*\((?P<cols>[^)]+)\)\s*"
    r"REFERENCES\s+(?P<ref>(?:\[[^\]]+\]|\w+))"
    r"(?:\s*\([^)]*\))?"
    r"(?P<actions>(?:\s+ON\s+(?:DELETE|UPDATE)\s+(?:CASCADE|SET\s+NULL|SET\s+DEFAULT|NO\s+ACTION))*)",
    re.IGNORECASE,
)


def _table_name_from_create(statement: str) -> str | None:
    match = re.search(
        r"CREATE\s+TABLE\s+(?P<name>(?:\[[^\]]+\]|\w+))",
        statement,
        re.IGNORECASE,
    )
    if not match:
        return None
    return match.group("name").strip("[]")


def _find_illegal_self_ref_actions(ddl_statements: list[str]) -> list[str]:
    bad: list[str] = []
    for statement in ddl_statements:
        table = _table_name_from_create(statement)
        if table is None:
            continue
        for match in _FK_REF_RE.finditer(statement):
            ref = match.group("ref").strip("[]")
            actions = match.group("actions") or ""
            if ref.lower() != table.lower():
                continue
            for kind in ("DELETE", "UPDATE"):
                action_match = re.search(
                    rf"ON\s+{kind}\s+(CASCADE|SET\s+NULL|SET\s+DEFAULT)",
                    actions,
                    re.IGNORECASE,
                )
                if action_match:
                    bad.append(
                        f"{table}.{match.group('cols').strip()}: "
                        f"self-ref ON {kind} {action_match.group(1).upper()}"
                    )
    return bad


def _cascade_edges_from_metadata() -> dict[str, set[str]]:
    """parent_table -> child_tables that cascade (DELETE action) on FK."""
    edges: dict[str, set[str]] = defaultdict(set)
    for table in Base.metadata.tables.values():
        for fk in table.foreign_key_constraints:
            assert isinstance(fk, ForeignKeyConstraint)
            if not _is_cascading(fk.ondelete):
                continue
            referred = fk.referred_table
            if referred is None:
                continue
            edges[referred.name].add(table.name)
    return edges


def _multiple_cascade_paths(edges: dict[str, set[str]]) -> list[str]:
    """SQL Server 1785: a table must not be reachable by two cascade paths."""
    problems: list[str] = []
    roots = set(edges) | {c for children in edges.values() for c in children}
    for root in roots:
        # BFS counting distinct paths to each node (capped).
        path_count: dict[str, int] = defaultdict(int)
        path_count[root] = 1
        queue: deque[str] = deque([root])
        while queue:
            node = queue.popleft()
            for child in edges.get(node, ()):
                if child == node:
                    problems.append(f"self-cascade loop on {node}")
                    continue
                path_count[child] += path_count[node]
                if path_count[child] == path_count[node]:
                    # first arrival via this parent contribution
                    queue.append(child)
                if path_count[child] > 1:
                    problems.append(
                        f"multiple cascade paths to {child} when deleting {root}"
                    )
    # Unique messages
    return sorted(set(problems))


def test_mssql_migration_0001_has_no_illegal_fk_actions() -> None:
    ddl = _capture_mssql_migration_ddl()
    assert ddl, "expected mock engine to capture migration DDL"
    joined = "\n".join(ddl).upper()

    # Self-referential SET NULL was the production failure on tags.parent_id.
    assert "REFERENCES TAGS" in joined or "REFERENCES [TAGS]" in joined
    illegal = _find_illegal_self_ref_actions(ddl)
    assert illegal == [], "illegal self-ref FK actions in MSSQL migration DDL:\n" + "\n".join(
        illegal
    )

    # tags.parent_id must not carry ON DELETE at all on MSSQL.
    tags_creates = [s for s in ddl if re.search(r"CREATE\s+TABLE\s+\[?tags\]?", s, re.I)]
    assert tags_creates, "tags table CREATE missing from migration DDL"
    tags_sql = tags_creates[0].upper()
    assert "PARENT_ID" in tags_sql
    assert not re.search(
        r"PARENT_ID.*REFERENCES\s+\[?TAGS\]?.*ON\s+DELETE",
        tags_sql,
        re.IGNORECASE | re.DOTALL,
    )


def test_orm_mssql_create_table_has_no_illegal_fk_actions() -> None:
    dialect = mssql.dialect()
    bad: list[str] = []
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=dialect))
        illegal = _find_illegal_self_ref_actions([ddl])
        bad.extend(illegal)
        for fk in table.foreign_key_constraints:
            referred = fk.referred_table
            if referred is not None and referred.name == table.name:
                if _is_cascading(fk.ondelete) or _is_cascading(fk.onupdate):
                    bad.append(
                        f"ORM {table.name}: self-ref still has "
                        f"ondelete={fk.ondelete!r} onupdate={fk.onupdate!r}"
                    )
    assert bad == [], "illegal ORM FK actions for MSSQL:\n" + "\n".join(bad)


def test_no_multiple_cascade_paths_in_orm_metadata() -> None:
    problems = _multiple_cascade_paths(_cascade_edges_from_metadata())
    assert problems == [], "SQL Server would reject these cascade graphs:\n" + "\n".join(
        problems
    )


def test_migration_source_gates_tags_parent_ondelete() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0001_initial_schema.py"
    ).read_text(encoding="utf-8")
    assert "if is_mssql" in source
    assert 'sa.ForeignKey("tags.id", ondelete="SET NULL")' in source
    assert re.search(
        r'sa\.ForeignKey\("tags\.id"\)\s*\n\s*if is_mssql',
        source,
    ) or re.search(
        r'ForeignKey\("tags\.id"\)\s+if is_mssql',
        source,
    )
