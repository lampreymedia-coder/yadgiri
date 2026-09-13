"""Dynamic hashtag management: slug/hashtag generation and validation."""

from __future__ import annotations

import re

from app.domain.classify import normalize_fa

_SLUG_SANITIZE_RE = re.compile(r"[^a-z0-9_]+")
# Allowed hashtag characters: Latin word chars plus Arabic/Persian letters
# and digits — Arabic punctuation (؟ ، ؛ ٪) is explicitly excluded.
_HASHTAG_SANITIZE_RE = re.compile(
    r"[^0-9A-Za-z_\u0621-\u063A\u0641-\u064A\u0660-\u0669\u066E-\u06D3\u06F0-\u06F9]+"
)

# Transliteration used only for building an ASCII slug from a Persian title.
_FA_TO_ASCII: dict[str, str] = {
    "ا": "a",
    "ب": "b",
    "پ": "p",
    "ت": "t",
    "ث": "s",
    "ج": "j",
    "چ": "ch",
    "ح": "h",
    "خ": "kh",
    "د": "d",
    "ذ": "z",
    "ر": "r",
    "ز": "z",
    "ژ": "zh",
    "س": "s",
    "ش": "sh",
    "ص": "s",
    "ض": "z",
    "ط": "t",
    "ظ": "z",
    "ع": "a",
    "غ": "gh",
    "ف": "f",
    "ق": "gh",
    "ک": "k",
    "گ": "g",
    "ل": "l",
    "م": "m",
    "ن": "n",
    "و": "v",
    "ه": "h",
    "ی": "y",
    "ء": "",
    "ئ": "y",
    "ؤ": "v",
}


def make_hashtag(title_fa: str) -> str:
    """Build the display hashtag: spaces become underscores, invalid chars dropped."""
    normalized = normalize_fa(title_fa)
    joined = normalized.replace(" ", "_")
    cleaned = _HASHTAG_SANITIZE_RE.sub("", joined).strip("_")
    return f"#{cleaned}"


def make_slug(title_fa: str) -> str:
    """Build an ASCII slug from a Persian (or Latin) title."""
    normalized = normalize_fa(title_fa).lower()
    transliterated = "".join(_FA_TO_ASCII.get(ch, ch) for ch in normalized)
    underscored = transliterated.replace(" ", "_")
    slug = _SLUG_SANITIZE_RE.sub("", underscored).strip("_")
    return slug or "tag"


def unique_slug(base: str, existing: set[str]) -> str:
    """Ensure slug uniqueness by suffixing a counter when needed."""
    if base not in existing:
        return base
    counter = 2
    while f"{base}_{counter}" in existing:
        counter += 1
    return f"{base}_{counter}"


# Initial tag titles live in app/i18n/fa.py (SEED_TAGS) per project rule 2.
