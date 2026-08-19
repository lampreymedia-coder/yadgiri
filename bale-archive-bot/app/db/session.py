"""Async engine/session factory with pool health settings and a circuit breaker."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.observability import metrics
from app.observability.logging import get_logger

logger = get_logger(__name__)

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
        engine_kwargs: dict[str, object] = {
            "pool_pre_ping": True,
            "pool_recycle": 1800,
        }
        if url.startswith("postgresql"):
            engine_kwargs.update(
                {
                    "pool_size": pool_size,
                    "max_overflow": max_overflow,
                    "connect_args": {"command_timeout": command_timeout},
                }
            )
        self.engine: AsyncEngine = create_async_engine(url, **engine_kwargs)
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
                # Driver-level disconnects surface as DBAPI errors of various
                # types; classify by module rather than swallowing anything.
                if type(exc).__module__.startswith(("asyncpg", "sqlalchemy")):
                    await self.breaker.record_failure()
                raise
            else:
                await self.breaker.record_success()

    async def dispose(self) -> None:
        await self.engine.dispose()
