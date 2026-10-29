"""Shared fixtures.

Tests build a THROW-AWAY MySQL database inside the test machine from the
staff schema (tests/fixtures/schema_appendix_a.sql + section 5-11 changes).
They never connect to the production server. The bot code under test uses
a MySQL user that only has SELECT/INSERT/UPDATE/DELETE, exactly like
production, so any attempt to create a table would fail here too.

Root access for building the test database (defaults work on a local MySQL
installed with apt, run as the OS root user):
    TEST_MYSQL_SOCKET   (default /var/run/mysqld/mysqld.sock)
    TEST_MYSQL_ROOT_USER / TEST_MYSQL_ROOT_PASSWORD
    TEST_MYSQL_HOST / TEST_MYSQL_PORT  (for the bot user; default 127.0.0.1:3306)
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("BALE_BOT_TOKEN", "test-token")
os.environ.setdefault("DATABASE_URL", "mysql+aiomysql://x:y@127.0.0.1/Bale_Archive")

FIXTURES = Path(__file__).parent / "fixtures"

# Every SQL statement the bot code sends through SQLAlchemy during the whole
# test session (RootDB below uses raw PyMySQL and is not recorded).
EXECUTED_SQL: list[str] = []


def _record_sql(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
    EXECUTED_SQL.append(statement)


def _install_sql_recorder() -> None:
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    if not event.contains(Engine, "before_cursor_execute", _record_sql):
        event.listen(Engine, "before_cursor_execute", _record_sql)


_install_sql_recorder()
SCHEMA = FIXTURES / "schema_merged.sql"

BOT_USER = "balebot_test"
BOT_PASSWORD = "test-pass"  # noqa: S105 — local throw-away test user
MAIN_DB = "Bale_Archive"
CHECKED_DB = "Bale_Archive_checked"  # + CHECK (ContentType BETWEEN 1 AND 4)
NO_NOTE_DB = "Bale_Archive_nonote"  # Posts.UserNote missing (incomplete migration)
OLD_NAMES_DB = "Bale_Archive_oldnames"  # old Person table still under its old name

HASHTAGS = [(1, "یادگیری"), (2, "شبکه و منبع"), (3, "محتوایی"), (4, "سند")]
# 10 active units (+1 inactive) so the /register picker needs two pages.
ORG_UNITS = [(1, 1, "ستاد مرکزی", None, 1)] + [
    (i, 2, f"واحد {i:02d}", 1, 1) for i in range(2, 11)
] + [(11, 2, "واحد بسته", 1, 0)]
DELETE_ORDER = ("PostMedia", "PostHashtags", "Posts", "BaleGroupMembers", "BaleGroups", "Users")


def _statements(path: Path) -> list[str]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith("--")]
    return [chunk.strip() for chunk in "\n".join(lines).split(";") if chunk.strip()]


class RootDB:
    """Root connection used only to build/inspect the throw-away test database."""

    def __init__(self) -> None:
        import pymysql

        kwargs: dict[str, Any] = {
            "user": os.environ.get("TEST_MYSQL_ROOT_USER", "root"),
            "password": os.environ.get("TEST_MYSQL_ROOT_PASSWORD", ""),
            "charset": "utf8mb4",
            "autocommit": True,
        }
        socket = os.environ.get("TEST_MYSQL_SOCKET", "/var/run/mysqld/mysqld.sock")
        if os.path.exists(socket):
            kwargs["unix_socket"] = socket
        else:
            kwargs["host"] = os.environ.get("TEST_MYSQL_HOST", "127.0.0.1")
        self.conn = pymysql.connect(**kwargs)

    def execute(self, sql: str, params: Any = None) -> list[tuple[Any, ...]]:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())

    def build(self, name: str, extra: tuple[str, ...] = ()) -> None:
        self.execute(f"DROP DATABASE IF EXISTS `{name}`")
        self.execute(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
        self.execute(f"USE `{name}`")
        for statement in _statements(SCHEMA):
            self.execute(statement)
        for statement in extra:
            self.execute(statement)
        for host in ("localhost", "127.0.0.1"):
            self.execute(f"CREATE USER IF NOT EXISTS '{BOT_USER}'@'{host}' IDENTIFIED BY '{BOT_PASSWORD}'")
            self.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON `{name}`.* TO '{BOT_USER}'@'{host}'")
        self.reset(name)

    def reset(self, name: str = MAIN_DB) -> None:
        self.execute(f"USE `{name}`")
        for table in DELETE_ORDER:
            self.execute(f"DELETE FROM `{table}`")
        self.execute("DELETE FROM Hashtags")
        self.execute("UPDATE OrgUnits SET ParentId = NULL")
        self.execute("DELETE FROM OrgUnits")
        for unit in ORG_UNITS:
            self.execute(
                "INSERT INTO OrgUnits (Id, LevelNo, Name, ParentId, IsActive) VALUES (%s, %s, %s, %s, %s)",
                unit,
            )
        for tag_id, tag_name in HASHTAGS:
            self.execute(
                "INSERT INTO Hashtags (Id, Name, IsActive, Description) VALUES (%s, %s, 1, %s)",
                (tag_id, tag_name, f"توضیح هشتگ {tag_name}"),
            )

    def count(self, table: str, name: str = MAIN_DB) -> int:
        return int(self.execute(f"SELECT COUNT(*) FROM `{name}`.`{table}`")[0][0])

    def rows(self, sql: str, params: Any = None) -> list[tuple[Any, ...]]:
        return self.execute(sql, params)

    def add_user(
        self,
        bale_chat_id: int | None,
        *,
        first: str = "کاربر",
        last: str = "سامانه",
        username: str | None = None,
        bale_username: str | None = None,
        is_active: int = 1,
        is_deleted: int = 0,
        phone: str | None = "09120000000",
    ) -> int:
        """A Users row as the STAFF system would create it (not the bot)."""
        self.execute(
            "INSERT INTO Users (Username, PasswordHash, FirstName, LastName, Phone, BaleChatId, "
            "BaleUsername, IsAdmin, IsActor, MustChangePassword, BaleRequireCode, IsDeleted, "
            "IsActive, NotifyBale, NotifyMeetings, NotifyWeekly, NotifyDelays, FailedLogins, "
            "CreatedAt) VALUES (%s, %s, %s, %s, %s, %s, %s, 1, 1, 0, 0, %s, %s, 1, 1, 1, 1, 0, NOW())",
            (
                username or f"staff_{bale_chat_id}",
                "$2b$12$realhash",
                first,
                last,
                phone,
                bale_chat_id,
                bale_username,
                is_deleted,
                is_active,
            ),
        )
        return int(self.execute("SELECT LAST_INSERT_ID()")[0][0])


def bot_url(name: str = MAIN_DB) -> str:
    host = os.environ.get("TEST_MYSQL_HOST", "127.0.0.1")
    port = os.environ.get("TEST_MYSQL_PORT", "3306")
    return f"mysql+aiomysql://{BOT_USER}:{BOT_PASSWORD}@{host}:{port}/{name}?charset=utf8mb4"


@pytest.fixture(scope="session")
def root_db() -> Iterator[RootDB]:
    try:
        root = RootDB()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no local MySQL for the throw-away test database: {exc}")
    root.build(MAIN_DB)
    root.build(
        CHECKED_DB,
        ("ALTER TABLE Posts ADD CONSTRAINT CK_Posts_ContentType CHECK (ContentType BETWEEN 1 AND 4)",),
    )
    root.build(NO_NOTE_DB, ("ALTER TABLE Posts DROP COLUMN UserNote",))
    root.build(OLD_NAMES_DB, ("CREATE TABLE Person (id INT NOT NULL, PRIMARY KEY (id))",))
    yield root
    for name in (MAIN_DB, CHECKED_DB, NO_NOTE_DB, OLD_NAMES_DB):
        root.execute(f"DROP DATABASE IF EXISTS `{name}`")
    root.conn.close()


@pytest.fixture
def db(root_db: RootDB) -> RootDB:
    """Clean bot tables (and the staff hashtags / org units) before each test."""
    for name in (CHECKED_DB, MAIN_DB):
        root_db.reset(name)
    root_db.execute(f"USE `{MAIN_DB}`")
    return root_db


@pytest.fixture
def fake_bale() -> Any:
    from tests.fakes.fake_bale import FakeBaleServer

    return FakeBaleServer()


@pytest.fixture
async def api(fake_bale: Any) -> AsyncIterator[Any]:
    from app.bale.client import BaleClient
    from app.bale.methods import BaleAPI

    client = BaleClient("test-token", transport=fake_bale.transport())
    yield BaleAPI(client)
    await client.close()
