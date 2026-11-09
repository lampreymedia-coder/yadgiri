"""Unit picker in /register and the panel: search by Reply, tree, suggestions, recent, /register <Id>."""

from __future__ import annotations

from typing import Any

from tests.bot.harness import ADMIN_ID, GROUP, GROUP_ID, OTHER_USER, Harness

ADMIN = {"id": ADMIN_ID, "is_bot": False, "first_name": "مدیر"}
NAMED_GROUP = {**GROUP, "title": "نهاد اندیشکده ای - نگاشت"}

# Extra units on top of the seeded ones (1 «ستاد مرکزی», 2..10 «واحد NN», 11 inactive).
UNITS = [
    (100, 1, "معاونت پژوهش", None, 1),
    (101, 2, "اندیشکده توسعه صنعتی نگاشت", 100, 1),
    (102, 2, "اندیشکده راهبردی افق", 100, 1),
    (103, 3, "سیستم کنترل بلوغ و انتقال فاز", 101, 1),
    (104, 3, "سیستم کنترل بلوغ و انتقال فاز", 102, 1),
    (105, 4, "بخش پایش", 103, 1),
    (3465, 2, "دفتر میان‌بر", 100, 1),
    (3466, 2, "دفتر بسته", 100, 0),
] + [(200 + i, 3, f"گروه آزمایشی {i:02d}", 102, 1) for i in range(1, 26)]


def add_units(h: Harness, units: list[tuple[Any, ...]] = UNITS) -> None:
    h.root.execute(f"USE `{h.db_name()}`")
    for unit in units:
        h.root.execute(
            "INSERT INTO OrgUnits (Id, LevelNo, Name, ParentId, IsActive) VALUES (%s, %s, %s, %s, %s)",
            unit,
        )


def picker(h: Harness, chat_id: int = GROUP_ID) -> Any:
    for message in reversed(list(h.fake.messages.values())):
        if message.chat_id == chat_id and not message.deleted and message.reply_markup:
            return message
    raise AssertionError("no picker message")


def labels(h: Harness, chat_id: int = GROUP_ID) -> list[str]:
    return h.fake.markup_labels(picker(h, chat_id).reply_markup)


async def tap(h: Harness, label_start: str, chat_id: int = GROUP_ID, user: dict = ADMIN) -> None:
    message = picker(h, chat_id)
    rows = message.reply_markup["inline_keyboard"]
    data = next(
        b["callback_data"] for row in rows for b in row if b["text"].startswith(label_start)
    )
    assert data.isascii() and len(data.encode()) <= 64
    _, action, sid, arg = data.split("|")
    await h.press(user, action, sid, arg, chat_id=chat_id, message_id=message.message_id)


def prompt_id(h: Harness, chat_id: int = GROUP_ID) -> int:
    return next(
        m.message_id
        for m in reversed(list(h.fake.messages.values()))
        if m.chat_id == chat_id and not m.deleted and m.text and "در پاسخ (Reply)" in m.text
    )


async def search(h: Harness, words: str, chat: dict = GROUP, user: dict = ADMIN) -> int:
    await tap(h, "🔎", chat_id=chat["id"])
    reply_to = {"message_id": prompt_id(h, chat["id"]), "chat": chat}
    return await h.send(chat, user, text=words, reply_to_message=reply_to)


async def test_search_by_reply_paged_and_confirm(h: Harness) -> None:
    add_units(h)
    await h.text(GROUP, ADMIN, "/register")
    message_id = await search(h, "گروه آزمایشی")
    # the admin's search message is consumed: removed from the group, no wizard, no rows
    assert (GROUP_ID, message_id) in h.deleted()
    assert len(h.ctx.wizards) == 0 and h.count("Posts") == 0
    text = picker(h).text
    assert "۲۵ نتیجه" in text and "صفحه‌ی ۱ از ۳" in text
    results = [label for label in labels(h) if "آزمایشی" in label]
    assert len(results) == 10
    assert results[0] == "معاونت پژوهش › اندیشکده راهبردی افق › گروه آزمایشی 01 (س۳)"
    assert "◀️ بعدی" in labels(h) and "قبلی ▶️" not in labels(h)
    await tap(h, "◀️ بعدی")
    await tap(h, "◀️ بعدی")
    assert len([label for label in labels(h) if "آزمایشی" in label]) == 5
    assert "قبلی ▶️" in labels(h) and "◀️ بعدی" not in labels(h)
    await tap(h, "معاونت پژوهش › اندیشکده راهبردی افق › گروه آزمایشی 25")
    assert "معاونت پژوهش › اندیشکده راهبردی افق › گروه آزمایشی 25" in picker(h).text
    await tap(h, "↩️ بازگشت")  # back to the same results page
    assert "صفحه‌ی ۳ از ۳" in picker(h).text
    await tap(h, "معاونت پژوهش › اندیشکده راهبردی افق › گروه آزمایشی 25")
    assert h.count("BaleGroups") == 0
    await tap(h, "✅ تأیید")
    assert h.root.rows("SELECT OrgUnitId, IsActive FROM BaleGroups") == [(225, 1)]


