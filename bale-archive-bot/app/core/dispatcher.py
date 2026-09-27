"""Update routing with a global error net: no exception escapes :meth:`dispatch`."""

from __future__ import annotations

from collections import OrderedDict

from app.bale.errors import BaleAPIError, NetworkError
from app.bale.keyboards import CallbackDataError, parse_callback
from app.bale.models import CallbackQuery, Message, Update
from app.core.albums import AlbumBuffer
from app.core.context import BotContext
from app.domain.classify import normalize_fa
from app.handlers import admin, intake, panel, user_menu, wizard
from app.i18n import fa
from app.observability.logging import get_logger

logger = get_logger(__name__)

_PERSIAN_COMMANDS = {
    "شروع": "start",
    "راهنما": "help",
    "شناسه": "id",
    "هشتگ": "tags",
    "هشتگها": "tags",
}


_BUTTON_COMMANDS = {
    fa.BTN_MY_POSTS: "my",
    fa.BTN_MY_STATS: "mystats",
    fa.BTN_UNDO_LAST: "undo",
    fa.BTN_HELP: "help",
    fa.BTN_ADMIN_PANEL: "panel",
}


def parse_command(text: str | None) -> tuple[str, list[str]] | None:
    """'/cmd@bot arg1 arg2' or a whole-word Persian alias → (cmd, args)."""
    stripped = (text or "").strip()
    if not stripped:
        return None
    if stripped.startswith("/"):
        parts = stripped.split()
        command = parts[0][1:].split("@")[0].lower()
        return (command, parts[1:]) if command else None
    if stripped in _BUTTON_COMMANDS:
        return _BUTTON_COMMANDS[stripped], []
    words = stripped.split()
    alias = _PERSIAN_COMMANDS.get(normalize_fa(words[0]).replace(" ", ""))
    if alias is not None and len(words) == 1:
        return alias, []
    return None


class _SeenUpdates:
    """Drops an update id seen recently (Bale may resend after a restart)."""

    def __init__(self, size: int = 10_000) -> None:
        self._ids: OrderedDict[int, None] = OrderedDict()
        self._size = size

    def first_time(self, update_id: int) -> bool:
        if update_id in self._ids:
            return False
        self._ids[update_id] = None
        if len(self._ids) > self._size:
            self._ids.popitem(last=False)
        return True


class Dispatcher:
    def __init__(self, ctx: BotContext) -> None:
        self.ctx = ctx
        self.albums = AlbumBuffer(self._flush_group_batch, window_ms=ctx.settings.album_window_ms)
        self._seen = _SeenUpdates()

    async def _flush_group_batch(self, messages: list[Message]) -> None:
        try:
            await intake.process_group_batch(self.ctx, messages)
        except Exception:
            logger.exception("group_batch_failed", chat_id=messages[0].chat.id)

    async def dispatch(self, update: Update) -> None:
        """Process one update; never raises."""
        if not self._seen.first_time(update.update_id):
            return
        try:
            if update.message is not None:
                await self._on_message(update.message)
            elif update.edited_message is not None:
                intake.apply_edit(self.ctx, update.edited_message)
            elif update.callback_query is not None:
                await self._on_callback(update.callback_query)
        except Exception:
            logger.exception("update_failed", update_id=update.update_id)

    # ─── Messages ───

    async def _on_message(self, message: Message) -> None:
        if message.from_user is None or message.from_user.is_bot:
            return
        if message.is_private_message:
            await self._on_private(message)
            return
        if intake.is_archive_chat(self.ctx, message.chat.id):
            command = parse_command(message.text)
            if command is not None and command[0] in {"register", "unregister"}:
                await admin.handle_group_command(self.ctx, message, command[0])
            return  # never archived, never written to the database
        command = parse_command(message.text)
        if command is not None and (message.text or "").startswith("/"):
            if command[0] in {"register", "unregister"}:
                await admin.handle_group_command(self.ctx, message, command[0])
            return  # other commands in groups: silence
        await self.albums.add(message)

    async def _on_private(self, message: Message) -> None:
        assert message.from_user is not None
        ctx = self.ctx
        command = parse_command(message.text)
        name = command[0] if command is not None else ""
        args = command[1] if command is not None else []
        if command is None:
            waiting = panel.take_input(ctx, message.from_user.id)
            if waiting is not None:
                await panel.handle_input(ctx, message, *waiting)
                return
        else:
            ctx.pending_input.pop(message.from_user.id, None)
        if name == "start":
            await user_menu.send_start(ctx, message.from_user.id)
            await wizard.resume_pending(ctx, message.from_user.id)
        elif name == "help":
            await user_menu.send_help(ctx, message.from_user.id)
        elif name == "my":
            await user_menu.send_my_posts(ctx, message.from_user.id)
        elif name == "mystats":
            await user_menu.send_my_stats(ctx, message.from_user.id)
        elif name == "undo":
            await user_menu.ask_undo(ctx, message.from_user.id)
        elif name == "id":
            await self._send(message.chat.id, fa.your_id(message.from_user.id))
        elif name == "tags":
            from app.db import repo

            async with ctx.db.tx() as conn:
                names = [tag.name for tag in await repo.active_hashtags(conn)]
            await self._send(message.chat.id, fa.tags_list(names))
        elif name in admin.PRIVATE_ADMIN_COMMANDS:
            await admin.handle_private_command(ctx, message, name, args)
        elif name in {"register", "unregister"}:
            if ctx.is_admin(message.from_user.id):
                await self._send(message.chat.id, fa.REGISTER_IN_GROUP_ONLY)
        elif command is not None:
            await self._send(message.chat.id, fa.UNKNOWN_COMMAND)
        else:
            # Content sent straight to the bot is not archived (it has no group).
            await self._send(message.chat.id, fa.HELP)

    async def _send(self, chat_id: int, text: str) -> None:
        try:
            await self.ctx.api.send_message(chat_id, text)
        except (BaleAPIError, NetworkError) as exc:
            logger.info("reply_failed", chat_id=chat_id, error=str(exc))

    # ─── Callbacks ───

    async def _on_callback(self, cq: CallbackQuery) -> None:
        try:
            data = parse_callback(cq.data or "")
        except CallbackDataError:
            logger.info("callback_dropped", reason="malformed", data=cq.data)
            return
        chat_id = cq.message.chat.id if cq.message is not None else None
        logger.info("callback_received", action=data.action, actor=cq.from_user.id, chat_id=chat_id)
        if data.action == admin.ACT_LEVEL:
            # Registration must work in a group that is not registered yet.
            await admin.handle_level_callback(self.ctx, cq, data.sid, data.arg)
            return
        if data.action == user_menu.ACT_UNDO:
            async with self.ctx.user_locks.get(("undo", cq.from_user.id)):
                await user_menu.handle_undo_callback(self.ctx, cq, data.arg)
            return
        if data.action == panel.ACT_PANEL:
            await panel.handle_callback(self.ctx, cq, data.sid, data.arg)
            return
        if data.action in wizard.WIZARD_ACTIONS:
            async with self.ctx.user_locks.get(("wizard", cq.from_user.id)):
                await wizard.handle_callback(self.ctx, cq, data.action, data.sid, data.arg)
            return
        logger.info("callback_dropped", reason="unknown_action", action=data.action)
