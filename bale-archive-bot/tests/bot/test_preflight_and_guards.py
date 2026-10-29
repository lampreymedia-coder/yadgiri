"""Preflight (merged schema), local files, mapping, and the no-DDL guarantees."""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import pytest

from app.core.offset import OffsetStore
from app.domain.content import ContentType
from app.mapping import media_type, post_content_type
from app.preflight import _grant_is_too_wide, run_preflight
from app.timeutil import tehran_from_unix
from tests.conftest import MAIN_DB, NO_NOTE_DB, OLD_NAMES_DB, RootDB, bot_url

ROOT = Path(__file__).resolve().parents[2]


async def test_preflight_passes_on_prepared_database(db: RootDB) -> None:
    checks = await run_preflight(bot_url(MAIN_DB), expected_db=MAIN_DB)
    assert [c.title for c in checks if not c.ok] == []
    assert not any(c.warning for c in checks)  # zz_old_* and DatabankItems are fine
    titles = "\n".join(c.title for c in checks)
    assert "OrgUnits" in titles and "UserNote" in titles and "UQ_Post_BaleMsg" in titles


async def test_preflight_names_a_missing_column(db: RootDB) -> None:
    checks = await run_preflight(bot_url(NO_NOTE_DB), expected_db=NO_NOTE_DB)
    failed = [c for c in checks if not c.ok]
    assert len(failed) == 1
    assert "Posts.UserNote" in failed[0].title
    assert "اسکریپت ادغام" in failed[0].fix


async def test_preflight_names_missing_tables(db: RootDB) -> None:
    db.execute("CREATE DATABASE IF NOT EXISTS `Bale_Archive_empty`")
    for host in ("localhost", "127.0.0.1"):
        db.execute(f"GRANT SELECT ON `Bale_Archive_empty`.* TO 'balebot_test'@'{host}'")
    try:
        checks = await run_preflight(bot_url("Bale_Archive_empty"), expected_db="Bale_Archive_empty")
        failed = [c for c in checks if not c.ok]
        assert len(failed) == 1
        for table in ("Users", "BaleGroups", "BaleGroupMembers", "Hashtags", "Posts", "PostHashtags", "PostMedia", "OrgUnits"):
            assert table in failed[0].title
    finally:
        db.execute("DROP DATABASE IF EXISTS `Bale_Archive_empty`")


async def test_preflight_warns_about_old_table_names(db: RootDB) -> None:
    checks = await run_preflight(bot_url(OLD_NAMES_DB), expected_db=OLD_NAMES_DB)
    assert all(c.ok for c in checks)  # only a warning, the bot still starts
    warnings = [c for c in checks if c.warning]
    assert len(warnings) == 1 and "Person" in warnings[0].title


async def test_preflight_rejects_wrong_database_name(db: RootDB) -> None:
    checks = await run_preflight(bot_url(MAIN_DB), expected_db="bale_archive")
    assert not checks[0].ok and "bale_archive" in checks[0].title


async def test_preflight_needs_an_active_hashtag_and_org_unit(db: RootDB) -> None:
    db.execute(f"UPDATE `{MAIN_DB}`.Hashtags SET IsActive = 0")
    db.execute(f"UPDATE `{MAIN_DB}`.OrgUnits SET IsActive = 0")
    checks = await run_preflight(bot_url(MAIN_DB), expected_db=MAIN_DB)
    failed = [c.title for c in checks if not c.ok]
    assert len(failed) == 2
    assert "Hashtags" in failed[0] and "OrgUnits" in failed[1]


async def test_preflight_needs_unique_bale_chat_id(db: RootDB) -> None:
    db.execute("CREATE DATABASE `Bale_Archive_nouq` CHARACTER SET utf8mb4")
    try:
        db.execute("USE `Bale_Archive_nouq`")
        from tests.conftest import SCHEMA, _statements

        for statement in _statements(SCHEMA):
            db.execute(statement.replace("UNIQUE KEY UQ_Users_BaleChatId", "KEY IX_Users_BaleChatId"))
        for host in ("localhost", "127.0.0.1"):
            db.execute(f"GRANT SELECT ON `Bale_Archive_nouq`.* TO 'balebot_test'@'{host}'")
        checks = await run_preflight(bot_url("Bale_Archive_nouq"), expected_db="Bale_Archive_nouq")
        failed = [c.title for c in checks if not c.ok]
        assert any("Users(BaleChatId)" in title for title in failed)
    finally:
        db.execute("DROP DATABASE IF EXISTS `Bale_Archive_nouq`")
        db.execute(f"USE `{MAIN_DB}`")


