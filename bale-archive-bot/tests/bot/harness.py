"""Test driver: feeds Bale updates into the real dispatcher against the test MySQL."""

from __future__ import annotations

import asyncio
import itertools
from pathlib import Path
from typing import Any

from app.bale.methods import BaleAPI
from app.bale.models import Update
from app.config import Settings
from app.core.admins import AdminStore
from app.core.context import BotContext
from app.core.dispatcher import Dispatcher
from app.db.session import Database
from tests.conftest import MAIN_DB, RootDB, bot_url
from tests.fakes.fake_bale import FakeBaleServer

ADMIN_ID = 111
USER = {"id": 222, "is_bot": False, "first_name": "علی", "last_name": "رضایی", "username": "ali"}
OTHER_USER = {"id": 333, "is_bot": False, "first_name": "سارا", "username": "sara"}
GROUP_ID = -100
GROUP = {"id": GROUP_ID, "type": "group", "title": "گروه رصد"}
ARCHIVE_ID = -500
ARCHIVE = {"id": ARCHIVE_ID, "type": "group", "title": "آرشیو"}
UNKNOWN_GROUP = {"id": -777, "type": "group", "title": "گروه ناشناس"}

MB = 1024 * 1024


def make_settings(data_dir: Path, db_name: str = MAIN_DB, **extra: Any) -> Settings:
    values: dict[str, Any] = {
        "BALE_BOT_TOKEN": "test-token",
        "DATABASE_URL": bot_url(db_name),
        "ARCHIVE_CHAT_ID": ARCHIVE_ID,
        "ADMIN_USER_IDS": [ADMIN_ID],
        "DATA_DIR": str(data_dir),
        "ALBUM_WINDOW_MS": 50,
    }
    values.update(extra)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


class Harness:
    def __init__(self, settings: Settings, api: BaleAPI, fake: FakeBaleServer, root: RootDB) -> None:
        self.settings = settings
        self.fake = fake
        self.root = root
        self.db = Database(settings.database_url)
        self.ctx = BotContext(
            settings=settings,
            api=api,
            db=self.db,
            admins=AdminStore(settings.admins_file, settings.admin_user_ids),
        )
        self.ctx.bot_username = fake.bot_username
        self.ctx.bot_user_id = fake.bot_id
        self.dispatcher = Dispatcher(self.ctx)
        self._update_ids = itertools.count(1)
        self._message_ids = itertools.count(5000)

    async def close(self) -> None:
        await self.settle()
        await self.db.dispose()

    async def settle(self) -> None:
        """Flush album buffers and wait for background downloads."""
        await self.dispatcher.albums.drain()
        for _ in range(50):
            pending = [task for task in self.ctx.background if not task.done()]
            if not pending:
                break
            await asyncio.gather(*pending, return_exceptions=True)

    # ─── Sending updates ───

    async def feed(self, payload: dict[str, Any]) -> None:
        payload = {"update_id": next(self._update_ids), **payload}
        update = Update.model_validate(payload)
        await self.dispatcher.dispatch(update)
        await self.settle()

    def next_message_id(self) -> int:
        return next(self._message_ids)

    async def send(
        self, chat: dict[str, Any], user: dict[str, Any], message_id: int | None = None, **content: Any
    ) -> int:
        message_id = message_id or self.next_message_id()
        message = {
            "message_id": message_id,
            "date": 1_758_880_800,  # 2025-09-26 10:00:00 UTC → 13:30 Tehran
            "chat": chat,
            "from": user,
            **content,
        }
        await self.feed({"message": message})
        return message_id

    async def text(self, chat: dict[str, Any], user: dict[str, Any], body: str) -> int:
        return await self.send(chat, user, text=body)

    async def private(self, user: dict[str, Any], body: str) -> None:
        chat = {"id": user["id"], "type": "private", "first_name": user.get("first_name", "")}
        await self.send(chat, user, text=body)

    async def press(
        self,
        user: dict[str, Any],
        action: str,
        sid: str = "",
        arg: str = "",
        chat_id: int | None = None,
        message_id: int = 1,
    ) -> None:
        chat_id = chat_id if chat_id is not None else user["id"]
        await self.feed(
            {
                "callback_query": {
                    "id": f"cq{next(self._update_ids)}",
                    "from": user,
                    "data": f"1|{action}|{sid}|{arg}",
                    "message": {
                        "message_id": message_id,
                        "chat": {"id": chat_id, "type": "private" if chat_id > 0 else "group", "title": GROUP["title"]},
                    },
                }
            }
        )

    # ─── Wizard helpers ───

    def sid(self, user: dict[str, Any] = USER) -> str:
        sessions = self.ctx.wizards.for_user(user["id"])
        assert sessions, "no open wizard"
        return sessions[-1].sid

    async def confirm(self, tag_ids: list[int], user: dict[str, Any] = USER) -> None:
        """yes → toggle tags → continue → final."""
        sid = self.sid(user)
        await self.press(user, "y", sid)
        for tag_id in tag_ids:
            await self.press(user, "t", sid, str(tag_id))
        await self.press(user, "c", sid)
        await self.press(user, "f", sid)

    # ─── Database helpers ───

    def register_group(self, bale_group_id: int = GROUP_ID, name: str = "گروه رصد", level: int = 1, active: int = 1) -> int:
        self.root.execute(f"USE `{MAIN_DB}`")
        self.root.execute(
            "INSERT INTO EhyaGroup (bale_group_id, bale_group_name, level, is_active) VALUES (%s, %s, %s, %s)",
            (bale_group_id, name, level, active),
        )
        return int(self.root.execute("SELECT id FROM EhyaGroup WHERE bale_group_id = %s", (bale_group_id,))[0][0])

    def count(self, table: str) -> int:
        return self.root.count(table, self.settings.database_url.rsplit("/", 1)[1].split("?")[0])

    def post_rows(self) -> int:
        return self.count("Post") + self.count("PostHashtag") + self.count("PostMedia")

    # ─── Fake-server helpers ───

    def texts_to(self, chat_id: int) -> list[str]:
        return [params.get("text", "") for params in self.fake.calls_for("sendMessage") if int(params["chat_id"]) == chat_id]

    def deleted(self) -> set[tuple[int, int]]:
        return {(int(p["chat_id"]), int(p["message_id"])) for p in self.fake.calls_for("deleteMessage")}

    def outbound_calls(self) -> list[str]:
        ignore = {"answerCallbackQuery"}
        return [name for name, _ in self.fake.calls if name not in ignore]
