"""Unit tests: webhook vs safety-polling receive policy."""

from __future__ import annotations

from app.core.receive import (
    safety_polling_needed,
    should_register_webhook,
    webhook_needs_reregister,
)


def test_polling_needed_when_public_tunnel_is_down() -> None:
    assert safety_polling_needed(public_ok=False, pending=0, last_webhook_age_seconds=1) is True


def test_polling_needed_when_bale_has_a_backlog() -> None:
    assert safety_polling_needed(public_ok=True, pending=89, last_webhook_age_seconds=1) is True


def test_polling_not_needed_when_webhook_is_healthy_and_idle() -> None:
    assert safety_polling_needed(public_ok=True, pending=0, last_webhook_age_seconds=120) is False


def test_polling_needed_when_pending_unknown_and_webhook_stale() -> None:
    assert (
        safety_polling_needed(public_ok=True, pending=None, last_webhook_age_seconds=30) is True
    )


def test_dead_tunnel_must_not_keep_webhook() -> None:
    assert should_register_webhook(False) is False
    assert should_register_webhook(True) is True


def test_webhook_reregister_when_missing_or_host_changed() -> None:
    expected = "https://example.trycloudflare.com/webhook/secret"
    assert webhook_needs_reregister("", expected) is True
    assert webhook_needs_reregister(None, expected) is True
    assert webhook_needs_reregister(expected, expected) is False
    assert webhook_needs_reregister(expected + "/", expected) is False
    assert webhook_needs_reregister("https://other.example/webhook/secret", expected) is True
