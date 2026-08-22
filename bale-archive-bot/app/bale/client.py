"""Low-level Bale API client: timeouts, retry/backoff and rate limiting.

Every request goes through :meth:`BaleClient.request` which:

* acquires the outbound token-bucket limiter (global / per-chat / per-group),
* enforces an explicit timeout on every network call,
* honours ``retry_after`` on 429,
* retries 5xx / network errors with exponential backoff + jitter (max 5),
* never retries other 4xx errors.

Traffic stays on ``tapi.bale.ai`` only. Request shape matches the official
Iranian ``python-bale-bot`` library so Bale's edge does not treat the bot as a
foreign scraper (User-Agent, GET for read methods, IPv4, short-lived calls).
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any, Protocol

import httpx

from app.bale.errors import (
    BadRequest,
    BaleAPIError,
    NetworkError,
    RateLimited,
    ServerError,
    error_for,
)
from app.observability import metrics
from app.observability.logging import get_logger

logger = get_logger(__name__)

# Official python-bale-bot User-Agent. httpx's default "python-httpx/…" is a
# common WAF deny/empty-getUpdates signature on Iranian edges.
BALE_USER_AGENT = (
    "python-bale-bot (https://python-bale-bot.ir): An API wrapper for Bale written in Python"
)

# python-bale-bot + Bale staff: these methods are GET. Query-string GET also
# survives Iranian proxies that strip JSON bodies on GET.
_GET_QUERY_METHODS = frozenset(
    {
        "getMe",
        "getUpdates",
        "getWebhookInfo",
        "deleteWebhook",
        "getChat",
        "getChatMembersCount",
        "leaveChat",
        "deleteMessage",
        "getChatAdministrators",
        "getChatMember",
        "inviteUser",
    }
)

_MAX_ATTEMPTS = 5
_BACKOFF_BASE_SECONDS = 1.0
_DEFAULT_RETRY_AFTER = 5.0


class OutboundLimiter(Protocol):
    """Interface for the outbound rate limiter (implemented in app.core.ratelimit)."""

    async def acquire(self, chat_id: int | None, is_group: bool) -> None:
        """Block until a request to ``chat_id`` is allowed."""


class NullLimiter:
    """No-op limiter used when none is provided (tests, scripts)."""

    async def acquire(self, chat_id: int | None, is_group: bool) -> None:
        return


class BaleClient:
    """Async HTTP client for ``https://tapi.bale.ai/bot<TOKEN>/<METHOD>``."""

    def __init__(
        self,
        token: str,
        base_url: str = "https://tapi.bale.ai",
        limiter: OutboundLimiter | None = None,
        request_timeout: float = 25.0,
        connect_timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = token
        self._base = base_url.rstrip("/")
        self._limiter: OutboundLimiter = limiter if limiter is not None else NullLimiter()
        self._request_timeout = request_timeout
        self._connect_timeout = connect_timeout
        self._transport = transport
        self._http = self._make_http()

    def _make_http(self) -> httpx.AsyncClient:
        timeout = httpx.Timeout(
            self._request_timeout,
            connect=self._connect_timeout,
            read=self._request_timeout,
            write=20.0,
            pool=20.0,
        )
        headers = {
            "User-Agent": BALE_USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "fa-IR,fa;q=0.9",
        }
        if self._transport is not None:
            return httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=False,
                transport=self._transport,
                headers=headers,
            )
        # IPv4 only: IPv6 to tapi.bale.ai often hangs on mixed/filtered networks.
        return httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            transport=httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=0),  # noqa: S104
            headers=headers,
        )

    async def reset(self) -> None:
        """Drop a stalled TLS session (NAT/DPI idle-kill) and open a fresh one."""
        try:
            await self._http.aclose()
        except Exception:  # noqa: BLE001 — close must not block reconnect
            logger.info("http_client_close_failed")
        self._http = self._make_http()

    @property
    def file_base_url(self) -> str:
        return f"{self._base}/file/bot{self._token}"

    def method_url(self, method: str) -> str:
        return f"{self._base}/bot{self._token}/{method}"

    async def close(self) -> None:
        await self._http.aclose()

    @staticmethod
    def _normalize_payload(params: dict[str, Any] | None) -> dict[str, Any]:
        """Shape a payload the way the official Bale libraries do.

        python-bale-bot always sends ``chat_id`` as a string and
        ``reply_markup`` as a JSON *string* (double-encoded). Sending a nested
        object or a numeric chat_id is what produced ``404 no such group or
        user`` against real groups even when the bot had just received a
        message from that same chat.
        """
        payload: dict[str, Any] = {}
        for key, value in (params or {}).items():
            if value is None:
                continue
            if key in {"chat_id", "from_chat_id"}:
                payload[key] = str(value)
            elif key == "reply_markup" and isinstance(value, dict):
                payload[key] = json.dumps(value, ensure_ascii=False)
            else:
                payload[key] = value
        return payload

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        chat_id: int | None = None,
        is_group: bool = False,
        max_attempts: int = _MAX_ATTEMPTS,
        use_form: bool = False,
        force_post: bool = False,
    ) -> Any:
        """Call a Bale API method and return the ``result`` payload."""
        payload = self._normalize_payload(params)
        last_error: Exception | None = None
        use_get = files is None and not use_form and not force_post and method in _GET_QUERY_METHODS

        for attempt in range(1, max_attempts + 1):
            await self._limiter.acquire(chat_id, is_group)
            started = time.monotonic()
            try:
                if files:
                    response = await self._http.post(
                        self.method_url(method), data=payload, files=files
                    )
                elif use_form:
                    form = {
                        key: value if isinstance(value, str) else json.dumps(value)
                        for key, value in payload.items()
                    }
                    response = await self._http.post(self.method_url(method), data=form)
                elif use_get:
                    response = await self._http.get(
                        self.method_url(method), params=self._query_payload(payload)
                    )
                else:
                    response = await self._http.post(self.method_url(method), json=payload)
                body = response.json()
            except (httpx.TimeoutException, httpx.TransportError, ValueError) as exc:
                last_error = NetworkError(method, exc)
                metrics.api_requests.labels(method=method, outcome="network_error").inc()
                logger.warning(
                    "bale_api_network_error", method=method, attempt=attempt, error=str(exc)
                )
                await self._sleep_backoff(attempt)
                continue
            finally:
                metrics.api_request_seconds.labels(method=method).observe(
                    time.monotonic() - started
                )

            if body.get("ok"):
                metrics.api_requests.labels(method=method, outcome="ok").inc()
                return body.get("result")

            error_code = int(body.get("error_code", response.status_code or 0))
            description = str(body.get("description", ""))
            retry_after = self._extract_retry_after(body)
            error = error_for(method, error_code, description, retry_after)

            if isinstance(error, RateLimited):
                metrics.api_requests.labels(method=method, outcome="rate_limited").inc()
                logger.warning(
                    "bale_api_rate_limited",
                    method=method,
                    attempt=attempt,
                    retry_after=error.retry_after,
                )
                last_error = error
                await asyncio.sleep(error.retry_after)
                continue
            if isinstance(error, ServerError):
                metrics.api_requests.labels(method=method, outcome="server_error").inc()
                logger.warning(
                    "bale_api_server_error",
                    method=method,
                    attempt=attempt,
                    error_code=error_code,
                    description=description,
                )
                last_error = error
                await self._sleep_backoff(attempt)
                continue

            # Non-retryable 4xx: raise immediately.
            metrics.api_requests.labels(method=method, outcome="client_error").inc()
            logger.warning(
                "bale_api_client_error",
                method=method,
                error_code=error_code,
                description=description,
                chat_id=payload.get("chat_id"),
                param_keys=sorted(payload.keys()),
                form=use_form,
            )
            raise error

        assert last_error is not None
        metrics.api_requests.labels(method=method, outcome="exhausted").inc()
        logger.error("bale_api_retries_exhausted", method=method, error=str(last_error))
        raise last_error

    async def download_file(self, file_path: str, max_bytes: int) -> bytes:
        """Download a file by ``file_path``; raises ``BadRequest`` if larger than allowed."""
        url = f"{self.file_base_url}/{file_path}"
        last_error: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                async with self._http.stream("GET", url) as response:
                    if response.status_code >= 500:
                        last_error = ServerError(
                            "getFileContent", response.status_code, "download failed"
                        )
                        await self._sleep_backoff(attempt)
                        continue
                    if response.status_code >= 400:
                        raise BadRequest(
                            "getFileContent", response.status_code, "download rejected"
                        )
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise BadRequest(
                                "getFileContent", 413, f"file exceeds {max_bytes} bytes"
                            )
                        chunks.append(chunk)
                    return b"".join(chunks)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = NetworkError("getFileContent", exc)
                await self._sleep_backoff(attempt)
        assert last_error is not None
        raise last_error

    @staticmethod
    def _extract_retry_after(body: dict[str, Any]) -> float | None:
        parameters = body.get("parameters")
        if isinstance(parameters, dict):
            value = parameters.get("retry_after")
            if isinstance(value, int | float):
                return float(value)
        return None

    @staticmethod
    def _query_payload(payload: dict[str, Any]) -> dict[str, str]:
        query: dict[str, str] = {}
        for key, value in payload.items():
            if isinstance(value, dict | list):
                query[key] = json.dumps(value, ensure_ascii=False)
            else:
                query[key] = str(value)
        return query

    @staticmethod
    async def _sleep_backoff(attempt: int) -> None:
        delay = _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
        delay = min(delay, 16.0) + random.uniform(0.0, 0.5)
        await asyncio.sleep(delay)


__all__ = ["BaleAPIError", "BaleClient", "NullLimiter", "OutboundLimiter"]
