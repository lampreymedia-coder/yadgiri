"""Picture compression (Pillow) through the real save flow; ensure_membership race."""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

from PIL import Image
from sqlalchemy import text

from app.db import repo
from tests.bot.harness import GROUP, USER, Harness
from tests.conftest import EXECUTED_SQL


def _noisy_jpeg(width: int, height: int, quality: int = 100) -> bytes:
    import random

    rnd = random.Random(1)
    image = Image.new("RGB", (width, height))
    image.putdata([(rnd.randrange(256), x % 256, 128) for x in range(width * height)])
    buffer = io.BytesIO()
    exif = Image.Exif()
    exif[0x010F] = "TestCamera"  # Make
    image.save(buffer, "JPEG", quality=quality, exif=exif.tobytes())
    return buffer.getvalue()


def _smooth(width: int, height: int, fmt: str, **options: object) -> bytes:
    image = Image.linear_gradient("L").resize((width, height)).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, fmt, **options)
    return buffer.getvalue()


def _transparent_png(width: int, height: int) -> bytes:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for x in range(0, width, 7):
        for y in range(0, height, 5):
            image.putpixel((x, y), (x % 256, y % 256, 90, 200))
    buffer = io.BytesIO()
    image.save(buffer, "PNG", compress_level=0)
    return buffer.getvalue()


async def _save_photo(h: Harness, data: bytes, width: int, height: int) -> int:
    h.register_group()
    h.fake.file_bytes["img"] = data
    start = len(EXECUTED_SQL)
    await h.send(GROUP, USER, photo=[{"file_id": "img", "width": width, "height": height, "file_size": len(data)}])
    await h.confirm([1])
    await h.settle()
    return start


def _media_writes(since: int) -> list[str]:
    """Every SQL touching PostMedia after the Post insert (i.e. by compression)."""
    return [
        s
        for s in EXECUTED_SQL[since:]
        if re.search(r"PostMedia", s) and not s.lstrip().upper().startswith(("INSERT", "SELECT"))
    ]


async def test_large_photo_becomes_1920x1440_and_smaller(h: Harness) -> None:
    data = _noisy_jpeg(4000, 3000)
    start = await _save_photo(h, data, 4000, 3000)
    (path, size, width, height, mime), = h.root.rows(
        "SELECT storage_path, file_size, width, height, mime_type FROM PostMedia"
    )
    assert (width, height, mime) == (1920, 1440, "image/jpeg")
    assert size < len(data) and size == Path(path).stat().st_size
    with Image.open(path) as saved:
        assert saved.size == (1920, 1440)
        assert not saved.getexif()  # metadata removed
    assert _media_writes(start) == [
        "UPDATE PostMedia SET storage_path = %s, file_size = %s, width = %s, "
        "height = %s, mime_type = %s WHERE id = %s"
    ]
    entry = next(iter(json.loads((h.settings.data_path / "compression.json").read_text()).values()))
    assert entry["replaced"] is True and entry["new_size"] == size


async def test_small_optimized_photo_is_untouched(h: Harness) -> None:
    data = _smooth(800, 600, "JPEG", quality=70, optimize=True)
    start = await _save_photo(h, data, 800, 600)
    (path, size, width), = h.root.rows("SELECT storage_path, file_size, width FROM PostMedia")
    assert Path(path).read_bytes() == data
    assert (size, width) == (len(data), 800)
    assert _media_writes(start) == []


async def test_transparent_png_stays_png(h: Harness) -> None:
    data = _transparent_png(600, 400)
    start = await _save_photo(h, data, 600, 400)
    (path, mime), = h.root.rows("SELECT storage_path, mime_type FROM PostMedia")
    assert path.endswith(".png") and mime == "image/png"
    with Image.open(path) as saved:
        assert saved.format == "PNG" and saved.mode == "RGBA"
    assert len(_media_writes(start)) == 1


async def test_exif_rotation_applied_before_resize(h: Harness) -> None:
    image = Image.new("RGB", (4000, 3000), (10, 200, 30))
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90° on display
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=100, exif=exif.tobytes())
    data = buffer.getvalue()
    await _save_photo(h, data, 4000, 3000)
    (width, height), = h.root.rows("SELECT width, height FROM PostMedia")
    assert (width, height) == (1440, 1920)


async def test_broken_picture_keeps_original(h: Harness) -> None:
    start = await _save_photo(h, b"not really a jpeg", 10, 10)
    (path,), = h.root.rows("SELECT storage_path FROM PostMedia")
    assert Path(path).read_bytes() == b"not really a jpeg"
    assert _media_writes(start) == []


class _RacingConn:
    """The SELECT sees no row (another message inserts it meanwhile), so INSERT hits the key."""

    def __init__(self, conn) -> None:  # type: ignore[no-untyped-def]
        self.conn = conn

    async def execute(self, statement, params=None):  # type: ignore[no-untyped-def]
        if str(statement).startswith("SELECT 1 FROM PersonGroup"):
            return await self.conn.execute(text("SELECT 1 FROM Hashtag WHERE id = -1"))
        return await self.conn.execute(statement, params)


async def test_ensure_membership_duplicate_insert_is_ignored(h: Harness) -> None:
    group_id = h.register_group()
    h.root.execute("INSERT INTO Person (firstname, bale_user_id, is_active) VALUES ('x', 9, 1)")
    (person_id,), = h.root.rows("SELECT id FROM Person")
    h.root.execute(
        "INSERT INTO PersonGroup (person_id, ehya_group_id) VALUES (%s, %s)", (person_id, group_id)
    )
    async with h.db.tx() as conn:
        await repo.ensure_membership(_RacingConn(conn), person_id, group_id)  # type: ignore[arg-type]
        # the message keeps being processed on the same transaction
        assert await repo.active_hashtags(conn)
        await repo.ensure_membership(conn, person_id, group_id)
    assert h.count("PersonGroup") == 1
