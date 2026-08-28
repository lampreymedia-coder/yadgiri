"""Unit tests: Persian formatting helpers and report rendering."""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.reports import text_bar
from app.i18n import fa


def test_fa_digits() -> None:
    assert fa.fa_digits(487) == "۴۸۷"
    assert fa.fa_digits("12:34") == "۱۲:۳۴"


def test_jalali_date_known_value() -> None:
    # 2026-08-19 UTC → 1405/05/28 Jalali (Tehran).
    dt = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
    assert fa.jalali_date(dt) == "۱۴۰۵/۰۵/۲۸"


def test_format_bytes() -> None:
    assert "گیگابایت" in fa.format_bytes(2_400_000_000)
    assert "مگابایت" in fa.format_bytes(5_000_000)
    assert fa.format_bytes(None) == "نامشخص"


def test_format_duration() -> None:
    assert fa.format_duration(201) == "۳:۲۱"
    assert fa.format_duration(None) == ""


def test_text_bar_rtl_safe_blocks() -> None:
    assert text_bar(1.0, max_width=8) == "█" * 8
    assert text_bar(0.0) == ""
    half = text_bar(0.5, max_width=8)
    assert 3 <= len(half) <= 5


def test_success_message_is_short_confirmation() -> None:
    text = fa.success_message("k7f2qa", "#یادگیری", "گروه رصد", 10)
    assert "آرشیو شد" in text
    assert "/undo" not in text


def test_caption_header_format() -> None:
    header = fa.published_header("علی احمدی", "#یادگیری #محتوایی")
    assert "علی احمدی" in header
    assert "#یادگیری" in header


def test_decision_prompt_names_group_and_excerpt() -> None:
    text = fa.decision_prompt(
        "علی",
        "text",
        "رصد دوم",
        datetime(2026, 8, 22, 12, 0, tzinfo=UTC),
        short_id="ab12cd",
        excerpt="متن گروه دوم",
    )
    assert "رصد دوم" in text
    assert "ab12cd" in text
    assert "متن گروه دوم" in text
    assert "بالاتر" in text
    assert "انصراف" in text


def test_receive_backlog_mentions_pending_count() -> None:
    text = fa.receive_backlog(89)
    assert "۸۹" in text
    assert "پشتیبان" in text


def test_research_copy_requires_admin() -> None:
    text = fa.research_set_done("تست ربات")
    assert "تست ربات" in text
    assert "ادمین" in text
    assert "فوروارد" in text
    assert "بدون منشن" in text
    need = fa.research_need_admin("تست ربات")
    assert "ادمین" in need
    assert "نقش این گروه" not in need
    assert "مدیر" in fa.BOT_JOIN_DENIED
    assert "خارج" in fa.bot_left_unauthorized_group("رصد تازه")
    assert "رصد تازه" in fa.admin_unauthorized_add("رصد تازه", "علی")


def test_research_delivery_gap_explains_all_admins_and_private_fallback() -> None:
    text = fa.research_delivery_gap(
        "تست ربات",
        member_count=7,
        admin_count=6,
        bot_is_admin=True,
        almost_all_admins=True,
        withheld=True,
    )
    assert "تست ربات" in text
    assert "نفرستاد" in text
    assert "۶" in text
    assert "۷" in text
    assert "همه" in text
    assert "خصوصی" in text
    assert "سازنده" in text


def test_missing_archive_howto_tells_admin_to_rebind() -> None:
    text = fa.missing_archive_howto(["#محتوایی"])
    assert "#محتوایی" in text
    assert "/archive" in text
    assert "نسازید" in text


def test_user_saved_mentions_missing_archive() -> None:
    assert "آرشیو شد" in fa.user_saved()
    text = fa.user_saved(["#محتوایی"])
    assert "#محتوایی" in text
    assert "/archive" in text
    text = fa.start_owner_setup("مینا")
    assert "مینا" in text
    assert "/archive" in text
    assert "/panel" in text
    assert "یادگیری" in text
    assert "سند" in text
    assert "شبکه و منبع" in text
    assert "محتوایی" in text
    assert "دو نفره" in text


def test_image_keep_copy_and_preview_line() -> None:
    assert "تصویر هم ذخیره شود" in fa.IMAGE_KEEP_PROMPT
    assert "تزئینی" in fa.IMAGE_KEEP_PROMPT
    text = fa.preview_prompt(
        "علی",
        "ali",
        "رصد",
        "image",
        "",
        "نامشخص",
        "#یادگیری",
        "توضیح",
        datetime(2026, 8, 22, 12, 0, tzinfo=UTC),
        "ab12cd",
        image_line=fa.PREVIEW_IMAGE_TEXT_ONLY,
    )
    assert "ذخیره نمی‌شود" in text
    assert "فقط متن" in fa.BTN_IMAGE_NO
    assert "متن و تصویر" in fa.BTN_IMAGE_YES
    assert "تصویر هم ذخیره شود" in fa.HELP_MESSAGE
