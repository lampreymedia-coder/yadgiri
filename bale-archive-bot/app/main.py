"""Application entrypoint: polling or webhook mode.

Polling uses short GET getUpdates (no long-poll). Iranian NAT/DPI and Bale's
edge drop hung sockets; a 2s idle loop matches the original Bale docs.
On Windows the process is kept alive by NSSM.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from collections.abc import AsyncIterator
from typing import Any

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.bale.capabilities import probe_capabilities
from app.bale.client import BaleClient
from app.bale.errors import BaleAPIError, NetworkError
from app.bale.methods import BaleAPI
from app.bale.models import Update
from app.config import RunMode, Settings, get_settings
from app.core.context import BotContext
from app.core.dispatcher import Dispatcher
from app.core.ratelimit import OutboundRateLimiter
from app.db.session import Database
from app.observability import metrics as app_metrics
from app.observability.health import health_payload
from app.observability.logging import configure_logging, get_logger
from app.workers.digest import run_weekly_digest
from app.workers.media_worker import build_storage, run_media_once
from app.workers.outbox import run_outbox_once
from app.workers.ttl_sweeper import run_expiry_once, run_nightly_cleanup, run_reminders_once

logger = get_logger(__name__)

_WEBHOOK_BODY_LIMIT = 20 * 1024 * 1024


class Application:
    """Owns the runtime: context, dispatcher, scheduler and shutdown."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        limiter = OutboundRateLimiter(
            settings.rate_global_rps,
            settings.rate_per_chat_per_sec,
            settings.rate_per_group_per_min,
        )
        client = BaleClient(settings.bale_bot_token, settings.bale_api_base, limiter)
        self.api = BaleAPI(client)
        self.db = Database(settings.database_url, settings.db_pool_size, settings.db_max_overflow)
        self.ctx: BotContext | None = None
        self.dispatcher: Dispatcher | None = None
        self.scheduler = AsyncIOScheduler(timezone=settings.tz)
        self.stop_event = asyncio.Event()
        self.started_event = asyncio.Event()
        self._inflight: set[asyncio.Task[None]] = set()

    async def startup(self) -> None:
        from app.bale.capabilities import Capabilities

        caps = Capabilities()
        try:
            caps = await probe_capabilities(self.api)
        except (BaleAPIError, NetworkError) as exc:
            logger.warning("capability_probe_failed", error=str(exc))

        self.ctx = BotContext(settings=self.settings, api=self.api, db=self.db, caps=caps)
        await self._prepare_store()
        try:
            me = await self.api.get_me()
            self.ctx.bot_username = me.username or ""
            self.ctx.bot_user_id = me.id
            logger.info("bot_identified", username=me.username, bot_id=me.id)
        except (BaleAPIError, NetworkError) as exc:
            logger.warning("get_me_failed", error=str(exc))

        self.dispatcher = Dispatcher(self.ctx)
        self._register_jobs()
        self.scheduler.start()

        if self.ctx.archive_chat_id is not None:
            try:
                await self.api.get_chat(self.ctx.archive_chat_id)
            except (BaleAPIError, NetworkError) as exc:
                logger.warning("archive_chat_check_failed", error=str(exc))

        self.started_event.set()

    async def _prepare_store(self) -> None:
        """Create tables (sqlite), seed tags, restore runtime settings."""
        assert self.ctx is not None
        if self.settings.database_url.startswith("sqlite"):
            from app.db.base import Base

            async with self.db.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        from app.db.repositories.misc import AppSettingsRepository
        from app.db.repositories.tags import TagRepository
        from app.db.repositories.users import UserRepository
        from app.i18n.fa import SEED_TAGS

        async with self.db.session() as session:
            tags = TagRepository(session)
            for slug, title_fa, hashtag in SEED_TAGS:
                if await tags.get_by_slug(slug) is None:
                    await tags.create(slug=slug, title_fa=title_fa, hashtag=hashtag)
            stored = AppSettingsRepository(session)
            archive_id = await stored.get("archive_chat_id")
            notify_id = await stored.get("admin_notify_chat_id")
            owner_id = await stored.get("owner_user_id")
            if archive_id is not None:
                self.ctx.archive_chat_id = int(archive_id)
            if notify_id is not None:
                self.ctx.admin_notify_chat_id = int(notify_id)
            if owner_id is not None:
                self.ctx.runtime_admin_ids.add(int(owner_id))
            users = UserRepository(session)
            for admin_user in await users.list_admins():
                self.ctx.runtime_admin_ids.add(admin_user.bale_user_id)
        logger.info(
            "store_ready",
            archive_chat_id=self.ctx.archive_chat_id,
            admins=len(self.ctx.runtime_admin_ids),
        )

    def _register_jobs(self) -> None:
        assert self.ctx is not None
        ctx = self.ctx
        storage = build_storage(ctx)
        self.scheduler.add_job(
            run_outbox_once, IntervalTrigger(seconds=30), args=[ctx], max_instances=1
        )
        self.scheduler.add_job(
            run_media_once, IntervalTrigger(seconds=20), args=[ctx, storage], max_instances=1
        )
        self.scheduler.add_job(
            run_reminders_once, IntervalTrigger(seconds=60), args=[ctx], max_instances=1
        )
        self.scheduler.add_job(
            run_expiry_once, IntervalTrigger(seconds=60), args=[ctx], max_instances=1
        )
        self.scheduler.add_job(
            run_nightly_cleanup, CronTrigger(hour=3, minute=30), args=[ctx], max_instances=1
        )
        self.scheduler.add_job(
            run_weekly_digest,
            CronTrigger(day_of_week="thu", hour=20, minute=0),
            args=[ctx],
            max_instances=1,
        )
        assert self.dispatcher is not None
        self.scheduler.add_job(
            self.dispatcher.process_spool, IntervalTrigger(seconds=60), max_instances=1
        )

    async def shutdown(self) -> None:
        """Graceful: stop intake, drain in-flight work (≤30s), close pools."""
        logger.info("shutdown_started")
        self.stop_event.set()
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        if self.dispatcher is not None:
            await self.dispatcher.albums.drain()
        if self._inflight:
            done, pending = await asyncio.wait(self._inflight, timeout=30)
            for task in pending:
                task.cancel()
            logger.info("inflight_drained", done=len(done), cancelled=len(pending))
        await self.api.client.close()
        await self.db.dispose()
        logger.info("shutdown_complete")

    async def _prepare_polling(self) -> None:
        try:
            await self.api.delete_webhook()
            logger.info("webhook_deleted")
        except (BaleAPIError, NetworkError) as exc:
            logger.warning("delete_webhook_failed", error=str(exc))
            try:
                await self.api.set_webhook("")
            except (BaleAPIError, NetworkError) as inner:
                logger.warning("webhook_clear_failed", error=str(inner))
        try:
            info = await self.api.get_webhook_info()
            logger.info(
                "webhook_info",
                url=info.url or "",
                pending=info.pending_update_count,
            )
        except (BaleAPIError, NetworkError) as exc:
            logger.warning("webhook_info_failed", error=str(exc))
        try:
            ok = await self.api.set_my_commands(
                [
                    {"command": "start", "description": "فعال‌سازی ربات"},
                    {"command": "archive", "description": "این گروه آرشیو خصوصی شود"},
                    {"command": "help", "description": "راهنما"},
                    {"command": "panel", "description": "منوی مدیریت"},
                ]
            )
            logger.info("commands_registered", ok=ok)
        except (BaleAPIError, NetworkError) as exc:
            logger.warning("commands_register_failed", error=str(exc))

    async def _notify_owner_ready(self) -> None:
        """Tell the owner the process is live — also proves private sendMessage works."""
        assert self.ctx is not None
        from app.bale.keyboards import keyboard, url_button
        from app.i18n import fa

        owner_id = next(iter(self.ctx.runtime_admin_ids), None)
        if owner_id is None:
            owner_id = self.ctx.admin_notify_chat_id
        if owner_id is None:
            return
        markup = None
        if self.ctx.bot_username:
            markup = keyboard(
                [
                    [
                        url_button(
                            fa.BTN_ADD_TO_GROUP,
                            f"https://ble.ir/{self.ctx.bot_username}?startgroup=start",
                        )
                    ]
                ]
            )
        try:
            await self.api.send_message(owner_id, fa.BOT_READY_PING, markup)
            logger.info("owner_ready_ping_sent", chat_id=owner_id)
        except (BaleAPIError, NetworkError) as exc:
            logger.warning("owner_ready_ping_failed", chat_id=owner_id, error=str(exc))

    def _track(self, coro: Any) -> asyncio.Task[None]:
        task: asyncio.Task[None] = asyncio.create_task(coro)
        self._inflight.add(task)
        task.add_done_callback(self._inflight.discard)
        return task

    # ─── Polling ───

    async def run_polling(self) -> None:
        """Short-interval GET polling. Offset is only advanced from live replies.

        Never restore a stored offset: a stale high offset confirms (drops)
        newer updates whose ids restarted, which Bale does after idle gaps.
        Duplicate delivery is already handled by claim_update.
        """
        assert self.dispatcher is not None
        offset: int | None = None

        await self._prepare_polling()
        await self._notify_owner_ready()
        logger.info("polling_started", offset=offset)
        empty_cycles = 0
        while not self.stop_event.is_set():
            try:
                updates = await asyncio.wait_for(
                    self.api.get_updates(offset=offset, limit=100),
                    timeout=30,
                )
            except TimeoutError:
                logger.warning("get_updates_watchdog")
                await self._reset_http()
                await self._sleep(self.settings.polling_idle_sleep)
                continue
            except (BaleAPIError, NetworkError) as exc:
                logger.warning("get_updates_failed", error=str(exc))
                await self._reset_http()
                await self._sleep(self.settings.polling_idle_sleep)
                continue

            if updates:
                empty_cycles = 0
                offset = max(u.update_id for u in updates) + 1
                for update in updates:
                    if self.stop_event.is_set():
                        break
                    task = self._track(self.dispatcher.dispatch(update))
                    await task
                await self._sleep(self.settings.polling_busy_sleep)
            else:
                empty_cycles += 1
                if empty_cycles == 1 or empty_cycles % 30 == 0:
                    logger.info("polling_idle", offset=offset, empty_cycles=empty_cycles)
                await self._sleep(self.settings.polling_idle_sleep)
        logger.info("polling_stopped", offset=offset)

    async def _reset_http(self) -> None:
        try:
            await self.api.client.reset()
        except Exception as exc:  # noqa: BLE001
            logger.warning("http_reset_failed", error=str(exc))

    async def _sleep(self, seconds: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self.stop_event.wait(), timeout=seconds)

    # ─── Webhook (FastAPI) ───

    def build_webapp(self) -> FastAPI:
        settings = self.settings
        app_instance = self

        @contextlib.asynccontextmanager
        async def lifespan(_: FastAPI) -> AsyncIterator[None]:
            await app_instance.startup()
            if settings.run_mode is RunMode.WEBHOOK:
                try:
                    await app_instance.api.set_webhook(settings.webhook_url)
                    logger.info("webhook_registered")
                except (BaleAPIError, NetworkError) as exc:
                    logger.error("webhook_registration_failed", error=str(exc))
            yield
            await app_instance.shutdown()

        web = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

        @web.get("/healthz")
        async def healthz() -> Response:
            assert app_instance.ctx is not None
            healthy, payload = await health_payload(app_instance.ctx)
            import json

            return Response(
                content=json.dumps(payload),
                media_type="application/json",
                status_code=200 if healthy else 503,
            )

        if settings.metrics_enabled:

            @web.get("/metrics")
            async def metrics_endpoint() -> Response:
                return Response(
                    content=generate_latest(app_metrics.registry),
                    media_type=CONTENT_TYPE_LATEST,
                )

        if settings.run_mode is RunMode.WEBHOOK:

            @web.post(settings.webhook_path)
            async def webhook(request: Request) -> Response:
                body = await request.body()
                if len(body) > _WEBHOOK_BODY_LIMIT:
                    return Response(status_code=413)
                try:
                    update = Update.model_validate_json(body)
                except ValueError:
                    logger.warning("webhook_invalid_body")
                    return Response(status_code=200)
                assert app_instance.dispatcher is not None
                app_instance._track(app_instance.dispatcher.dispatch(update))
                return Response(status_code=200)

        return web


async def _run_polling_mode(app_instance: Application) -> None:
    """Polling mode still serves /healthz and /metrics on port 8000."""
    web = app_instance.build_webapp()
    config = uvicorn.Config(web, host="0.0.0.0", port=8000, log_level="warning")  # noqa: S104
    server = uvicorn.Server(config)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, app_instance.stop_event.set)

    server_task = asyncio.create_task(server.serve())
    # Wait for startup() inside lifespan before polling begins.
    startup_wait = asyncio.create_task(app_instance.started_event.wait())
    await asyncio.wait({server_task, startup_wait}, return_when=asyncio.FIRST_COMPLETED)
    if not startup_wait.done():
        startup_wait.cancel()
    if app_instance.dispatcher is not None:
        await app_instance.run_polling()
    server.should_exit = True
    await server_task


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    app_instance = Application(settings)

    if settings.run_mode is RunMode.POLLING:
        asyncio.run(_run_polling_mode(app_instance))
    else:
        web = app_instance.build_webapp()
        uvicorn.run(web, host="0.0.0.0", port=8000, log_level="warning")  # noqa: S104


if __name__ == "__main__":
    main()
