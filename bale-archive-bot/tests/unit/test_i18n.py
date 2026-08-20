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


def test_success_message_contains_undo_command() -> None:
    text = fa.success_message("k7f2qa", "#یادگیری", "گروه رصد", 10)
    assert "/undo k7f2qa" in text
    assert "۱۰" in text


def test_caption_header_format() -> None:
    header = fa.published_header("علی احمدی", "#یادگیری #محتوایی")
    assert header.startswith("📌 علی احمدی")
    assert "#یادگیری" in header


def test_owner_setup_mentions_archive_command() -> None:
    text = fa.start_owner_setup("مینا")
    assert "مینا" in text
    assert "/archive" in text
    assert "/panel" in text
