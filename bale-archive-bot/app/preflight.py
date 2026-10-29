"""Read-only startup checks for the merged schema (CLAUDE-MERGE-SCHEMA.md §3.8).

Runs as the bot's own MySQL user and only reads (information_schema,
SHOW GRANTS, two COUNTs). It never fixes anything: a failed check names the
exact table/column that is missing so the staff migration can be completed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.config import EXPECTED_DATABASE
from app.db import repo
from app.db.schema import (
    AUTO_INCREMENT,
    BOT_TABLES,
    OLD_TABLES,
    REQUIRED_COLUMNS,
    REQUIRED_UNIQUE,
    UNIQUE_NAMES,
)
from app.db.session import ensure_utf8mb4

ALLOWED_PRIVILEGES = {"SELECT", "INSERT", "UPDATE", "DELETE", "USAGE"}
STAFF_FIX = "باید در اسکریپت ادغام نیرو (با root) اضافه شود؛ ربات خودش ساختار دیتابیس را تغییر نمی‌دهد."


@dataclass(slots=True)
class Check:
    ok: bool
    title: str
    fix: str = ""
    warning: bool = False  # shown, but does not stop the bot


def _grant_is_too_wide(line: str, database: str) -> bool:
    """True when one SHOW GRANTS line gives more than SELECT/INSERT/UPDATE/DELETE here."""
    match = re.match(r"GRANT\s+(.+?)\s+ON\s+(\S+)\s+TO\s", line, re.IGNORECASE)
    if match is None:
        return False  # e.g. role grants "GRANT `role` TO ..."
    privileges, scope = match.group(1), match.group(2)
    scope_db = scope.split(".", 1)[0].strip("`'\"")
    if scope_db not in ("*", database):
        return False
    privileges = re.sub(r"\([^)]*\)", "", privileges)  # column lists
    names = {p.strip().upper() for p in privileges.split(",") if p.strip()}
    return any(name not in ALLOWED_PRIVILEGES for name in names)


async def _names(conn: AsyncConnection, sql: str, params: dict[str, object]) -> list[tuple[str, ...]]:
    return [tuple(str(v) for v in row) for row in await conn.execute(text(sql), params)]


async def _run_checks(conn: AsyncConnection, expected_db: str) -> list[Check]:
    checks: list[Check] = []
    current = (await conn.execute(text("SELECT DATABASE()"))).scalar()
    if current != expected_db:
        checks.append(
            Check(
                False,
                f"دیتابیس باید دقیقاً «{expected_db}» باشد (با حروف بزرگ و کوچک)؛ الان «{current}» است.",
                f"در فایل .env آدرس DATABASE_URL را به .../{expected_db}?charset=utf8mb4 درست کنید.",
            )
        )
        return checks
    checks.append(Check(True, f"دیتابیس {expected_db} در دسترس است."))
    db = {"db": expected_db}

    present = {
        row[0]
        for row in await _names(
            conn, "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = :db", db
        )
    }
    missing_tables = [name for name in BOT_TABLES if name not in present]
    if missing_tables:
        checks.append(
            Check(
                False,
                "این جدول‌ها پیدا نشدند (یا کاربر ربات به آن‌ها دسترسی ندارد): "
                + "، ".join(missing_tables),
                STAFF_FIX
                + "\nGRANT SELECT, INSERT, UPDATE, DELETE ON Bale_Archive.* TO 'balebot'@'localhost';",
            )
        )
        return checks
    checks.append(Check(True, f"هر {len(BOT_TABLES)} جدول ربات وجود دارند: " + "، ".join(BOT_TABLES)))

    columns = await _names(
        conn,
        "SELECT TABLE_NAME, COLUMN_NAME, EXTRA FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = :db",
        db,
    )
    have = {(table, column) for table, column, _ in columns}
    extra = {(table, column): flags for table, column, flags in columns}
    missing_columns = [
        f"{table}.{column}"
        for table, wanted in REQUIRED_COLUMNS.items()
        for column in wanted
        if (table, column) not in have
    ]
    if missing_columns:
        checks.append(
            Check(False, "این ستون‌ها پیدا نشدند: " + "، ".join(missing_columns), STAFF_FIX)
        )
        return checks
    checks.append(Check(True, "همه‌ی ستون‌های لازم هستند (از جمله Posts.UserNote و Posts.Source)."))

    not_auto = [
        f"{table}.{column}"
        for table, column in AUTO_INCREMENT
        if "auto_increment" not in extra.get((table, column), "").lower()
    ]
    if not_auto:
        checks.append(
            Check(False, "این شناسه‌ها خودکار (AUTO_INCREMENT) نیستند: " + "، ".join(not_auto), STAFF_FIX)
        )
    else:
        checks.append(Check(True, "شناسه‌های Users/BaleGroups/Posts/PostMedia خودکار هستند."))

    index_rows = await _names(
        conn,
        "SELECT TABLE_NAME, INDEX_NAME, COLUMN_NAME FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = :db AND NON_UNIQUE = 0 ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX",
        db,
    )
    unique_sets: dict[tuple[str, str], list[str]] = {}
    for table, index, column in index_rows:
        unique_sets.setdefault((table, index), []).append(column)
    missing_unique = []
    for table, cols in REQUIRED_UNIQUE:
        found = any(t == table and set(c) == set(cols) for (t, _), c in unique_sets.items())
        if not found:
            label = UNIQUE_NAMES.get((table, cols), "UNIQUE")
            missing_unique.append(f"{label} روی {table}({', '.join(cols)})")
    if missing_unique:
        checks.append(Check(False, "این یکتاها نیستند: " + "، ".join(missing_unique), STAFF_FIX))
    else:
        checks.append(
            Check(True, "یکتاها درست‌اند (UQ_Post_BaleMsg، Users.BaleChatId، Users.Username، …).")
        )

    grants = [str(row[0]) for row in await conn.execute(text("SHOW GRANTS FOR CURRENT_USER()"))]
    too_wide = [line for line in grants if _grant_is_too_wide(line, expected_db)]
    if too_wide:
        current_user = str((await conn.execute(text("SELECT CURRENT_USER()"))).scalar())
        name, _, host = current_user.partition("@")
        user = f"'{name}'@'{host or 'localhost'}'"
        checks.append(
            Check(
                False,
                "کاربر دیتابیس ربات بیش از حد دسترسی دارد (می‌تواند جدول بسازد یا تغییر دهد):\n   "
                + "\n   ".join(too_wide),
                f"REVOKE ALL PRIVILEGES, GRANT OPTION FROM {user};\n"
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON Bale_Archive.* TO {user};",
            )
        )
    else:
        checks.append(
            Check(True, "کاربر ربات نمی‌تواند جدول بسازد (فقط SELECT, INSERT, UPDATE, DELETE).")
        )

    hashtags = await repo.count_active_hashtags(conn)
    if hashtags:
        checks.append(Check(True, f"{hashtags} هشتگ فعال در Hashtags هست."))
    else:
        checks.append(
            Check(False, "هیچ هشتگ فعالی در جدول Hashtags نیست (IsActive = 1).", STAFF_FIX)
        )
    units = await repo.count_active_org_units(conn)
    if units:
        checks.append(Check(True, f"{units} واحد سازمانی فعال در OrgUnits هست."))
    else:
        checks.append(
            Check(False, "هیچ واحد سازمانی فعالی در جدول OrgUnits نیست (IsActive = 1).", STAFF_FIX)
        )

    leftovers = [name for name in OLD_TABLES if name in present]
    if leftovers:
        checks.append(
            Check(
                True,
                "هشدار: جدول‌های قدیمی هنوز با نام قبلی هستند: "
                + "، ".join(leftovers)
                + " — ربات از آن‌ها استفاده نمی‌کند (باید zz_old_ شوند).",
                warning=True,
            )
        )
    return checks


async def run_preflight(database_url: str, expected_db: str = EXPECTED_DATABASE) -> list[Check]:
    url = ensure_utf8mb4(database_url)
    engine = create_async_engine(url, pool_size=1, max_overflow=0)
    try:
        async with engine.connect() as conn:
            return await _run_checks(conn, expected_db)
    except Exception as exc:  # noqa: BLE001 — shown to the owner as plain text
        host = make_url(url).host
        return [
            Check(
                False,
                f"اتصال به MySQL ممکن نشد ({host}): {exc}",
                "بررسی کنید MySQL روشن است (systemctl status mysql) و نام کاربری/رمز در .env درست است.",
            )
        ]
    finally:
        await engine.dispose()


def format_report(checks: list[Check]) -> str:
    lines = ["بررسی پیش از شروع (preflight):"]
    for check in checks:
        mark = "⚠️ " if check.warning else ("✅ " if check.ok else "❌ ")
        lines.append(mark + check.title)
        if not check.ok and check.fix:
            lines.append("   کاری که باید انجام شود:")
            lines.extend("   " + part for part in check.fix.splitlines())
    if all(check.ok for check in checks):
        lines.append("همه چیز درست است.")
    else:
        lines.append("ربات تا درست شدن موارد ❌ روشن نمی‌شود. ربات خودش چیزی را تغییر نمی‌دهد.")
    return "\n".join(lines)
