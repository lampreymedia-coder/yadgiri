"""Typed errors for the Bale API client."""

from __future__ import annotations


class BaleAPIError(Exception):
    """Base error for any non-ok Bale API response."""

    def __init__(self, method: str, error_code: int, description: str) -> None:
        self.method = method
        self.error_code = error_code
        self.description = description
        super().__init__(f"{method} failed: [{error_code}] {description}")


class BadRequest(BaleAPIError):
    """400 — invalid parameters; never retried."""


class Unauthorized(BaleAPIError):
    """401 — token invalid."""


class Forbidden(BaleAPIError):
    """403 — bot blocked by user / missing permission / not a member."""


class NotFound(BaleAPIError):
    """404 — chat or message not found (also unknown method)."""


class RateLimited(BaleAPIError):
    """429 — too many requests. ``retry_after`` is seconds to wait."""

    def __init__(self, method: str, error_code: int, description: str, retry_after: float) -> None:
        super().__init__(method, error_code, description)
        self.retry_after = retry_after


class ServerError(BaleAPIError):
    """5xx — transient server error; retried with backoff."""


class NetworkError(Exception):
    """Timeout / connection failure; retried with backoff."""

    def __init__(self, method: str, cause: Exception) -> None:
        self.method = method
        self.cause = cause
        super().__init__(f"{method} network failure: {cause!r}")


def error_for(
    method: str, error_code: int, description: str, retry_after: float | None
) -> BaleAPIError:
    """Map an error_code to the matching typed exception."""
    if error_code == 400:
        return BadRequest(method, error_code, description)
    if error_code == 401:
        return Unauthorized(method, error_code, description)
    if error_code == 403:
        return Forbidden(method, error_code, description)
    if error_code == 404:
        return NotFound(method, error_code, description)
    if error_code == 429:
        return RateLimited(method, error_code, description, retry_after if retry_after else 5.0)
    if error_code >= 500:
        return ServerError(method, error_code, description)
    return BaleAPIError(method, error_code, description)
