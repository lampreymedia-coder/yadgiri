"""Unit tests for Bale research-group delivery risk detection."""

from __future__ import annotations

from app.domain.delivery import almost_all_administrators


def test_almost_all_administrators_true_when_everyone_is_admin() -> None:
    assert almost_all_administrators(7, 7) is True
    assert almost_all_administrators(6, 6) is True


def test_almost_all_administrators_true_with_one_ordinary_member_in_large_group() -> None:
    assert almost_all_administrators(7, 6) is True
    assert almost_all_administrators(5, 4) is True


def test_almost_all_administrators_false_for_working_mixed_group() -> None:
    assert almost_all_administrators(5, 3) is False
    assert almost_all_administrators(10, 3) is False


def test_almost_all_administrators_false_for_tiny_owner_bot_member_group() -> None:
    assert almost_all_administrators(3, 2) is False
    assert almost_all_administrators(0, 0) is False
    assert almost_all_administrators(5, 0) is False