async def test_preflight_flags_a_user_that_can_create_tables(db: RootDB) -> None:
    db.execute("CREATE USER IF NOT EXISTS 'wide_test'@'127.0.0.1' IDENTIFIED BY 'x'")
    db.execute("CREATE USER IF NOT EXISTS 'wide_test'@'localhost' IDENTIFIED BY 'x'")
    for host in ("127.0.0.1", "localhost"):
        db.execute(f"GRANT ALL PRIVILEGES ON `{MAIN_DB}`.* TO 'wide_test'@'{host}'")
    url = bot_url(MAIN_DB).replace("balebot_test:test-pass", "wide_test:x")
    try:
        checks = await run_preflight(url, expected_db=MAIN_DB)
        failed = [c for c in checks if not c.ok]
        assert len(failed) == 1 and "REVOKE ALL PRIVILEGES" in failed[0].fix
    finally:
        db.execute("DROP USER IF EXISTS 'wide_test'@'127.0.0.1'")
        db.execute("DROP USER IF EXISTS 'wide_test'@'localhost'")


async def test_preflight_reports_unreachable_database() -> None:
    checks = await run_preflight("mysql+aiomysql://nobody:x@127.0.0.1:1/Bale_Archive")
    assert len(checks) == 1 and not checks[0].ok


def test_grant_parser() -> None:
    assert not _grant_is_too_wide("GRANT USAGE ON *.* TO `b`@`localhost`", "Bale_Archive")
    assert not _grant_is_too_wide(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON `Bale_Archive`.* TO `b`@`localhost`", "Bale_Archive"
    )
    assert _grant_is_too_wide("GRANT SELECT, CREATE ON `Bale_Archive`.* TO `b`@`localhost`", "Bale_Archive")
    assert _grant_is_too_wide("GRANT ALL PRIVILEGES ON *.* TO `root`@`localhost`", "Bale_Archive")
    assert not _grant_is_too_wide("GRANT ALL PRIVILEGES ON `other`.* TO `b`@`%`", "Bale_Archive")


def test_bot_database_user_cannot_create_tables(db: RootDB) -> None:
    """Negative test run straight through PyMySQL (not SQLAlchemy), so the guard's
    SQL recorder only ever sees what the bot code itself executes."""
    import os

    import pymysql

    conn = pymysql.connect(
        host=os.environ.get("TEST_MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("TEST_MYSQL_PORT", "3306")),
        user="balebot_test",
        password="test-pass",  # noqa: S106 — local throw-away test user
        database=MAIN_DB,
    )
    try:
        with conn.cursor() as cur, pytest.raises(pymysql.err.OperationalError, match="denied"):
            cur.execute("CREATE TABLE should_not_exist (id INT)")
    finally:
        conn.close()
    assert db.execute(
        "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_NAME = 'should_not_exist'"
    ) == [(0,)]


def test_running_bot_code_has_no_table_creation() -> None:
    """Every module the bot loads (plus the Linux scripts) is free of DDL and migrations."""
    import app.main  # noqa: F401 — load the whole running program

    files = sorted(
        Path(module.__file__)
        for name, module in list(sys.modules.items())
        if (name == "app" or name.startswith("app.")) and getattr(module, "__file__", None)
    )
    files += [ROOT / "scripts" / name for name in ("preflight.py", "deploy.sh", "install.sh", "run.sh", "backup.sh")]
    files += [ROOT / "deploy" / "balebot.service"]
    forbidden = re.compile(
        r"create_all|alembic|CREATE\s+(TABLE|DATABASE|SCHEMA|INDEX)|DROP\s+(TABLE|DATABASE)|ALTER\s+TABLE",
        re.IGNORECASE,
    )
    offenders = []
    for path in files:
        body = path.read_text(encoding="utf-8")
        if path.name == "preflight.py" and path.parent.name == "app":
            # The ALTER commands appear only as text printed for the owner.
            body = re.sub(r'FIX_[A-Z_]+ = \((?:.|\n)*?\n\)', "", body)
        for match in forbidden.finditer(body):
            offenders.append(f"{path.relative_to(ROOT)}: {match.group(0)}")
    assert offenders == []
    assert any(p.name == "archive.py" for p in files)


def test_offset_file_roundtrip(tmp_path: Path) -> None:
    store = OffsetStore(tmp_path / "sub" / "offset")
    assert store.load() is None
    store.save(1234)
    assert OffsetStore(tmp_path / "sub" / "offset").load() == 1234


def test_mapping_codes() -> None:
    assert post_content_type([ContentType.TEXT]) == 1
    assert post_content_type([ContentType.LINK]) == 1
    assert post_content_type([ContentType.IMAGE, ContentType.IMAGE]) == 2
    assert post_content_type([ContentType.IMAGE, ContentType.VIDEO]) == 3
    assert post_content_type([ContentType.ANIMATION]) == 3
    assert post_content_type([ContentType.VOICE]) == 4
    assert post_content_type([ContentType.DOCUMENT]) == 5
    assert post_content_type([ContentType.STICKER]) is None
    assert media_type(ContentType.IMAGE) == 1
    assert media_type(ContentType.VIDEO) == 2
    assert media_type(ContentType.AUDIO) == 3
    assert media_type(ContentType.DOCUMENT) == 4


def test_tehran_time() -> None:
    assert tehran_from_unix(1_758_880_800) == datetime(2025, 9, 26, 13, 30)
