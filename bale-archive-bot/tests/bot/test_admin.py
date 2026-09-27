"""/register, /unregister, admins file, reports."""

from __future__ import annotations

from app.core.admins import AdminStore, RemoveResult
from tests.bot.harness import ADMIN_ID, ARCHIVE, GROUP, GROUP_ID, USER, Harness

ADMIN = {"id": ADMIN_ID, "is_bot": False, "first_name": "مدیر"}


async def test_register_asks_level_and_adds_one_row(h: Harness) -> None:
    await h.text(GROUP, ADMIN, "/register")
    labels = h.fake.markup_labels(h.fake.last_markup(GROUP_ID))
    assert labels == ["۱", "۲", "۳", "۴", "۵", "۶", "۷"]
    assert h.count("EhyaGroup") == 0
    await h.press(ADMIN, "lv", "", "3", chat_id=GROUP_ID, message_id=1)
    rows = h.root.rows("SELECT bale_group_id, bale_group_name, level, is_active FROM EhyaGroup")
    assert rows == [(GROUP_ID, "گروه رصد", 3, 1)]
    # the group now works
    await h.text(GROUP, USER, "متن")
    assert len(h.ctx.wizards) == 1


def _level_button(h: Harness, label: str) -> str:
    markup = h.fake.last_markup(GROUP_ID)
    assert markup is not None
    return next(b["callback_data"] for row in markup["inline_keyboard"] for b in row if b["text"] == label)


async def test_register_in_unregistered_group_real_button_level_3(h: Harness) -> None:
    """Regression: the level tap must not be swallowed by the unregistered-group silence."""
    await h.text(GROUP, ADMIN, "/register")
    data = _level_button(h, "۳")
    _, action, sid, arg = data.split("|")
    assert sid == str(GROUP_ID)
    await h.press(ADMIN, action, sid, arg, chat_id=GROUP_ID, message_id=1)
    rows = h.root.rows("SELECT bale_group_id, level, is_active FROM EhyaGroup")
    assert rows == [(GROUP_ID, 3, 1)]


async def test_register_level_tap_without_message_field(h: Harness) -> None:
    """Some Bale callbacks carry no ``message``; the group id comes from callback_data."""
    await h.text(GROUP, ADMIN, "/register")
    data = _level_button(h, "۳")
    await h.feed({"callback_query": {"id": "cq-x", "from": ADMIN, "data": data}})
    assert h.root.rows("SELECT bale_group_id, level FROM EhyaGroup") == [(GROUP_ID, 3)]


async def test_non_admin_register_is_silent(h: Harness) -> None:
    await h.text(GROUP, USER, "/register")
    await h.press(USER, "lv", "", "2", chat_id=GROUP_ID)
    assert h.count("EhyaGroup") == 0
    assert h.fake.calls_for("sendMessage") == []


async def test_unregister_keeps_the_row(h: Harness) -> None:
    h.register_group()
    await h.text(GROUP, ADMIN, "/unregister")
    assert h.root.rows("SELECT is_active FROM EhyaGroup") == [(0,)]
    await h.text(GROUP, USER, "متن")
    assert len(h.ctx.wizards) == 0
    # registering again re-activates the same row
    await h.text(GROUP, ADMIN, "/register")
    await h.press(ADMIN, "lv", "", "5", chat_id=GROUP_ID)
    assert h.root.rows("SELECT level, is_active FROM EhyaGroup") == [(5, 1)]
    assert h.count("EhyaGroup") == 1


async def test_archive_group_cannot_be_registered(h: Harness) -> None:
    await h.text(ARCHIVE, ADMIN, "/register")
    await h.press(ADMIN, "lv", "", "1", chat_id=ARCHIVE["id"])
    assert h.count("EhyaGroup") == 0


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
