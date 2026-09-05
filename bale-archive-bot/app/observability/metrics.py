"""Prometheus metrics registry for the bot."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

registry = CollectorRegistry()

updates_received = Counter(
    "bot_updates_received_total",
    "Number of updates received from Bale",
    ["kind"],
    registry=registry,
)
updates_duplicated = Counter(
    "bot_updates_duplicated_total",
    "Updates skipped because they were already processed",
    registry=registry,
)
api_requests = Counter(
    "bot_api_requests_total",
    "Outgoing Bale API requests",
    ["method", "outcome"],
    registry=registry,
)
api_request_seconds = Histogram(
    "bot_api_request_seconds",
    "Latency of Bale API requests",
    ["method"],
    registry=registry,
)
submissions_total = Counter(
    "bot_submissions_total",
    "Submissions by final status",
    ["status"],
    registry=registry,
)
outbox_pending = Gauge(
    "bot_outbox_pending",
    "Pending outbox rows",
    registry=registry,
)
handler_errors = Counter(
    "bot_handler_errors_total",
    "Unhandled errors caught by the global error handler",
    ["where"],
    registry=registry,
)
degraded_mode = Gauge(
    "bot_degraded_mode",
    "1 when the database circuit breaker is open (spool mode)",
    registry=registry,
)
