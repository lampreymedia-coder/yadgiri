"""Local disk Storage backend."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.db.models import MediaFile
from app.domain.media import LocalStorage, storage_key_for


@pytest.mark.asyncio
async def test_local_storage_writes_and_closes_handle(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path)
    stored = await store.put("ab/hello.txt", "سلام".encode(), "text/plain")
    dest = Path(stored)
    assert dest.is_file()
    assert dest.read_text(encoding="utf-8") == "سلام"
    assert dest.is_relative_to(tmp_path.resolve())


def test_storage_key_is_short_and_pathlib() -> None:
    media = MediaFile(submission_id=1, bale_file_id="f1", file_name="report.PDF")
    key = storage_key_for(media)
    parts = Path(key).parts
    assert len(parts) == 2
    assert parts[1].endswith(".pdf")
    assert len(key) < 80
