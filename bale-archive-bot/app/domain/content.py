"""Bot-side content kinds produced by :mod:`app.domain.classify`.

These are only labels inside the program. What is written to the database
(``Post.content_type`` / ``PostMedia.media_type``) comes from
:mod:`app.mapping`.
"""

from __future__ import annotations

import enum


class ContentType(enum.StrEnum):
    TEXT = "text"
    LINK = "link"
    IMAGE = "image"
    VIDEO = "video"
    ANIMATION = "animation"
    VOICE = "voice"
    AUDIO = "audio"
    DOCUMENT = "document"
    STICKER = "sticker"
    CONTACT = "contact"
    LOCATION = "location"
    ALBUM = "album"
    OTHER = "other"
