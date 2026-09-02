"""Async engine/session factory with pool health settings and a circuit breaker."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.observability import metrics
from app.observability.logging import get_logger

logger = get_logger(__name__)

_SQLITE_BUSY_MARKERS = ("database is locked", "database table is locked", "sqlite_busy")


def is_sqlite_busy(exc: BaseException) -> bool:
    """True for a transient SQLite writer conflict, not a down database."""
    text = str(exc).lower()
    if any(marker in text for marker in _SQLITE_BUSY_MARKERS):
        return True
    origin = getattr(exc, "orig", None)
    if origin is not None and origin is not exc:
        return is_sqlite_busy(origin)
    cause = exc.__cause__
    if cause is not None and cause is not exc:
        return is_sqlite_busy(cause)
    return False


def is_connectivity_error(exc: BaseException) -> bool:
    """True for errors that indicate the database itself is unreachable."""
    if is_sqlite_busy(exc):
        return False
    if isinstance(exc, ConnectionError | OSError | TimeoutError):
        return True
    if isinstance(exc, OperationalError | InterfaceError):
        return True
    return bool(isinstance(exc, DBAPIError) and exc.connection_invalidated)


def _apply_sqlite_pragmas(dbapi_connection: object, _record: object) -> None:
    """WAL + busy timeout so readers do not fail writers immediately.

    File SQLite in DELETE journal mode serialises the whole file. Workers that
    used to hold a transaction open while calling the Bale API made ordinary
    button taps raise ``database is locked``, which was then shown to the user
    as a system outage.
    """
    raw = getattr(dbapi_connection, "_connection", dbapi_connection)
    sqlite_conn = getattr(raw, "_conn", raw)
    cursor = sqlite_conn.cursor()  # type: ignore[attr-defined]
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


_FAILURE_THRESHOLD = 5
_RECOVERY_SECONDS = 30.0


class CircuitBreaker:
    """Open after N consecutive DB failures; half-open after a cool-down."""

    def __init__(
        self,
        failure_threshold: int = _FAILURE_THRESHOLD,
        recovery_seconds: float = _RECOVERY_SECONDS,
    ) -> None:
        self._failures = 0
        self._threshold = failure_threshold
        self._recovery = recovery_seconds
        self._opened_at: float | None = None
        self._lock = asyncio.Lock()

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        # Half-open after the cool-down: allow the next attempt through.
        return time.monotonic() - self._opened_at < self._recovery

    async def record_success(self) -> None:
        async with self._lock:
            self._failures = 0
            if self._opened_at is not None:
                logger.info("db_circuit_closed")
                self._opened_at = None
                metrics.degraded_mode.set(0)

    async def record_failure(self) -> None:
        async with self._lock:
            self._failures += 1
            if self._failures >= self._threshold and self._opened_at is None:
                self._opened_at = time.monotonic()
                metrics.degraded_mode.set(1)
                logger.error("db_circuit_opened", failures=self._failures)


class Database:
    """Holds the engine, session factory and circuit breaker."""

    def __init__(
        self,
        url: str,
        pool_size: int = 10,
        max_overflow: int = 10,
        command_timeout: float = 10.0,
    ) -> None:
        engine_kwargs: dict[str, object] = {}
        if url.startswith("postgresql"):
            engine_kwargs.update(
                {
                    "pool_pre_ping": True,
                    "pool_recycle": 1800,
                    "pool_size": pool_size,
                    "max_overflow": max_overflow,
                    "connect_args": {"command_timeout": command_timeout},
                }
            )
        elif url.startswith("sqlite"):
            # SQLite (tests): shared connection for :memory:, generous lock
            # timeout for file-based concurrency tests.
            from sqlalchemy.pool import NullPool, StaticPool

            if ":memory:" in url:
                engine_kwargs.update({"poolclass": StaticPool})
            else:
                from pathlib import Path

                from sqlalchemy.engine.url import make_url

                db_path = make_url(url).database
                if db_path:
                    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
                engine_kwargs.update({"poolclass": NullPool, "connect_args": {"timeout": 30.0}})
        self.engine: AsyncEngine = create_async_engine(url, **engine_kwargs)
        if url.startswith("sqlite"):
            event.listen(self.engine.sync_engine, "connect", _apply_sqlite_pragmas)
        self.session_factory = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )
        self.breaker = CircuitBreaker()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a session inside a transaction; feeds the circuit breaker."""
        async with self.session_factory() as session:
            try:
                async with session.begin():
                    yield session
            except (ConnectionError, OSError, TimeoutError):
                await self.breaker.record_failure()
                raise
            except Exception as exc:
                # Only connectivity-class failures feed the breaker; logic
                # errors and SQLite BUSY must not open it.
                if is_connectivity_error(exc):
                    await self.breaker.record_failure()
                raise
            else:
                await self.breaker.record_success()

    async def dispose(self) -> None:
        await self.engine.dispose()
