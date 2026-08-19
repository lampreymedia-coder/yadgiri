"""Content classification and Persian text normalisation.

Field check order is mandated by the docs (animation also fills document):
voice → audio → animation → video → photo → document → sticker → contact
→ location → text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.bale.models import Message
from app.db.models import ContentType

URL_RE = re.compile(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", re.IGNORECASE)
HASHTAG_RE = re.compile(r"#[\w\u0600-\u06FF\u200c_]+")

_ARABIC_MAP = str.maketrans(
    {
        "ي": "ی",
        "ك": "ک",
        "ة": "ه",
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ـ": None,  # kashida
        "\u200c": " ",  # ZWNJ → space in the searchable copy
    }
)
_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_DIACRITICS_RE = re.compile(r"[\u064B-\u065F\u0670]")
_MULTISPACE_RE = re.compile(r"\s+")

_DOC_SUBTYPES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("pdf", ("application/pdf",), (".pdf",)),
    (
        "word",
        ("application/msword", "officedocument.wordprocessingml"),
        (".doc", ".docx", ".odt", ".rtf"),
    ),
    (
        "excel",
        ("application/vnd.ms-excel", "officedocument.spreadsheetml"),
        (".xls", ".xlsx", ".ods", ".csv"),
    ),
    (
        "powerpoint",
        ("application/vnd.ms-powerpoint", "officedocument.presentationml"),
        (".ppt", ".pptx", ".odp"),
    ),
    (
        "archive",
        (
            "application/zip",
            "application/x-rar",
            "application/x-7z",
            "application/gzip",
            "application/x-tar",
        ),
        (".zip", ".rar", ".7z", ".gz", ".tar", ".bz2"),
    ),
    (
        "code",
        ("text/x-python", "application/json", "application/xml", "text/x-script"),
        (".py", ".js", ".ts", ".json", ".xml", ".html", ".css", ".sql", ".sh", ".yml", ".yaml"),
    ),
    (
        "image_file",
        ("image/",),
        (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".tiff"),
    ),
    ("audio_file", ("audio/",), (".mp3", ".m4a", ".ogg", ".wav", ".flac", ".aac")),
    ("video_file", ("video/",), (".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv")),
    ("text_file", ("text/plain",), (".txt", ".md", ".log")),
)


def normalize_fa(text: str) -> str:
    """Normalise Persian text for search (original text is kept untouched)."""
    normalized = text.translate(_ARABIC_MAP)
    normalized = normalized.translate(_DIGIT_MAP)
    normalized = _DIACRITICS_RE.sub("", normalized)
    return _MULTISPACE_RE.sub(" ", normalized).strip()


def extract_urls(text: str) -> list[str]:
    return URL_RE.findall(text)


def extract_hashtags(text: str) -> list[str]:
    """Hashtags come from regex, not entities (Bale has no entities field)."""
    return HASHTAG_RE.findall(text)


def document_subtype(mime_type: str | None, file_name: str | None) -> str:
    mime = (mime_type or "").lower()
    name = (file_name or "").lower()
    for subtype, mimes, extensions in _DOC_SUBTYPES:
        if any(m in mime for m in mimes) or any(name.endswith(ext) for ext in extensions):
            return subtype
    return "other"


def audio_subtype(mime_type: str | None, file_name: str | None) -> str | None:
    name = (file_name or "").lower()
    for ext in (".mp3", ".m4a", ".ogg", ".wav", ".flac", ".aac", ".wma"):
        if name.endswith(ext):
            return ext[1:]
    if mime_type:
        return mime_type
    return None


@dataclass(slots=True)
class MediaInfo:
    """Extracted metadata for one media item of a submission."""

    file_id: str
    file_unique_id: str | None = None
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    duration: int | None = None
    width: int | None = None
    height: int | None = None


@dataclass(slots=True)
class ClassifiedContent:
    """Result of classifying a single message."""

    content_type: ContentType
    content_subtype: str | None = None
    text_content: str | None = None
    text_normalized: str | None = None
    caption: str | None = None
    urls: list[str] = field(default_factory=list)
    is_forwarded: bool = False
    forward_source: str | None = None
    media: list[MediaInfo] = field(default_factory=list)


def _forward_source(message: Message) -> tuple[bool, str | None]:
    if message.forward_from is not None:
        user = message.forward_from
        label = user.username or f"{user.first_name} {user.last_name or ''}".strip()
        return True, f"user:{user.id}:{label}"
    if message.forward_from_chat is not None:
        chat = message.forward_from_chat
        return True, f"chat:{chat.id}:{chat.title or chat.username or ''}"
    return False, None


def _link_dominant(text: str, urls: list[str]) -> bool:
    """True when the message is essentially just URL(s)."""
    if not urls:
        return False
    stripped = text
    for url in urls:
        stripped = stripped.replace(url, "")
    return len(stripped.strip()) <= max(20, len(text) // 5)


def classify(message: Message) -> ClassifiedContent:
    """Classify a message into a :class:`ClassifiedContent` (spec section 7)."""
    is_forwarded, forward_source = _forward_source(message)
    caption = message.caption
    caption_urls = extract_urls(caption) if caption else []

    def result(
        content_type: ContentType,
        subtype: str | None = None,
        media: list[MediaInfo] | None = None,
        text: str | None = None,
    ) -> ClassifiedContent:
        combined_text = text if text is not None else caption
        return ClassifiedContent(
            content_type=content_type,
            content_subtype=subtype,
            text_content=text,
            text_normalized=normalize_fa(combined_text) if combined_text else None,
            caption=caption,
            urls=extract_urls(text) if text else caption_urls,
            is_forwarded=is_forwarded,
            forward_source=forward_source,
            media=media or [],
        )

    if message.voice is not None:
        v = message.voice
        return result(
            ContentType.VOICE,
            v.mime_type,
            [MediaInfo(v.file_id, v.file_unique_id, None, v.mime_type, v.file_size, v.duration)],
        )
    if message.audio is not None:
        a = message.audio
        return result(
            ContentType.AUDIO,
            audio_subtype(a.mime_type, a.file_name),
            [
                MediaInfo(
                    a.file_id, a.file_unique_id, a.file_name, a.mime_type, a.file_size, a.duration
                )
            ],
        )
    if message.animation is not None:
        # Must precede document: Bale fills document alongside animation.
        an = message.animation
        return result(
            ContentType.ANIMATION,
            an.mime_type,
            [
                MediaInfo(
                    an.file_id,
                    an.file_unique_id,
                    an.file_name,
                    an.mime_type,
                    an.file_size,
                    an.duration,
                    an.width,
                    an.height,
                )
            ],
        )
    if message.video is not None:
        vd = message.video
        return result(
            ContentType.VIDEO,
            vd.mime_type,
            [
                MediaInfo(
                    vd.file_id,
                    vd.file_unique_id,
                    vd.file_name,
                    vd.mime_type,
                    vd.file_size,
                    vd.duration,
                    vd.width,
                    vd.height,
                )
            ],
        )
    if message.photo:
        largest = max(
            message.photo, key=lambda p: (p.width or 0) * (p.height or 0) or (p.file_size or 0)
        )
        return result(
            ContentType.IMAGE,
            None,
            [
                MediaInfo(
                    largest.file_id,
                    largest.file_unique_id,
                    None,
                    None,
                    largest.file_size,
                    None,
                    largest.width,
                    largest.height,
                )
            ],
        )
    if message.document is not None:
        d = message.document
        return result(
            ContentType.DOCUMENT,
            document_subtype(d.mime_type, d.file_name),
            [MediaInfo(d.file_id, d.file_unique_id, d.file_name, d.mime_type, d.file_size)],
        )
    if message.sticker is not None:
        s = message.sticker
        return result(
            ContentType.STICKER,
            None,
            [
                MediaInfo(
                    s.file_id, s.file_unique_id, None, None, s.file_size, None, s.width, s.height
                )
            ],
        )
    if message.contact is not None:
        c = message.contact
        text = f"{c.first_name} {c.last_name or ''}".strip()
        return result(ContentType.CONTACT, None, [], text)
    if message.location is not None:
        loc = message.location
        return result(ContentType.LOCATION, None, [], f"{loc.latitude},{loc.longitude}")
    if message.text is not None:
        text = message.text
        urls = extract_urls(text)
        if urls and _link_dominant(text, urls):
            return result(ContentType.LINK, None, [], text)
        return result(ContentType.TEXT, None, [], text)
    return result(ContentType.OTHER)
