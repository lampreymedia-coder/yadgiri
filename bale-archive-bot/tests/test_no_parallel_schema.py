"""Guard tests: no parallel schema, ever (CLAUDE-FEATURES-SAFE.md §3, CLAUDE-MERGE-SCHEMA.md §3.9).

The bot may only read/write rows in the 8 tables of the merged Bale_Archive
schema; it never runs DDL; it never updates Users except BaleUsername.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tests.conftest import EXECUTED_SQL

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_TABLES = {
    "Users", "BaleGroups", "BaleGroupMembers", "Hashtags", "Posts", "PostHashtags", "PostMedia",
    "OrgUnits",
}  # fmt: skip
OLD_TABLE_NAMES = ("Person", "EhyaGroup", "PersonGroup", "Hashtag", "Post", "PostHashtag")

FORBIDDEN = [
    re.compile(r"CREATE\s+(TABLE|DATABASE|SCHEMA|INDEX|VIEW|TEMPORARY)", re.IGNORECASE),
    re.compile(r"DROP\s+", re.IGNORECASE),
    re.compile(r"ALTER\s+TABLE", re.IGNORECASE),
    re.compile(r"TRUNCATE", re.IGNORECASE),
    re.compile(r"RENAME\s+TABLE", re.IGNORECASE),
    re.compile(r"alembic|create_all|drop_all|metadata\.create|Base\.metadata|sqlite", re.IGNORECASE),
    # Old parallel tables («users» is now the official Users table, so it is allowed).
    re.compile(
        r"(FROM|JOIN|INTO|UPDATE|TABLE)\s+[`\"]?(groups|tags|submissions|submission_tags|"
        r"media_files|conversation_states|processed_updates|outbox|audit_log|app_settings)\b",
        re.IGNORECASE,
    ),
    # Pre-merge staff table names (case-sensitive: «Posts», «Hashtags» … are the new ones).
    re.compile(
        r"(FROM|JOIN|INTO|UPDATE|TABLE)\s+[`\"]?(Person|EhyaGroup|PersonGroup|Hashtag|Post|PostHashtag)\b"
    ),
]

DDL = re.compile(r"^\s*(CREATE|DROP|ALTER|TRUNCATE|RENAME)\b", re.IGNORECASE)
TABLE_REF = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+[`\"]?([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)


def _executable_files() -> list[Path]:
    files: list[Path] = []
    for folder in ("app", "scripts"):
        files += [p for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    return sorted(files)


def _preflight_allowed(path: Path, body: str) -> str:
    """preflight.py may only mention DDL inside the text it PRINTS for the owner.

    Those strings are the FIX_* constants; every SQL it EXECUTES must be SELECT or
    SHOW GRANTS (checked separately below).
    """
    if path != ROOT / "app" / "preflight.py":
        return body
    return re.sub(r'FIX_[A-Z_]+ = \((?:.|\n)*?\n\)', "", body)


def test_text_scan_of_app_and_scripts() -> None:
    offenders: list[str] = []
    for path in _executable_files():
        try:
            body = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        body = _preflight_allowed(path, body)
        for pattern in FORBIDDEN:
            for match in pattern.finditer(body):
                line = body.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.relative_to(ROOT)}:{line}: {match.group(0)!r}")
    assert offenders == [], "\n".join(offenders)


def test_preflight_executes_only_select_or_show_grants() -> None:
    tree = ast.parse((ROOT / "app" / "preflight.py").read_text(encoding="utf-8"))
    executed: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "text" and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                executed.append(arg.value)
    assert executed
    for sql in executed:
        assert re.match(r"\s*(SELECT|SHOW GRANTS)\b", sql, re.IGNORECASE), sql


def test_orm_tablenames_are_only_the_seven() -> None:
    bad: list[str] = []
    for path in _executable_files():
        if path.suffix != ".py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "__tablename__" for t in node.targets
            ):
                value = node.value.value if isinstance(node.value, ast.Constant) else None
                if value not in ALLOWED_TABLES:
                    bad.append(f"{path.relative_to(ROOT)}: __tablename__ = {value!r}")
    assert bad == [], "\n".join(bad)


def test_recorded_sql_has_no_ddl_and_only_the_seven_tables() -> None:
    """Runs last (file sorts after tests/bot/): checks every SQL the suite executed."""
    statements = [s for s in EXECUTED_SQL if s.strip()]
    ddl = [s for s in statements if DDL.match(s)]
    assert ddl == [], ddl
    tables = {name for s in statements for name in TABLE_REF.findall(s)}
    # information_schema reads come from preflight (read-only metadata).
    tables -= {"information_schema"}
    unknown = {t for t in tables if t not in ALLOWED_TABLES}
    assert unknown == set(), unknown


def test_bot_never_updates_users_except_bale_username() -> None:
    """Users is shared with the staff system: only a NULL BaleUsername may be filled."""
    updates = [s for s in EXECUTED_SQL if re.match(r"\s*UPDATE\s+[`\"]?Users\b", s, re.IGNORECASE)]
    assert updates, "the suite should have exercised the BaleUsername fill"
    for statement in updates:
        assignments = re.search(r"\bSET\b(.*?)\bWHERE\b", statement, re.IGNORECASE | re.DOTALL)
        assert assignments is not None, statement
        columns = {part.split("=")[0].strip() for part in assignments.group(1).split(",")}
        assert columns == {"BaleUsername"}, statement


def test_old_table_names_never_reach_the_database() -> None:
    tables = {name for s in EXECUTED_SQL for name in TABLE_REF.findall(s)}
    assert not tables & set(OLD_TABLE_NAMES)


def test_sql_table_names_only_inside_the_db_layer() -> None:
    """One repository layer: no table name in SQL text outside app/db/."""
    pattern = re.compile(
        r"\b(FROM|JOIN|INTO|UPDATE)\s+[`\"]?(" + "|".join(sorted(ALLOWED_TABLES)) + r")\b"
    )
    offenders = []
    for path in sorted((ROOT / "app").rglob("*.py")):
        if (ROOT / "app" / "db") in path.parents:
            continue
        body = path.read_text(encoding="utf-8")
        offenders += [f"{path.relative_to(ROOT)}: {m.group(0)}" for m in pattern.finditer(body)]
    assert offenders == []