async def test_search_with_parent_name_finds_one_of_two_same_names(h: Harness) -> None:
    add_units(h)
    await h.text(GROUP, ADMIN, "/register")
    await search(h, "سیستم کنترل بلوغ")
    assert len([label for label in labels(h) if "سیستم کنترل بلوغ" in label]) == 2
    await search(h, "نگاشت کنترل بلوغ")
    found = [label for label in labels(h) if "(س" in label]
    # too long for 60 characters: the start of the path is cut, the name stays whole
    assert found == ["…شکده توسعه صنعتی نگاشت › سیستم کنترل بلوغ و انتقال فاز (س۳)"]
    assert len(found[0]) <= 60


async def test_many_same_name_results_show_the_hint(h: Harness) -> None:
    add_units(h, [(300 + i, 2, f"شاخه {i:02d}", 1, 1) for i in range(12)])
    add_units(h, [(400 + i, 3, "دفتر هماهنگی", 300 + i, 1) for i in range(12)])
    await h.text(GROUP, ADMIN, "/register")
    await search(h, "دفتر هماهنگی")
    assert "۱۲ نتیجه؛ برای دقیق‌تر شدن، نام واحد بالاتر را هم بنویسید" in picker(h).text
    await search(h, "شاخه 07 دفتر")
    assert [label for label in labels(h) if "(س" in label] == [
        "ستاد مرکزی › شاخه 07 › دفتر هماهنگی (س۳)"
    ]


async def test_nothing_found_offers_a_new_search(h: Harness) -> None:
    add_units(h)
    await h.text(GROUP, ADMIN, "/register")
    await search(h, "ناموجود")
    assert "چیزی پیدا نشد" in picker(h).text
    assert "🔎 جست‌وجوی دوباره" in labels(h)


async def test_short_search_and_other_users_reply_are_not_searches(h: Harness) -> None:
    add_units(h)
    h.register_group(org_unit=3)  # changing the unit of a working group
    await h.text(GROUP, ADMIN, "/register")
    await search(h, "ن")
    assert "حداقل ۲ حرف" in h.texts_to(GROUP_ID)[-1]
    # someone else replying to the prompt: not a search; handled like any group message
    await search(h, "نگاشت", user=OTHER_USER)
    state = next(iter(h.ctx.unit_pickers.values()))
    assert state.query == ""
    assert len(h.ctx.wizards) == 1 and h.ctx.wizards.all()[0].user_id == OTHER_USER["id"]
    # the admin's reply is a search and is never archived
    await search(h, "نگاشت")
    assert state.query == "نگاشت"
    assert len(h.ctx.wizards) == 1 and h.count("Posts") == 0


