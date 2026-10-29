"""/register, /unregister, admins file, reports."""

from __future__ import annotations

from app.core.admins import AdminStore, RemoveResult
from tests.bot.harness import ADMIN_ID, ARCHIVE, GROUP, GROUP_ID, USER, Harness

ADMIN = {"id": ADMIN_ID, "is_bot": False, "first_name": "مدیر"}


def _buttons(h: Harness) -> list[tuple[str, str]]:
    markup = h.fake.last_markup(GROUP_ID)
    assert markup is not None
    return [(b["text"], b["callback_data"]) for row in markup["inline_keyboard"] for b in row]


def _unit_button(h: Harness, unit_name: str) -> str:
    return next(data for label, data in _buttons(h) if label.startswith(unit_name))


async def test_register_lists_org_units_paged_and_adds_one_row(h: Harness) -> None:
    await h.text(GROUP, ADMIN, "/register")
    first_page = _buttons(h)
    names = [label for label, _ in first_page if "سطح" in label]
    # 10 active units (the inactive «واحد بسته» is hidden), 8 per page, LevelNo then Name
    assert len(names) == 8 and names[0].startswith("ستاد مرکزی") and names[1].startswith("واحد 02")
    assert all("واحد بسته" not in label for label, _ in first_page)
    assert all(len(data.encode()) <= 64 and data.isascii() for _, data in first_page)
    nxt = next(data for label, data in first_page if label == "▶️")
    _, action, sid, arg = nxt.split("|")
    await h.press(ADMIN, action, sid, arg, chat_id=GROUP_ID, message_id=1)
    second = [label for label, _ in _buttons(h) if "سطح" in label]
    assert [n.split(" (")[0] for n in second] == ["واحد 09", "واحد 10"]

    assert h.count("BaleGroups") == 0
    _, action, sid, arg = _unit_button(h, "واحد 10").split("|")
    assert sid == str(GROUP_ID) and arg == "10"
    await h.press(ADMIN, action, sid, arg, chat_id=GROUP_ID, message_id=1)
    rows = h.root.rows(
        "SELECT BaleChatId, Title, OrgUnitId, IsActive, CreatedAt IS NOT NULL FROM BaleGroups"
    )
    assert rows == [(GROUP_ID, "گروه رصد", 10, 1, 1)]
    # the group now works
    await h.text(GROUP, USER, "متن")
    assert len(h.ctx.wizards) == 1


async def test_register_unit_tap_without_message_field(h: Harness) -> None:
    """Some Bale callbacks carry no ``message``; the group id comes from callback_data."""
    await h.text(GROUP, ADMIN, "/register")
    data = _unit_button(h, "واحد 03")
    await h.feed({"callback_query": {"id": "cq-x", "from": ADMIN, "data": data}})
    assert h.root.rows("SELECT BaleChatId, OrgUnitId FROM BaleGroups") == [(GROUP_ID, 3)]


async def test_inactive_unit_is_refused(h: Harness) -> None:
    await h.text(GROUP, ADMIN, "/register")
    await h.press(ADMIN, "ou", str(GROUP_ID), "11", chat_id=GROUP_ID)
    assert h.count("BaleGroups") == 0


async def test_non_admin_register_is_silent(h: Harness) -> None:
    await h.text(GROUP, USER, "/register")
    await h.press(USER, "ou", str(GROUP_ID), "2", chat_id=GROUP_ID)
    assert h.count("BaleGroups") == 0
    assert h.fake.calls_for("sendMessage") == []


async def test_unregister_keeps_the_row_and_register_reactivates(h: Harness) -> None:
    h.register_group(org_unit=3)
    h.root.execute("UPDATE BaleGroups SET Title = %s", ("نام نیرو",))
    await h.text(GROUP, ADMIN, "/unregister")
    assert h.root.rows("SELECT IsActive FROM BaleGroups") == [(0,)]
    await h.text(GROUP, USER, "متن")
    assert len(h.ctx.wizards) == 0
    # registering again: only IsActive=1 and OrgUnitId change (Title stays as staff set it)
    await h.text(GROUP, ADMIN, "/register")
    await h.press(ADMIN, "ou", str(GROUP_ID), "5", chat_id=GROUP_ID)
    assert h.root.rows("SELECT OrgUnitId, IsActive, Title FROM BaleGroups") == [(5, 1, "نام نیرو")]
    assert h.count("BaleGroups") == 1


async def test_archive_group_cannot_be_registered(h: Harness) -> None:
    await h.text(ARCHIVE, ADMIN, "/register")
    await h.press(ADMIN, "ou", str(ARCHIVE["id"]), "1", chat_id=ARCHIVE["id"])
    assert h.count("BaleGroups") == 0


async def test_stats_report(h: Harness) -> None:
    h.register_group()
    await h.text(GROUP, USER, "اولی")
    await h.confirm([1, 2])
    await h.send(GROUP, USER, voice={"file_id": "v", "file_size": 10})
    await h.confirm([1])
    await h.private(ADMIN, "/stats")
    report = h.texts_to(ADMIN_ID)[-1]
    assert "کل ثبت‌ها: ۲" in report
    assert "علی رضایی (@ali) — ۲" in report
    assert "پردیتاترین هشتگ: #یادگیری (۲)" in report
    assert "#شبکه_و_منبع: ۱" in report
    assert "متن: ۱" in report and "صوت: ۱" in report
    assert "گروه رصد: ۲" in report


async def test_stats_is_admin_only(h: Harness) -> None:
    await h.private(USER, "/stats")
    assert "کل ثبت‌ها" not in "".join(h.texts_to(USER["id"]))


async def test_add_and_remove_admin_via_file(h: Harness) -> None:
    await h.private(ADMIN, "/addadmin 444")
    assert h.ctx.is_admin(444)
    assert "444" in h.settings.admins_file.read_text()
    await h.private(ADMIN, "/removeadmin 111")  # from .env: permanent
    assert h.ctx.is_admin(ADMIN_ID)
    await h.private(ADMIN, "/removeadmin 444")
    assert not h.ctx.is_admin(444)


def test_admin_store_keeps_at_least_one(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = AdminStore(tmp_path / "admins.json", [])
    assert store.add(5)
    assert store.remove(5) is RemoveResult.IS_OWNER  # the only admin is the owner
    assert store.add(6)
    assert store.remove(6) is RemoveResult.REMOVED
    reloaded = AdminStore(tmp_path / "admins.json", [])
    assert reloaded.all == {5}
