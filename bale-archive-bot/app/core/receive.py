"""Receive-path policy: webhook is optional; polling must never stop.

The Cloud Agent (and any host behind a trycloudflare URL) can lose the
public tunnel while the local process stays healthy. Bale then queues
updates on the webhook and the bot looks dead. Safety polling drains
that queue even while the webhook URL is still registered.
"""

from __future__ import annotations


def safety_polling_needed(
    *,
    public_ok: bool | None,
    pending: int | None,
    last_webhook_age_seconds: float | None,
    stale_after_seconds: float = 20.0,
) -> bool:
    """True when getUpdates must run so inbound messages are not stranded."""
    if public_ok is False:
        return True
    if pending is not None:
        return pending > 0
    if last_webhook_age_seconds is None:
        return False
    return last_webhook_age_seconds >= stale_after_seconds


def should_register_webhook(public_ok: bool) -> bool:
    """Never point Bale at a tunnel that cannot reach this process."""
    return public_ok


def poll_receive_stale(
    last_poll_at: float | None,
    now: float,
    max_age_seconds: float = 90.0,
) -> bool:
    """True when the receive loop has not completed a cycle recently."""
    if not last_poll_at:
        return False
    return (now - last_poll_at) > max_age_seconds


def webhook_needs_reregister(current_url: str | None, expected_url: str) -> bool:
    """True when Bale has no webhook (or a different host) than we expect."""
    if not expected_url:
        return False
    have = (current_url or "").strip()
    if not have:
        return True
    return have.rstrip("/") != expected_url.rstrip("/")