async def test_tree_roots_children_up_and_pick_this(h: Harness) -> None:
    add_units(h)
    await h.text(GROUP, ADMIN, "/register")
    await tap(h, "🌳")
    assert labels(h)[:2] == ["ستاد مرکزی (۹)", "معاونت پژوهش (۳)"]  # «دفتر بسته» is inactive
    await tap(h, "معاونت پژوهش")
    assert "مسیر فعلی: معاونت پژوهش" in picker(h).text
    assert labels(h)[:3] == [
        "اندیشکده توسعه صنعتی نگاشت (۱)",
        "اندیشکده راهبردی افق (۲۶)",
        "دفتر میان‌بر",
    ]
    assert "دفتر بسته" not in labels(h)
    await tap(h, "اندیشکده راهبردی افق")
    assert "مسیر فعلی: معاونت پژوهش › اندیشکده راهبردی افق" in picker(h).text
    assert len([label for label in labels(h) if "آزمایشی" in label or "سیستم" in label]) == 8
    await tap(h, "⬆️ بالا")
    assert "مسیر فعلی: معاونت پژوهش" in picker(h).text and "›" not in picker(h).text
    await tap(h, "⬆️ بالا")
    assert labels(h)[0] == "ستاد مرکزی (۹)"
    await tap(h, "معاونت پژوهش")
    await tap(h, "✅ انتخاب همین واحد")
    await tap(h, "✅ تأیید")
    assert h.root.rows("SELECT OrgUnitId FROM BaleGroups") == [(100,)]


async def test_suggestions_from_group_title(h: Harness) -> None:
    add_units(h)
    await h.text(NAMED_GROUP, ADMIN, "/register")
    assert "💡 پیشنهادها" in labels(h)
    await tap(h, "💡")
    suggested = [label for label in labels(h) if "(س" in label]
    assert len(suggested) <= 3
    assert any(label.endswith("اندیشکده توسعه صنعتی نگاشت (س۲)") for label in suggested)


async def test_no_suggestion_button_without_shared_words(h: Harness) -> None:
    add_units(h)
    await h.text(GROUP, ADMIN, "/register")  # «گروه رصد»: no unit has «رصد»
    assert "💡 پیشنهادها" not in labels(h)
    assert "🕘 اخیر" not in labels(h)  # no group registered yet


async def test_recent_units_from_bale_groups(h: Harness) -> None:
    add_units(h)
    h.register_group(bale_group_id=-901, org_unit=101)
    h.register_group(bale_group_id=-902, org_unit=3)
    h.register_group(bale_group_id=-903, org_unit=101)
    h.root.execute(
        "UPDATE BaleGroups SET UpdatedAt = CreatedAt + INTERVAL 1 DAY WHERE BaleChatId = -901"
    )
    await h.text(GROUP, ADMIN, "/register")
    await tap(h, "🕘")
    recent = [label for label in labels(h) if "(س" in label]
    assert recent == ["معاونت پژوهش › اندیشکده توسعه صنعتی نگاشت (س۲)", "ستاد مرکزی › واحد 03 (س۲)"]


async def test_register_with_id_goes_straight_to_confirm(h: Harness) -> None:
    add_units(h)
    await h.text(GROUP, ADMIN, "/register 3465")
    assert "معاونت پژوهش › دفتر میان‌بر" in picker(h).text
    await tap(h, "✅ تأیید")
    assert h.root.rows("SELECT OrgUnitId FROM BaleGroups") == [(3465,)]


async def test_register_with_unknown_or_inactive_id_is_refused(h: Harness) -> None:
    add_units(h)
    for raw in ("99999", "3466", "abc"):
        await h.text(GROUP, ADMIN, f"/register {raw}")
        assert "پیدا نشد یا فعال نیست" in h.texts_to(GROUP_ID)[-1]
    assert h.count("BaleGroups") == 0


async def test_panel_group_screen_uses_the_same_picker(h: Harness) -> None:
    add_units(h)
    group_id = h.register_group()
    chat = {"id": ADMIN_ID, "type": "private", "first_name": "مدیر"}
    await h.private(ADMIN, "/panel")
    await h.press(ADMIN, "pa", "grs", str(group_id), message_id=picker(h, ADMIN_ID).message_id)
    await tap(h, "🏢", chat_id=ADMIN_ID)
    assert labels(h, ADMIN_ID)[:2] == ["🔎 جست‌وجو", "🌳 مرور درختی"]
    await search(h, "دفتر میان", chat=chat)
    await tap(h, "معاونت پژوهش › دفتر میان‌بر", chat_id=ADMIN_ID)
    await tap(h, "✅ تأیید", chat_id=ADMIN_ID)
    assert h.root.rows("SELECT OrgUnitId FROM BaleGroups") == [(3465,)]
    assert "واحد سازمانی: دفتر میان‌بر" in picker(h, ADMIN_ID).text
