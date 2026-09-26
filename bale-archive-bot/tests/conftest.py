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
SCHEMA = FIXTURES / "schema_appendix_a.sql"
SCHEMA_5_11 = FIXTURES / "schema_5_11.sql"

BOT_USER = "balebot_test"
BOT_PASSWORD = "test-pass"  # noqa: S105 — local throw-away test user
MAIN_DB = "Bale_Archive"
OLD_CHECK_DB = "Bale_Archive_oldcheck"  # CHECKs still 1-4 / 1-3, Person.id automatic
ORIGINAL_DB = "Bale_Archive_original"  # appendix A exactly, nothing changed

HASHTAGS = [(1, "یادگیری"), (2, "شبکه و منبع"), (3, "محتوایی"), (4, "سند")]
BOT_TABLES_DELETE_ORDER = ("PostMedia", "PostHashtag", "Post", "PersonGroup", "Person", "EhyaGroup")


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

    def build(self, name: str, *, apply_5_11: bool, auto_person_id: bool) -> None:
        self.execute(f"DROP DATABASE IF EXISTS `{name}`")
        self.execute(
            f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        self.execute(f"USE `{name}`")
        for statement in _statements(SCHEMA):
            self.execute(statement)
        if apply_5_11:
            for statement in _statements(SCHEMA_5_11):
                self.execute(statement)
        elif auto_person_id:
            self.execute("SET FOREIGN_KEY_CHECKS=0")
            self.execute("ALTER TABLE Person MODIFY id INT NOT NULL AUTO_INCREMENT")
            self.execute("SET FOREIGN_KEY_CHECKS=1")
        for host in ("localhost", "127.0.0.1"):
            self.execute(f"CREATE USER IF NOT EXISTS '{BOT_USER}'@'{host}' IDENTIFIED BY '{BOT_PASSWORD}'")
            self.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON `{name}`.* TO '{BOT_USER}'@'{host}'")
        self.reset(name)

    def reset(self, name: str = MAIN_DB) -> None:
        self.execute(f"USE `{name}`")
        for table in BOT_TABLES_DELETE_ORDER:
            self.execute(f"DELETE FROM `{table}`")
        self.execute("DELETE FROM Hashtag")
        for tag_id, tag_name in HASHTAGS:
            self.execute("INSERT INTO Hashtag (id, name, is_active) VALUES (%s, %s, 1)", (tag_id, tag_name))

    def count(self, table: str, name: str = MAIN_DB) -> int:
        return int(self.execute(f"SELECT COUNT(*) FROM `{name}`.`{table}`")[0][0])

    def rows(self, sql: str, params: Any = None) -> list[tuple[Any, ...]]:
        return self.execute(sql, params)


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
    root.build(MAIN_DB, apply_5_11=True, auto_person_id=True)
    root.build(OLD_CHECK_DB, apply_5_11=False, auto_person_id=True)
    root.build(ORIGINAL_DB, apply_5_11=False, auto_person_id=False)
    yield root
    for name in (MAIN_DB, OLD_CHECK_DB, ORIGINAL_DB):
        root.execute(f"DROP DATABASE IF EXISTS `{name}`")
    root.conn.close()


@pytest.fixture
def db(root_db: RootDB) -> RootDB:
    """Clean bot tables (and the 4 staff hashtags) before each test."""
    for name in (OLD_CHECK_DB, MAIN_DB):
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
