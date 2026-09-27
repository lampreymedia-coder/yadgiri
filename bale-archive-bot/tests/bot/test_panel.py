"""2-4: private admin panel with buttons; 5 of section 3: Excel is RTL, Persian, Shamsi."""

from __future__ import annotations

import io
import re
from datetime import datetime

from openpyxl import load_workbook

from app.domain.excel import HEADERS, build_workbook
from app.domain.reports import ExportRow
from tests.bot.harness import ADMIN_ID, GROUP, USER, Harness

ADMIN = {"id": ADMIN_ID, "is_bot": False, "first_name": "مدیر"}


def last_text(h: Harness, chat_id: int) -> str:
    texts = [m.text or "" for m in h.fake.messages.values() if m.chat_id == chat_id and not m.deleted]
    return texts[-1] if texts else ""


def panel_id(h: Harness) -> int:
    ids = [m.message_id for m in h.fake.messages.values() if m.chat_id == ADMIN_ID and m.reply_markup]
    return ids[-1]


async def _seed(h: Harness) -> None:
    h.register_group()
    await h.text(GROUP, USER, "اولی")
    await h.confirm([1, 2])
    await h.send(GROUP, USER, voice={"file_id": "v", "file_size": 10})
    await h.confirm([1])


async def test_panel_home_buttons(h: Harness) -> None:
    await h.private(ADMIN, "/panel")
    labels = h.fake.markup_labels(h.fake.last_markup(ADMIN_ID))
    for expected in ("📊 آمار کلی", "🏷 گزارش هشتگ‌ها", "🙋 کاربران فعال", "📂 گروه‌ها",
                     "📥 خروجی اکسل", "✏️ مدیریت هشتگ‌ها", "👥 مدیران", "💾 وضعیت دیسک"):
        assert expected in labels


async def test_panel_is_admin_only(h: Harness) -> None:
    await h.private(USER, "/panel")
    await h.press(USER, "pa", "st")
    assert all("آمار" not in t for t in h.texts_to(USER["id"]))


async def test_stats_bars_and_users(h: Harness) -> None:
    await _seed(h)
    await h.private(ADMIN, "/panel")
    await h.press(ADMIN, "pa", "st", message_id=panel_id(h))
    assert "کل ثبت‌ها: ۲" in last_text(h, ADMIN_ID)
    await h.press(ADMIN, "pa", "tr", message_id=panel_id(h))
    bars = last_text(h, ADMIN_ID)
    assert "#یادگیری\n██████████ ۲" in bars and "#شبکه_و_منبع\n█████░░░░░ ۱" in bars
    await h.press(ADMIN, "pa", "us", message_id=panel_id(h))
    assert "علی رضایی (@ali) — ۲" in last_text(h, ADMIN_ID)
    (person_id,), = h.root.rows("SELECT id FROM Person")
    await h.press(ADMIN, "pa", "usr", str(person_id), message_id=panel_id(h))
    assert "👤 علی رضایی" in last_text(h, ADMIN_ID) and "کل ثبت‌ها: ۲" in last_text(h, ADMIN_ID)


async def test_group_report_level_and_disable(h: Harness) -> None:
    await _seed(h)
    (group_id,), = h.root.rows("SELECT id FROM EhyaGroup")
    await h.private(ADMIN, "/panel")
    await h.press(ADMIN, "pa", "grs", str(group_id), message_id=panel_id(h))
    assert "کل ثبت‌ها: ۲" in last_text(h, ADMIN_ID)
    await h.press(ADMIN, "pa", "grl", f"{group_id}:6", message_id=panel_id(h))
    await h.press(ADMIN, "pa", "grt", f"{group_id}:0", message_id=panel_id(h))
    assert h.root.rows("SELECT level, is_active FROM EhyaGroup") == [(6, 0)]
    assert h.count("EhyaGroup") == 1


async def test_hashtag_add_rename_toggle_never_delete(h: Harness) -> None:
    await h.private(ADMIN, "/panel")
    await h.press(ADMIN, "pa", "ha")
    await h.private(ADMIN, "گزارش میدانی")
    assert h.root.rows("SELECT name, is_active FROM Hashtag WHERE id > 4") == [("گزارش میدانی", 1)]
    await h.press(ADMIN, "pa", "ha")
    await h.private(ADMIN, "سند")  # duplicate name
    assert "از قبل هست" in h.texts_to(ADMIN_ID)[-2] or "از قبل هست" in h.texts_to(ADMIN_ID)[-1]
    await h.press(ADMIN, "pa", "hr", "3")
    await h.private(ADMIN, "محتوای ویژه")
    await h.press(ADMIN, "pa", "ht", "2:0")
    rows = h.root.rows("SELECT id, name, is_active FROM Hashtag ORDER BY id")
    assert rows[1] == (2, "شبکه و منبع", 0)
    assert rows[2] == (3, "محتوای ویژه", 1)
    assert len(rows) == 5


async def test_export_sends_a_document(h: Harness) -> None:
    await _seed(h)
    await h.private(ADMIN, "/panel")
    for screen, arg in (("xa", ""), ("xhs", "2"), ("xrs", "7")):
        await h.press(ADMIN, "pa", screen, arg)
    assert len(h.fake.calls_for("sendDocument")) == 3
    (group_id,), = h.root.rows("SELECT id FROM EhyaGroup")
    await h.press(ADMIN, "pa", "xgs", str(group_id + 99))  # empty filter
    assert "هیچ ثبتی نیست" in h.texts_to(ADMIN_ID)[-1]


def test_excel_is_rtl_persian_and_shamsi() -> None:
    row = ExportRow(
        post_id=7,
        created_at=datetime(2026, 9, 27, 13, 30),
        posted_at=datetime(2026, 9, 27, 13, 29),
        sender="علی رضایی (@ali)",
        bale_user_id=222,
        group_name="گروه رصد",
        content_type=4,
        hashtags="یادگیری، سند",
        content_text="",
        files=1,
    )
    sheet = load_workbook(io.BytesIO(build_workbook([row]))).active
    assert sheet.sheet_view.rightToLeft is True
    assert [cell.value for cell in sheet[1]] == HEADERS
    assert all(re.search("[؀-ۿ]", header) for header in HEADERS)
    values = [cell.value for cell in sheet[2]]
    assert values[1] == "1405/07/05 13:30"  # Shamsi date
    assert values[6] == "صوت"


async def test_disk_status(h: Harness) -> None:
    await h.private(ADMIN, "/panel")
    await h.press(ADMIN, "pa", "dk", message_id=panel_id(h))
    text = last_text(h, ADMIN_ID)
    assert "فضای آزاد" in text and "پوشه‌ی media" in text
