"""Unit tests: classification for every content type + Persian normalisation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.bale.models import Message, Update
from app.db.models import ContentType
from app.domain.classify import (
    classify,
    document_subtype,
    extract_hashtags,
    extract_urls,
    normalize_fa,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "updates"


def load_message(name: str) -> Message:
    update = Update.model_validate(json.loads((FIXTURES / f"{name}.json").read_text("utf-8")))
    assert update.message is not None
    return update.message


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("text", ContentType.TEXT),
        ("link", ContentType.LINK),
        ("image", ContentType.IMAGE),
        ("video", ContentType.VIDEO),
        ("animation", ContentType.ANIMATION),
        ("voice", ContentType.VOICE),
        ("audio", ContentType.AUDIO),
        ("document", ContentType.DOCUMENT),
        ("location", ContentType.LOCATION),
        ("contact", ContentType.CONTACT),
        ("sticker", ContentType.STICKER),
    ],
)
def test_classify_all_types(fixture: str, expected: ContentType) -> None:
    assert classify(load_message(fixture)).content_type is expected


def test_animation_takes_priority_over_document() -> None:
    # Bale fills document alongside animation; animation must win.
    message = load_message("animation")
    assert message.document is not None
    result = classify(message)
    assert result.content_type is ContentType.ANIMATION


def test_image_picks_largest_photo_size() -> None:
    result = classify(load_message("image"))
    assert result.media[0].file_id == "ph_big"
    assert result.caption == "توضیح تصویر"


def test_document_subtype_from_mime_and_extension() -> None:
    assert document_subtype("application/pdf", None) == "pdf"
    assert document_subtype(None, "report.docx") == "word"
    assert document_subtype(None, "data.xlsx") == "excel"
    assert document_subtype("application/zip", None) == "archive"
    assert document_subtype(None, "script.py") == "code"
    assert document_subtype("image/png", None) == "image_file"
    assert document_subtype(None, "unknown.xyz") == "other"


def test_forwarded_message_records_source() -> None:
    result = classify(load_message("forwarded_text"))
    assert result.is_forwarded is True
    assert result.forward_source is not None
    assert "hossein" in result.forward_source


def test_link_dominant_vs_text_with_link() -> None:
    link_msg = load_message("link")
    assert classify(link_msg).content_type is ContentType.LINK
    text_msg = load_message("text")
    text_msg.text = (
        "این توضیح مفصل و طولانی درباره‌ی یک مقاله است https://a.io و ادامه‌ی توضیح مفصل"
    )
    result = classify(text_msg)
    assert result.content_type is ContentType.TEXT
    assert result.urls == ["https://a.io"]


def test_voice_metadata_extracted() -> None:
    result = classify(load_message("voice"))
    assert result.media[0].duration == 201
    assert result.content_subtype == "audio/ogg"


# ─── Persian normalisation (mandatory rules) ───


def test_normalize_arabic_letters() -> None:
    assert normalize_fa("علي") == "علی"
    assert normalize_fa("كتاب") == "کتاب"
    assert normalize_fa("مدرسة") == "مدرسه"
    assert normalize_fa("أحمد إمام آب") == "احمد امام اب"


def test_normalize_digits() -> None:
    assert normalize_fa("۱۲۳۴") == "1234"
    assert normalize_fa("٥٦٧") == "567"


def test_normalize_kashida_and_diacritics() -> None:
    assert normalize_fa("مـــتـن") == "متن"
    assert normalize_fa("مَتْن") == "متن"


def test_normalize_zwnj_and_spaces() -> None:
    assert normalize_fa("می\u200cخواهم") == "می خواهم"
    assert normalize_fa("  الف   ب  ") == "الف ب"


def test_extract_urls_and_hashtags() -> None:
    text = "ببینید https://example.com/x و www.test.ir #یادگیری #شبکه_و_منبع"
    assert extract_urls(text) == ["https://example.com/x", "www.test.ir"]
    assert extract_hashtags(text) == ["#یادگیری", "#شبکه_و_منبع"]
