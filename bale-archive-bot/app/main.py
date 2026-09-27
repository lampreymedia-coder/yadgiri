"""Entry point: preflight → polling loop → graceful shutdown.

* Runs only in polling mode (RUN_MODE=polling).
* The last update offset is kept in ``<DATA_DIR>/offset`` (a file, not the database).
* /healthz listens on 127.0.0.1:8000 only.
* If the read-only preflight fails, the bot does not start (exit code 78) and
  prints which command the owner must run. It never repairs anything itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import time

import uvicorn
from fastapi import FastAPI, Response

from app.bale.client import BaleClient
from app.bale.errors import BaleAPIError, NetworkError
from app.bale.methods import BaleAPI
from app.config import Settings, get_settings
from app.core.admins import AdminStore
from app.core.context import BotContext
from app.core.digest import maybe_send_daily_digest
from app.core.dispatcher import Dispatcher
from app.core.offset import OffsetStore
from app.core.ratelimit import OutboundRateLimiter
from app.core.signals import install_stop_signals
from app.core.watchdog import StallWatchdog
from app.db.session import Database
from app.handlers.wizard import expire_and_remind
from app.i18n import fa
from app.observability.health import health_payload
from app.observability.logging import configure_logging, get_logger
from app.preflight import format_report, run_preflight

logger = get_logger(__name__)

EXIT_CONFIG = 78  # systemd: RestartPreventExitStatus=78 — do not loop on a bad setup


class Application:
    def __init__(self, settings: Settings, api: BaleAPI | None = None) -> None:
        self.settings = settings
        if api is None:
            limiter = OutboundRateLimiter(
                settings.rate_global_rps,
                settings.rate_per_chat_per_sec,
                settings.rate_per_group_per_min,
            )
            api = BaleAPI(BaleClient(settings.bale_bot_token, settings.bale_api_base, limiter))
        self.api = api
        self.db = Database(settings.database_url, settings.db_pool_size, settings.db_max_overflow)
        self.ctx = BotContext(
            settings=settings,
            api=api,
            db=self.db,
            admins=AdminStore(settings.admins_file, settings.admin_user_ids),
        )
        self.dispatcher = Dispatcher(self.ctx)
        self.offsets = OffsetStore(settings.offset_file)
        self.stop_event = asyncio.Event()
        self.watchdog = StallWatchdog()
        self.last_poll_at = 0.0
        self._inflight: set[asyncio.Task[None]] = set()

    async def startup(self) -> None:
        try:
            me = await self.api.get_me()
            self.ctx.bot_username = me.username or ""
            self.ctx.bot_user_id = me.id
            logger.info("bot_identified", username=me.username, bot_id=me.id)
        except (BaleAPIError, NetworkError) as exc:
            logger.warning("get_me_failed", error=str(exc))
        with contextlib.suppress(BaleAPIError, NetworkError):
            await self.api.delete_webhook()
        try:
            await self.api.set_my_commands(fa.BOT_COMMANDS)
        except (BaleAPIError, NetworkError) as exc:
            logger.info("set_commands_failed", error=str(exc))
        if not self.ctx.admins.all:
            logger.warning("no_admins_configured")

    def _track(self, coro: object) -> None:
        task: asyncio.Task[None] = asyncio.create_task(coro)  # type: ignore[arg-type]
        self._inflight.add(task)
        task.add_done_callback(self._inflight.discard)

    async def _sleep(self, seconds: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self.stop_event.wait(), timeout=seconds)

    def _beat(self) -> None:
        self.watchdog.beat()
        self.last_poll_at = time.time()

    async def poll_once(self, offset: int | None) -> int | None:
        """One getUpdates round. Returns the next offset (saved to the file)."""
        try:
            updates = await asyncio.wait_for(
                self.api.get_updates(offset=offset, limit=100), timeout=30
            )
        except (TimeoutError, BaleAPIError, NetworkError) as exc:
            logger.warning("get_updates_failed", error=str(exc))
            self._beat()
            with contextlib.suppress(Exception):
                await self.api.client.reset()
            await self._sleep(self.settings.polling_idle_sleep)
            return offset
        self._beat()
        if not updates:
            await self._sleep(self.settings.polling_idle_sleep)
            return offset
        next_offset = max(update.update_id for update in updates) + 1
        self.offsets.save(next_offset)
        for update in updates:
            self._track(self.dispatcher.dispatch(update))
        await self._sleep(self.settings.polling_busy_sleep)
        return next_offset

    async def run_polling(self) -> None:
        offset = self.offsets.load()
        logger.info("polling_started", offset=offset)
        self.watchdog.start()
        self._beat()
        while not self.stop_event.is_set():
            offset = await self.poll_once(offset)
        logger.info("polling_stopped", offset=offset)

    async def run_sweeper(self) -> None:
        while not self.stop_event.is_set():
            await self._sleep(30)
            try:
                await expire_and_remind(self.ctx)
                await self.ctx.notifier.flush_due()
                await maybe_send_daily_digest(self.ctx)
            except Exception:
                logger.exception("sweeper_failed")

    def build_webapp(self) -> FastAPI:
        web = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

        @web.get("/healthz")
        async def healthz() -> Response:
            healthy, payload = await health_payload(self.ctx, self.last_poll_at)
            return Response(
                content=json.dumps(payload),
                media_type="application/json",
                status_code=200 if healthy else 503,
            )

        return web

    async def shutdown(self) -> None:
        logger.info("shutdown_started")
        self.watchdog.stop()
        await self.dispatcher.albums.drain()
        await self.ctx.notifier.flush_due(force=True)
        pending = self._inflight | self.ctx.background
        if pending:
            done, still = await asyncio.wait(pending, timeout=30)
            for task in still:
                task.cancel()
            logger.info("inflight_drained", done=len(done), cancelled=len(still))
        await self.api.client.close()
        await self.db.dispose()
        logger.info("shutdown_complete")


async def run(settings: Settings) -> int:
    checks = await run_preflight(settings.database_url)
    report = format_report(checks)
    print(report, flush=True)  # noqa: T201 — shown in journalctl for the owner
    if not all(check.ok for check in checks):
        logger.error("preflight_failed")
        return EXIT_CONFIG

    app = Application(settings)
    install_stop_signals(asyncio.get_running_loop(), app.stop_event.set)
    await app.startup()
    config = uvicorn.Config(
        app.build_webapp(), host=settings.http_host, port=settings.http_port, log_level="warning"
    )
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    sweeper = asyncio.create_task(app.run_sweeper())
    try:
        await app.run_polling()
    finally:
        app.stop_event.set()
        server.should_exit = True
        sweeper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sweeper
        with contextlib.suppress(Exception):
            await server_task
        await app.shutdown()
    return 0


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    logger.info("starting", run_mode=settings.run_mode)
    sys.exit(asyncio.run(run(settings)))


if __name__ == "__main__":
    main()
