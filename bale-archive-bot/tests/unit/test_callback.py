"""Unit tests: callback_data codec (64-byte ASCII limit)."""

from __future__ import annotations

import pytest

from app.bale.keyboards import (
    MAX_CALLBACK_BYTES,
    CallbackDataError,
    pack_callback,
    parse_callback,
)


def test_roundtrip() -> None:
    packed = pack_callback("tg", "k7f2qa", "3")
    assert packed == "1|tg|k7f2qa|3"
    data = parse_callback(packed)
    assert data.action == "tg"
    assert data.sid == "k7f2qa"
    assert data.arg == "3"


@pytest.mark.parametrize(
    "example",
    [
        "1|tg|k7f2qa|3",
        "1|cnt|k7f2qa|2",
        "1|bk|k7f2qa|",
        "1|ok|k7f2qa|",
        "1|no|k7f2qa|",
        "1|cx|k7f2qa|",
    ],
)
def test_spec_examples_fit_24_bytes(example: str) -> None:
    assert len(example.encode("ascii")) <= 24
    parse_callback(example)


def test_length_limit_enforced() -> None:
    with pytest.raises(CallbackDataError):
        pack_callback("act", "sid123", "x" * 60)
    # Exactly at limit passes: "1|a|s|" is 6 bytes → arg of 58 bytes = 64.
    packed = pack_callback("a", "s", "x" * 58)
    assert len(packed.encode("ascii")) == MAX_CALLBACK_BYTES


def test_non_ascii_rejected() -> None:
    with pytest.raises(CallbackDataError):
        pack_callback("tg", "k7f2qa", "یادگیری")


def test_pipe_rejected() -> None:
    with pytest.raises(CallbackDataError):
        pack_callback("t|g", "sid", "")


def test_malformed_parse_rejected() -> None:
    with pytest.raises(CallbackDataError):
        parse_callback("garbage")
    with pytest.raises(CallbackDataError):
        parse_callback("2|tg|sid|arg")  # unknown version
    with pytest.raises(CallbackDataError):
        parse_callback("1||sid|arg")  # empty action
