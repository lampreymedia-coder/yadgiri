"""Unit tests: dynamic tag slug/hashtag generation."""

from __future__ import annotations

from app.domain.tags import make_hashtag, make_slug, unique_slug


def test_hashtag_spaces_to_underscores() -> None:
    assert make_hashtag("شبکه و منبع") == "#شبکه_و_منبع"
    assert make_hashtag("یادگیری") == "#یادگیری"


def test_hashtag_strips_invalid_chars() -> None:
    assert make_hashtag("محتوایی!؟ ") == "#محتوایی"


def test_slug_is_ascii() -> None:
    slug = make_slug("شبکه و منبع")
    assert slug.isascii()
    assert " " not in slug


def test_slug_latin_passthrough() -> None:
    assert make_slug("Learning 101") == "learning_101"


def test_unique_slug_suffixes() -> None:
    existing = {"learning", "learning_2"}
    assert unique_slug("learning", existing) == "learning_3"
    assert unique_slug("fresh", existing) == "fresh"
