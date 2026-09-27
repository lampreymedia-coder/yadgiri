"""2-3: owner = first ADMIN_USER_IDS id; only the owner manages admins (admins.json only)."""

from __future__ import annotations

import json

from app.core.admins import AdminStore
from tests.bot.harness import ADMIN_ID, GROUP, USER, Harness

OWNER = {"id": ADMIN_ID, "is_bot": False, "first_name": "مالک"}
HELPER = {"id": 444, "is_bot": False, "first_name": "کمک"}


def _admins_file(h: Harness) -> dict:  # type: ignore[type-arg]
    return json.loads(h.settings.admins_file.read_text())


def test_owner_is_first_env_id(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = AdminStore(tmp_path / "a.json", [7, 8])
    assert store.owner == 7 and store.is_owner(7) and not store.is_owner(8)


async def test_owner_adds_by_id_and_regular_admin_cannot(h: Harness) -> None:
    await h.private(OWNER, "/addadmin 444")
    assert h.ctx.is_admin(444)
    assert _admins_file(h)["admins"] == [444]
    await h.private(HELPER, "/addadmin 555")
    await h.private(HELPER, "/removeadmin 444")
    assert not h.ctx.is_admin(555) and h.ctx.is_admin(444)
    assert "فقط مالک" in h.texts_to(444)[-1]


async def test_add_admin_by_typed_id_and_by_forward(h: Harness) -> None:
    await h.press(OWNER, "pa", "aid")
    await h.private(OWNER, "۴۴۴")
    assert h.ctx.is_admin(444)
    await h.press(OWNER, "pa", "afw")
    await h.send(
        {"id": ADMIN_ID, "type": "private"},
        OWNER,
        text="سلام",
        forward_from={"id": 555, "is_bot": False, "first_name": "سعید"},
    )
    assert h.ctx.is_admin(555)


async def test_add_admin_by_picking_from_person(h: Harness) -> None:
    h.register_group()
    await h.text(GROUP, USER, "سلام")  # USER becomes a Person row
    await h.press(OWNER, "pa", "apk")
    labels = h.fake.markup_labels(h.fake.last_markup(ADMIN_ID))
    assert any("علی" in label for label in labels)
    await h.press(OWNER, "pa", "apa", str(USER["id"]))
    assert h.ctx.is_admin(USER["id"])
    assert h.count("Person") == 1  # nothing written to the database for admins


async def test_transfer_ownership(h: Harness) -> None:
    await h.private(OWNER, "/addadmin 444")
    await h.press(OWNER, "pa", "aox", "444")
    assert h.ctx.admins.owner == 444
    assert h.ctx.is_admin(ADMIN_ID)  # old owner stays admin
    assert _admins_file(h)["owner"] == 444
    await h.private(OWNER, "/addadmin 999")
    assert not h.ctx.is_admin(999)  # no longer the owner
    reloaded = AdminStore(h.settings.admins_file, h.settings.admin_user_ids)
    assert reloaded.owner == 444


async def test_regular_admin_cannot_use_owner_buttons(h: Harness) -> None:
    await h.private(OWNER, "/addadmin 444")
    await h.press(HELPER, "pa", "apa", "777")
    await h.press(HELPER, "pa", "aox", "444")
    assert not h.ctx.is_admin(777)
    assert h.ctx.admins.owner == ADMIN_ID


async def test_id_command(h: Harness) -> None:
    await h.private(USER, "/id")
    assert str(USER["id"]) in h.texts_to(USER["id"])[-1]
