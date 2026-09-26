"""نگاشت نوع محتوا به کدهای دیتابیس — تنها جای این عددها.

اگر نیروی انسانی کدها را عوض کرد، فقط همین فایل را عوض کنید.
(بخش ۵-۱ و ۵-۲ فایل CLAUDE-BOT-FIX.md)

Post.content_type:
    1 متن (شامل لینک)
    2 تصویر و آلبوم تصویر
    3 ویدیو (کلیپ و انیمیشن)
    4 صوت (فایل صوتی و پیام صوتی)
    5 سند و فایل

PostMedia.media_type:
    1 تصویر
    2 ویدیو
    3 صوت
    4 سند
"""

from __future__ import annotations

from app.domain.content import ContentType

POST_TEXT = 1
POST_IMAGE = 2
POST_VIDEO = 3
POST_AUDIO = 4
POST_DOCUMENT = 5

MEDIA_IMAGE = 1
MEDIA_VIDEO = 2
MEDIA_AUDIO = 3
MEDIA_DOCUMENT = 4

# Bot content kind → Post.content_type. Kinds missing here are not archivable.
POST_CONTENT_TYPE: dict[ContentType, int] = {
    ContentType.TEXT: POST_TEXT,
    ContentType.LINK: POST_TEXT,
    ContentType.CONTACT: POST_TEXT,
    ContentType.LOCATION: POST_TEXT,
    ContentType.IMAGE: POST_IMAGE,
    ContentType.VIDEO: POST_VIDEO,
    ContentType.ANIMATION: POST_VIDEO,
    ContentType.VOICE: POST_AUDIO,
    ContentType.AUDIO: POST_AUDIO,
    ContentType.DOCUMENT: POST_DOCUMENT,
}

# Bot content kind of one file → PostMedia.media_type.
MEDIA_TYPE: dict[ContentType, int] = {
    ContentType.IMAGE: MEDIA_IMAGE,
    ContentType.VIDEO: MEDIA_VIDEO,
    ContentType.ANIMATION: MEDIA_VIDEO,
    ContentType.VOICE: MEDIA_AUDIO,
    ContentType.AUDIO: MEDIA_AUDIO,
    ContentType.DOCUMENT: MEDIA_DOCUMENT,
}

# Persian labels for reports (keyed by Post.content_type code).
POST_CONTENT_LABELS: dict[int, str] = {
    POST_TEXT: "متن",
    POST_IMAGE: "تصویر",
    POST_VIDEO: "ویدیو",
    POST_AUDIO: "صوت",
    POST_DOCUMENT: "سند و فایل",
}


def post_content_type(kinds: list[ContentType]) -> int | None:
    """Code for a whole post. ``kinds`` has one entry per message (albums: several).

    An album that holds any video counts as video; an all-picture album is
    an image post. ``None`` means the post cannot be archived.
    """
    if not kinds:
        return None
    if len(kinds) == 1:
        return POST_CONTENT_TYPE.get(kinds[0])
    codes = [POST_CONTENT_TYPE.get(kind) for kind in kinds]
    if any(code is None for code in codes):
        return None
    if POST_VIDEO in codes:
        return POST_VIDEO
    if all(code == POST_IMAGE for code in codes):
        return POST_IMAGE
    return codes[0]


def media_type(kind: ContentType) -> int | None:
    return MEDIA_TYPE.get(kind)
