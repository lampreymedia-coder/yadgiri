"""Update routing: idempotency → lock → handler, with a global error net.

No exception ever escapes :meth:`Dispatcher.dispatch`; the polling loop and
webhook endpoint stay alive no matter what a handler does.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from app.bale.errors import BaleAPIError, NetworkError
from app.bale.keyboards import CallbackDataError, parse_callback
from app.bale.models import CallbackQuery, Message, Update
from app.core.albums import AlbumBuffer
from app.core.context import BotContext
from app.core.fsm import WizardState
from app.core.idempotency import claim_update
from app.domain.classify import normalize_fa
from app.handlers import admin, group_intake, user_commands, wizard
from app.handlers.errors import handle_update_error
from app.i18n import fa
from app.observability import metrics
from app.observability.logging import get_logger

logger = get_logger(__name__)

# Whole-message Persian aliases so non-technical users need not type /archive.
_PERSIAN_COMMANDS = {
    "ارشیو": "archive",
    "ارشیوم": "archive",
    "بایگانی": "archive",
    "بایگانیخصوصی": "archive",
}


def parse_command(text: str) -> tuple[str, list[str]] | None:
    """Parse '/cmd arg1 arg2' or a Persian alias such as «آرشیو»."""
    stripped = (text or "").strip()
    if not stripped:
        return None
    if stripped.startswith("/"):
        parts = stripped.split()
        command = parts[0][1:].split("@")[0].lower()
        return command, parts[1:]
    first = normalize_fa(stripped.split()[0]).replace(" ", "")
    mapped = _PERSIAN_COMMANDS.get(first)
    if mapped is not None:
        return mapped, stripped.split()[1:]
    return None


class Dispatcher:
    def __init__(self, ctx: BotContext) -> None:
        self.ctx = ctx
        self.albums = AlbumBuffer(self._flush_group_batch, window_ms=ctx.settings.album_window_ms)
        self._spool_dir = Path(ctx.settings.spool_dir)

    async def _flush_group_batch(self, messages: list[Message]) -> None:
        await group_intake.process_group_batch(self.ctx, messages)

    async def dispatch(self, update: Update) -> None:
        """Process one update; never raises."""
        metrics.updates_received.labels(kind=update.kind).inc()
        try:
            await self._dispatch_inner(update)
        except Exception as exc:
            from app.db.session import is_connectivity_error

            if is_connectivity_error(exc):
                await self._handle_infra_failure(update, exc)
            else:
                await handle_update_error(self.ctx, update, exc)

    async def _handle_infra_failure(self, update: Update, exc: Exception) -> None:
        """Database unavailable: spool the raw update to disk, tell the user."""
        logger.error("infra_failure_spooling", update_id=update.update_id, error=str(exc))
        try:
            self._spool_dir.mkdir(parents=True, exist_ok=True)
            path = self._spool_dir / f"{update.update_id}_{int(time.time())}.json"
            path.write_text(json.dumps(update.raw(), ensure_ascii=False), encoding="utf-8")
        except OSError as spool_error:
            logger.error("spool_write_failed", error=str(spool_error))
        chat_id: int | None = None
        if update.message is not None:
            chat_id = update.message.chat.id
        elif update.callback_query is not None and update.callback_query.message is not None:
            chat_id = update.callback_query.message.chat.id
        if chat_id is not None:
            try:
                await self.ctx.api.send_message(chat_id, fa.ERR_DEGRADED)
            except (BaleAPIError, NetworkError) as send_error:
                logger.warning("degraded_notice_failed", error=str(send_error))

    async def _dispatch_inner(self, update: Update) -> None:
        if update.message is not None:
            message = update.message
            logger.info(
                "update_received",
                update_id=update.update_id,
                kind=update.kind,
                chat_id=message.chat.id,
                chat_type=message.chat.type,
                message_id=message.message_id,
                from_id=message.from_user.id if message.from_user else None,
                text_preview=(message.text or message.caption or "")[:80],
                added_members=len(message.added_members()),
                has_voice=message.voice is not None,
                has_audio=message.audio is not None,
                has_document=message.document is not None,
                has_video_note=message.video_note is not None,
            )
        elif update.callback_query is not None:
            logger.info(
                "update_received",
                update_id=update.update_id,
                kind=update.kind,
                data=update.callback_query.data,
            )
        else:
            logger.info("update_received", update_id=update.update_id, kind=update.kind)

        async with self.ctx.db.session() as session:
            if not await claim_update(session, update.update_id):
                return

        if update.message is not None:
            await self._on_message(update.message)
        elif update.edited_message is not None:
            logger.info(
                "edited_message_ignored",
                chat_id=update.edited_message.chat.id,
                message_id=update.edited_message.message_id,
            )
        elif update.callback_query is not None:
            await self._on_callback(update.callback_query)

    async def _on_message(self, message: Message) -> None:
        if message.added_members() or message.left_chat_member or message.group_chat_created:
            await group_intake.register_group_events(self.ctx, message)
            return
        if message.from_user is not None and message.from_user.is_bot:
            return

        if message.from_user is None:
            if not message.is_private_message:
                await group_intake.process_group_batch(self.ctx, [message])
            return

        user_id = message.from_user.id
        lock = self.ctx.locks.get(message.chat.id, user_id)
        # Group content must not be dropped while another update holds the lock.
        if (
            message.is_private_message
            and lock.locked()
            and parse_command(message.text or "") is None
        ):
            try:
                await self.ctx.api.send_message(message.chat.id, fa.ERR_BUSY)
            except (BaleAPIError, NetworkError) as exc:
                logger.info("busy_notice_failed", error=str(exc))
            return

        async with lock:
            if message.is_private_message:
                await self._on_private_message(message)
            else:
                await self._on_group_message(message)

    async def _on_private_message(self, message: Message) -> None:
        text = message.text or ""
        command = parse_command(text)
        if command is not None:
            await self._on_command(message, command[0], command[1])
            return

        assert message.from_user is not None
        async with self.ctx.db.session() as session:
            store = self.ctx.state_store(session)
            conversation = await store.load(message.chat.id, message.from_user.id)
            if conversation is not None and conversation.state is WizardState.AWAITING_NOTE:
                await wizard.handle_note_input(self.ctx, session, message, conversation)
                return
            if (
                conversation is not None
                and conversation.state is WizardState.ADMIN_INPUT
                and await admin.is_admin(self.ctx, session, message.from_user.id)
            ):
                await admin.handle_admin_input(self.ctx, session, message, conversation)
                return

        await group_intake.process_private_content(self.ctx, message)

    async def _on_group_message(self, message: Message) -> None:
        text = message.text or ""
        command = parse_command(text)
        mention_tokens: set[str] = set()
        if self.ctx.bot_username:
            name = self.ctx.bot_username.lower()
            mention_tokens = {f"@{name}", name}
        if command is None and (text or "").strip().lower() in mention_tokens:
            await group_intake.handle_group_hello(self.ctx, message)
            return
        if command is not None:
            await self._on_command(message, command[0], command[1])
            return
        if group_intake._should_ignore(self.ctx, message):
            return
        await self.albums.add(message)

    async def _on_command(self, message: Message, command: str, args: list[str]) -> None:
        assert message.from_user is not None

        if command == "start":
            if message.is_private_message:
                await user_commands.handle_start(self.ctx, message)
            else:
                await group_intake.handle_group_hello(self.ctx, message)
            return
        if command == "help":
            await user_commands.handle_help(self.ctx, message)
            return
        if command == "my" and message.is_private_message:
            await user_commands.handle_my(self.ctx, message)
            return
        if command == "undo":
            await user_commands.handle_undo(self.ctx, message, args)
            return
        if command == "resume" and message.is_private_message:
            await user_commands.handle_resume(self.ctx, message)
            return

        async with self.ctx.db.session() as session:
            authorized = await admin.is_admin(self.ctx, session, message.from_user.id)
            if command in {"onboard", "archive"} and not message.is_private_message:
                if not authorized:
                    authorized = await admin.promote_first_owner(
                        self.ctx, session, message.from_user
                    )
                if authorized:
                    if command == "onboard":
                        await admin.handle_onboard(self.ctx, message)
                    else:
                        await admin.handle_set_archive(self.ctx, session, message)
                elif command == "archive":
                    try:
                        await self.ctx.api.send_message(
                            message.from_user.id, fa.ARCHIVE_SET_NEED_PRIVATE
                        )
                    except (BaleAPIError, NetworkError) as exc:
                        logger.info("archive_need_private_dm_failed", error=str(exc))
                return
            if not authorized or not admin.admin_chat_allowed(self.ctx, message):
                if message.is_private_message:
                    await self.ctx.api.send_message(message.chat.id, fa.ERR_UNKNOWN_COMMAND)
                return
            await self._on_admin_command(session, message, command, args)

    async def _on_admin_command(
        self, session: object, message: Message, command: str, args: list[str]
    ) -> None:
        from sqlalchemy.ext.asyncio import AsyncSession

        assert isinstance(session, AsyncSession)
        assert message.from_user is not None
        ctx = self.ctx
        chat_id = message.chat.id
        actor = message.from_user.id

        if command == "panel":
            await admin.send_panel(ctx, chat_id)
        elif command == "stats":
            await admin.send_stats(ctx, session, chat_id, args)
        elif command == "top_users":
            await admin.send_top_users(ctx, session, chat_id, args)
        elif command == "top_tags":
            await admin.send_top_tags(ctx, session, chat_id, args)
        elif command == "tag":
            await admin.send_tag_browse(ctx, session, chat_id, args)
        elif command == "type":
            await admin.send_type_report(ctx, session, chat_id, args)
        elif command == "user":
            await admin.send_user_report(ctx, session, chat_id, args)
        elif command == "search":
            await admin.send_search(ctx, session, chat_id, args)
        elif command == "get":
            await admin.send_get(ctx, session, chat_id, args)
        elif command == "export":
            await admin.send_export(ctx, session, chat_id, args)
        elif command == "tags":
            await admin.send_tags_list(ctx, session, chat_id)
        elif command == "addtag":
            await admin.start_addtag_flow(ctx, session, message)
        elif command == "edittag":
            await admin.handle_edittag(ctx, session, chat_id, args, actor)
        elif command == "disabletag":
            await admin.handle_disabletag(ctx, session, chat_id, args)
        elif command == "reordertags":
            await admin.handle_reordertags(ctx, session, chat_id, args, actor)
        elif command == "groups":
            await admin.send_groups(ctx, session, chat_id)
        elif command == "health":
            await admin.send_health(ctx, session, chat_id)
        elif command == "settings":
            await admin.handle_settings(ctx, session, chat_id, args, actor)
        elif command == "broadcast":
            await admin.start_broadcast_flow(ctx, session, message)
        elif command == "forget":
            await admin.handle_forget(ctx, session, chat_id, args, actor)
        else:
            await ctx.api.send_message(chat_id, fa.ERR_UNKNOWN_COMMAND)

    async def _on_callback(self, cq: CallbackQuery) -> None:
        try:
            data = parse_callback(cq.data or "")
        except CallbackDataError:
            logger.warning("malformed_callback", data=cq.data)
            if self.ctx.caps.has("answerCallbackQuery"):
                try:
                    await self.ctx.api.answer_callback_query(cq.id, fa.ERR_EXPIRED)
                except (BaleAPIError, NetworkError) as exc:
                    logger.info("callback_answer_failed", error=str(exc))
            return

        chat_id = cq.message.chat.id if cq.message is not None else cq.from_user.id
        lock = self.ctx.locks.get(chat_id, cq.from_user.id)
        if lock.locked():
            if self.ctx.caps.has("answerCallbackQuery"):
                try:
                    await self.ctx.api.answer_callback_query(cq.id, fa.ERR_BUSY)
                except (BaleAPIError, NetworkError) as exc:
                    logger.info("callback_busy_answer_failed", error=str(exc))
            return

        async with lock, self.ctx.db.session() as session:
            if data.action in admin.ADMIN_ACTIONS:
                await admin.handle_admin_callback(self.ctx, session, cq)
            else:
                await wizard.handle_wizard_callback(self.ctx, session, cq)

    async def process_spool(self) -> int:
        """Replay spooled updates after the database comes back."""
        if not self._spool_dir.exists():
            return 0
        processed = 0
        for path in sorted(self._spool_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                update = Update.model_validate(raw)
            except (OSError, ValueError):
                logger.warning("spool_file_invalid", file=str(path))
                path.unlink(missing_ok=True)
                continue
            await self.dispatch(update)
            path.unlink(missing_ok=True)
            processed += 1
        if processed:
            logger.info("spool_replayed", count=processed)
        return processed
