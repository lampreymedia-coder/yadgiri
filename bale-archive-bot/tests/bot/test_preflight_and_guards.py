"""Preflight (section 5-11), local files, mapping, and the no-DDL guarantees."""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import text

from app.core.offset import OffsetStore
from app.domain.content import ContentType
from app.mapping import media_type, post_content_type
from app.preflight import _grant_is_too_wide, run_preflight
from app.timeutil import tehran_from_unix
from tests.conftest import MAIN_DB, OLD_CHECK_DB, ORIGINAL_DB, RootDB, bot_url

ROOT = Path(__file__).resolve().parents[2]


async def test_preflight_passes_on_prepared_database(db: RootDB) -> None:
    checks = await run_preflight(bot_url(MAIN_DB), expected_db=MAIN_DB)
    assert [c.title for c in checks if not c.ok] == []
    assert len(checks) == 7


async def test_preflight_names_the_missing_alter_commands(db: RootDB) -> None:
    checks = await run_preflight(bot_url(ORIGINAL_DB), expected_db=ORIGINAL_DB)
    failed = [c for c in checks if not c.ok]
    fixes = "\n".join(c.fix for c in failed)
    assert len(failed) == 3
    assert "CHECK (content_type BETWEEN 1 AND 5)" in fixes
    assert "CHECK (media_type BETWEEN 1 AND 4)" in fixes
    assert "MODIFY id INT NOT NULL AUTO_INCREMENT" in fixes


async def test_preflight_check_only_constraints(db: RootDB) -> None:
    checks = await run_preflight(bot_url(OLD_CHECK_DB), expected_db=OLD_CHECK_DB)
    assert len([c for c in checks if not c.ok]) == 2


async def test_preflight_rejects_wrong_database_name(db: RootDB) -> None:
    checks = await run_preflight(bot_url(MAIN_DB), expected_db="bale_archive")
    assert not checks[0].ok and "bale_archive" in checks[0].title


async def test_preflight_needs_an_active_hashtag(db: RootDB) -> None:
    db.execute(f"UPDATE `{MAIN_DB}`.Hashtag SET is_active = 0")
    checks = await run_preflight(bot_url(MAIN_DB), expected_db=MAIN_DB)
    assert [c.fix for c in checks if not c.ok] == [
        "INSERT INTO Hashtag (name, is_active) VALUES ('یادگیری', 1);"
    ]


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


async def test_bot_database_user_cannot_create_tables(db: RootDB) -> None:
    from app.db.session import Database

    database = Database(bot_url(MAIN_DB))
    try:
        with pytest.raises(Exception, match="denied"):
            async with database.tx() as conn:
                await conn.execute(text("CREATE TABLE should_not_exist (id INT)"))
    finally:
        await database.dispose()
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
