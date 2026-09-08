"""Unit tests: text+image archive helpers."""

from __future__ import annotations

from types import SimpleNamespace

from app.db.models import ContentType, StorageStatus, SubmissionStatus
from app.domain.submission import archives_image, has_text_and_image, image_storage_action


def _sub(**kwargs: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "content_type": ContentType.TEXT,
        "content_subtype": None,
        "text_content": None,
        "caption": None,
        "media_files": [],
        "meta": {},
        "status": SubmissionStatus.AWAITING_DECISION,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_has_text_and_image_requires_both() -> None:
    assert has_text_and_image(_sub(content_type=ContentType.IMAGE, caption="توضیح تصویر"))
    assert has_text_and_image(_sub(content_type=ContentType.IMAGE, text_content="متن کنار عکس"))
    assert not has_text_and_image(_sub(content_type=ContentType.IMAGE, caption="  "))
    assert not has_text_and_image(_sub(content_type=ContentType.TEXT, text_content="فقط متن"))
    assert not has_text_and_image(_sub(content_type=ContentType.VOICE, caption="توضیح صوت"))


def test_image_document_with_caption_counts() -> None:
    assert has_text_and_image(
        _sub(
            content_type=ContentType.DOCUMENT,
            content_subtype="image_file",
            caption="اسکرین‌شات",
        )
    )
    assert not has_text_and_image(
        _sub(content_type=ContentType.DOCUMENT, content_subtype="pdf", caption="گزارش")
    )


def test_mime_image_on_other_type_counts() -> None:
    media = SimpleNamespace(mime_type="image/png")
    assert has_text_and_image(
        _sub(content_type=ContentType.DOCUMENT, caption="لوگو", media_files=[media])
    )


def test_archives_image_defaults_to_keep() -> None:
    photo = _sub(content_type=ContentType.IMAGE, caption="توضیح")
    assert archives_image(photo) is True
    photo.meta = {"include_image": False}
    assert archives_image(photo) is False
    text = _sub(content_type=ContentType.TEXT, text_content="سلام")
    assert archives_image(text) is True


def test_image_storage_action_waits_until_choice() -> None:
    photo = _sub(content_type=ContentType.IMAGE, caption="توضیح")
    assert image_storage_action(photo) == "wait"
    photo.meta = {"include_image": True}
    assert image_storage_action(photo) == "download"
    photo.meta = {"include_image": False}
    assert image_storage_action(photo) == "skip"
    photo.status = SubmissionStatus.COMPLETED
    photo.meta = {}
    assert image_storage_action(photo) == "download"
    assert image_storage_action(_sub(content_type=ContentType.VOICE)) == "download"


def test_skipped_status_constant_is_not_failed() -> None:
    assert StorageStatus.SKIPPED_TOO_LARGE is not StorageStatus.FAILED
    assert StorageStatus.SKIPPED_TOO_LARGE is not StorageStatus.PENDING
