"""Structured JSON logging with secret redaction.

The bot token appears in every API URL, so every log event passes through
a redaction processor before being rendered.
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

_TOKEN_RE = re.compile(r"/bot[0-9A-Za-z:_-]+")
_SECRET_KEY_RE = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|access[_-]?key)", re.IGNORECASE
)
_PHONE_RE = re.compile(r"\+?98\d{10}|09\d{9}")

_REDACTED = "[REDACTED]"


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        value = _TOKEN_RE.sub("/bot" + _REDACTED, value)
        return _PHONE_RE.sub(_REDACTED, value)
    if isinstance(value, dict):
        return {
            k: (_REDACTED if _SECRET_KEY_RE.search(str(k)) else _redact_value(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def redact_processor(
    logger: structlog.typing.WrappedLogger,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Redact tokens, secrets and phone numbers from every log event."""
    for key in list(event_dict.keys()):
        if _SECRET_KEY_RE.search(key):
            event_dict[key] = _REDACTED
        else:
            event_dict[key] = _redact_value(event_dict[key])
    return event_dict


def configure_logging(level: str = "INFO", log_format: str = "json") -> None:
    """Configure structlog + stdlib logging once at startup."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)
    # httpx logs the full URL (including the bot token) at INFO.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    renderer: structlog.typing.Processor
    if log_format == "json":
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False)
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.typing.FilteringBoundLogger:
    """Return a named bound logger."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
