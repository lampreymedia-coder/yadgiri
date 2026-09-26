"""Read-only startup checks (CLAUDE-BOT-FIX.md section 5-11).

Runs as the bot's own MySQL user and only reads (information_schema,
SHOW GRANTS, one COUNT). It never fixes anything: when a check fails it
prints the exact command the owner has to run as MySQL root.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.config import EXPECTED_DATABASE
from app.db.session import ensure_utf8mb4

BOT_TABLES = ("Person", "EhyaGroup", "Hashtag", "PersonGroup", "Post", "PostHashtag", "PostMedia")
ALLOWED_PRIVILEGES = {"SELECT", "INSERT", "UPDATE", "DELETE", "USAGE"}

FIX_CONTENT_TYPE = (
    "ALTER TABLE Post DROP CHECK CK_Post_content_type;\n"
    "ALTER TABLE Post ADD CONSTRAINT CK_Post_content_type CHECK (content_type BETWEEN 1 AND 5);"
)
FIX_MEDIA_TYPE = (
    "ALTER TABLE PostMedia DROP CHECK CK_PostMedia_media_type;\n"
    "ALTER TABLE PostMedia ADD CONSTRAINT CK_PostMedia_media_type CHECK (media_type BETWEEN 1 AND 4);"
)
FIX_PERSON_ID = (
    "SET FOREIGN_KEY_CHECKS=0; ALTER TABLE Person MODIFY id INT NOT NULL AUTO_INCREMENT; "
    "SET FOREIGN_KEY_CHECKS=1;"
)


@dataclass(slots=True)
class Check:
    ok: bool
    title: str
    fix: str = ""


def _max_allowed(clause: str) -> int | None:
    numbers = [int(n) for n in re.findall(r"(?<![\w`])\d+(?![\w`])", clause)]
    return max(numbers) if numbers else None


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

    rows = await conn.execute(
        text("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = :db"),
        {"db": expected_db},
    )
    present = {str(row[0]) for row in rows}
    missing = [name for name in BOT_TABLES if name not in present]
    if missing:
        checks.append(
            Check(
                False,
                "این جدول‌ها پیدا نشدند یا کاربر balebot به آن‌ها دسترسی ندارد: "
                + "، ".join(missing),
                "اسکیمای نیروی انسانی را (با root) روی Bale_Archive برگردانید و دسترسی بدهید:\n"
                "GRANT SELECT, INSERT, UPDATE, DELETE ON Bale_Archive.* TO 'balebot'@'localhost';",
            )
        )
        return checks
    checks.append(Check(True, "هر ۷ جدول ربات وجود دارند."))

    constraints = await conn.execute(
        text(
            "SELECT CONSTRAINT_NAME, CHECK_CLAUSE FROM information_schema.CHECK_CONSTRAINTS "
            "WHERE CONSTRAINT_SCHEMA = :db AND CONSTRAINT_NAME IN "
            "('CK_Post_content_type', 'CK_PostMedia_media_type')"
        ),
        {"db": expected_db},
    )
    clauses = {str(row[0]): str(row[1]) for row in constraints}
    for name, needed, fix, label in (
        ("CK_Post_content_type", 5, FIX_CONTENT_TYPE, "content_type"),
        ("CK_PostMedia_media_type", 4, FIX_MEDIA_TYPE, "media_type"),
    ):
        clause = clauses.get(name)
        top = _max_allowed(clause) if clause is not None else None
        if clause is None or (top is not None and top >= needed):
            checks.append(Check(True, f"قید {label} تا {needed} باز است."))
        else:
            checks.append(
                Check(
                    False,
                    f"قید {label} هنوز فقط تا {top} اجازه می‌دهد (باید تا {needed} باشد).",
                    fix,
                )
            )

    extra = (
        await conn.execute(
            text(
                "SELECT EXTRA FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = :db "
                "AND TABLE_NAME = 'Person' AND COLUMN_NAME = 'id'"
            ),
            {"db": expected_db},
        )
    ).scalar()
    if extra and "auto_increment" in str(extra).lower():
        checks.append(Check(True, "Person.id خودکار (AUTO_INCREMENT) است."))
    else:
        checks.append(Check(False, "Person.id هنوز خودکار (AUTO_INCREMENT) نیست.", FIX_PERSON_ID))

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

    active = int(
        (await conn.execute(text("SELECT COUNT(*) FROM Hashtag WHERE is_active = 1"))).scalar_one()
    )
    if active:
        checks.append(Check(True, f"{active} هشتگ فعال هست."))
    else:
        checks.append(
            Check(
                False,
                "هیچ هشتگ فعالی در جدول Hashtag نیست.",
                "INSERT INTO Hashtag (name, is_active) VALUES ('یادگیری', 1);",
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
        lines.append(("✅ " if check.ok else "❌ ") + check.title)
        if not check.ok and check.fix:
            lines.append("   دستوری که باید (با root در MySQL) اجرا کنید:")
            lines.extend("   " + part for part in check.fix.splitlines())
    if all(check.ok for check in checks):
        lines.append("همه چیز درست است.")
    else:
        lines.append("ربات تا درست شدن موارد ❌ روشن نمی‌شود. ربات خودش چیزی را تغییر نمی‌دهد.")
    return "\n".join(lines)
