"""End-to-end wizard scenarios on the fake Bale server (no network)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from app.bale.models import Update
from app.core.context import BotContext
from app.core.dispatcher import Dispatcher
from app.db.models import Submission, SubmissionStatus
from app.db.repositories.outbox import OutboxRepository
from app.db.repositories.submissions import SubmissionRepository
from tests.fakes.fake_bale import FakeBaleServer

FIXTURES = Path(__file__).parent.parent / "fixtures" / "updates"

GROUP_ID = -100200300
USER_ID = 12345
ARCHIVE_ID = -500

_update_seq = iter(range(100000, 200000))


def load_update(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text("utf-8"))
    data["update_id"] = next(_update_seq)
    return data


def callback_update(data: str, chat_id: int, message_id: int) -> Update:
    return Update.model_validate(
        {
            "update_id": next(_update_seq),
            "callback_query": {
                "id": f"cb{next(_update_seq)}",
                "from": {"id": USER_ID, "is_bot": False, "first_name": "علی"},
                "message": {
                    "message_id": message_id,
                    "chat": {"id": chat_id, "type": "private" if chat_id > 0 else "group"},
                    "text": "wizard",
                },
                "data": data,
            },
        }
    )


def wizard_buttons(fake: FakeBaleServer, chat_id: int) -> dict[str, str]:
    """Map button label -> callback_data of the latest keyboard in a chat."""
    markup = fake.last_markup(chat_id)
    assert markup is not None
    return {
        btn["text"]: btn.get("callback_data", "")
        for row in markup["inline_keyboard"]
        for btn in row
    }


def wizard_message_id(fake: FakeBaleServer, chat_id: int) -> int:
    for message in reversed(list(fake.messages.values())):
        if message.chat_id == chat_id and not message.deleted and message.reply_markup:
            return message.message_id
    raise AssertionError("no wizard message found")


async def intake_text(dispatcher: Dispatcher) -> None:
    await dispatcher.dispatch(Update.model_validate(load_update("text")))


async def get_submission(ctx: BotContext) -> Submission:
    async with ctx.db.session() as session:
        subs = SubmissionRepository(session)
        result = await session.execute(
            __import__("sqlalchemy").select(Submission).order_by(Submission.id.desc()).limit(1)
        )
        submission = result.scalars().first()
        assert submission is not None
        return await subs.get_by_short_id(submission.short_id) or submission


@pytest.fixture
def dispatcher(ctx: BotContext) -> Dispatcher:
    return Dispatcher(ctx)


async def test_gateway_archive_before_delete(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    await intake_text(dispatcher)
    methods = [name for name, _ in fake_bale.calls]
    assert "copyMessage" in methods
    assert "deleteMessage" in methods
    assert methods.index("copyMessage") < methods.index("deleteMessage")
    # Archive copy went to the archive channel.
    copy_call = fake_bale.calls_for("copyMessage")[0]
    assert int(copy_call["chat_id"]) == ARCHIVE_ID
    # Wizard opened in the user's private chat.
    assert fake_bale.last_markup(GROUP_ID) is not None
    submission = await get_submission(ctx)
    assert submission.status is SubmissionStatus.AWAITING_DECISION
    assert submission.archive_message_id is not None


async def test_archive_failure_blocks_delete(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    fake_bale.fail_with("copyMessage", 400, "archive unavailable", times=99)
    await intake_text(dispatcher)
    assert fake_bale.calls_for("deleteMessage") == []
    async with ctx.db.session() as session:
        result = await session.execute(__import__("sqlalchemy").select(Submission))
        assert result.scalars().first() is None
        outbox = OutboxRepository(session)
        assert await outbox.pending_count() == 1  # admin alert queued


async def test_full_happy_path_two_tags(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    await intake_text(dispatcher)
    submission = await get_submission(ctx)
    sid = submission.short_id
    msg_id = wizard_message_id(fake_bale, GROUP_ID)

    # Step 1: yes
    await dispatcher.dispatch(callback_update(f"1|yes|{sid}|", GROUP_ID, msg_id))
    buttons = wizard_buttons(fake_bale, GROUP_ID)
    assert any("|cnt|" in cb for cb in buttons.values())

    # Step 2: two tags
    await dispatcher.dispatch(callback_update(f"1|cnt|{sid}|2", GROUP_ID, msg_id))
    buttons = wizard_buttons(fake_bale, GROUP_ID)
    tag_callbacks = [cb for cb in buttons.values() if "|tg|" in cb]
    assert len(tag_callbacks) == 3

    # Step 3: toggle two tags; a third toggle must be rejected via toast.
    await dispatcher.dispatch(callback_update(tag_callbacks[0], GROUP_ID, msg_id))
    await dispatcher.dispatch(callback_update(tag_callbacks[1], GROUP_ID, msg_id))
    calls_before = len(fake_bale.calls_for("editMessageText"))
    await dispatcher.dispatch(callback_update(tag_callbacks[2], GROUP_ID, msg_id))
    assert len(fake_bale.calls_for("editMessageText")) == calls_before  # unchanged
    answers = fake_bale.calls_for("answerCallbackQuery")
    assert any(a.get("text") and "دو" in str(a["text"]) for a in answers)

    # Step 4: continue → preview
    await dispatcher.dispatch(callback_update(f"1|ok|{sid}|", GROUP_ID, msg_id))
    buttons = wizard_buttons(fake_bale, GROUP_ID)
    assert any("|fin|" in cb for cb in buttons.values())

    # Back keeps selections.
    await dispatcher.dispatch(callback_update(f"1|bk|{sid}|", GROUP_ID, msg_id))
    markup = fake_bale.last_markup(GROUP_ID)
    assert markup is not None
    checked = [
        btn["text"]
        for row in markup["inline_keyboard"]
        for btn in row
        if btn["text"].startswith("✅")
    ]
    assert len(checked) == 2

    # Continue again and confirm.
    await dispatcher.dispatch(callback_update(f"1|ok|{sid}|", GROUP_ID, msg_id))
    await dispatcher.dispatch(callback_update(f"1|fin|{sid}|", GROUP_ID, msg_id))

    submission = await get_submission(ctx)
    assert submission.status is SubmissionStatus.COMPLETED
    assert len(submission.tags) == 2
    assert submission.published_message_id is not None
    published = fake_bale.messages[(GROUP_ID, submission.published_message_id)]
    assert published.text is not None
    assert "📌" in published.text
    assert published.text.count("#") == 2
    # Admin notification queued in the outbox.
    async with ctx.db.session() as session:
        outbox = OutboxRepository(session)
        assert await outbox.pending_count() == 1

    # Clicking the old keyboard after completion → expired toast, no crash.
    await dispatcher.dispatch(callback_update(f"1|yes|{sid}|", GROUP_ID, msg_id))
    answers = fake_bale.calls_for("answerCallbackQuery")
    assert any("منقضی" in str(a.get("text", "")) for a in answers)


async def test_decline_republishes_without_tags(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    await intake_text(dispatcher)
    submission = await get_submission(ctx)
    msg_id = wizard_message_id(fake_bale, GROUP_ID)
    await dispatcher.dispatch(callback_update(f"1|no|{submission.short_id}|", GROUP_ID, msg_id))
    submission = await get_submission(ctx)
    assert submission.status is SubmissionStatus.DECLINED
    assert submission.published_message_id is not None
    republished = fake_bale.messages[(GROUP_ID, submission.published_message_id)]
    assert republished.text is not None
    assert republished.text.startswith("📎")
    assert "#" not in republished.text


async def test_cancel_removes_everything(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    await intake_text(dispatcher)
    submission = await get_submission(ctx)
    msg_id = wizard_message_id(fake_bale, GROUP_ID)
    await dispatcher.dispatch(callback_update(f"1|cx|{submission.short_id}|", GROUP_ID, msg_id))
    submission = await get_submission(ctx)
    assert submission.status is SubmissionStatus.CANCELLED
    assert submission.published_message_id is None


async def test_foreign_user_click_rejected(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    await intake_text(dispatcher)
    submission = await get_submission(ctx)
    msg_id = wizard_message_id(fake_bale, GROUP_ID)
    foreign = Update.model_validate(
        {
            "update_id": next(_update_seq),
            "callback_query": {
                "id": "cb-foreign",
                "from": {"id": 999888, "is_bot": False, "first_name": "غریبه"},
                "message": {
                    "message_id": msg_id,
                    "chat": {"id": GROUP_ID, "type": "group"},
                    "text": "wizard",
                },
                "data": f"1|yes|{submission.short_id}|",
            },
        }
    )
    await dispatcher.dispatch(foreign)
    submission = await get_submission(ctx)
    assert submission.status is SubmissionStatus.AWAITING_DECISION  # unchanged
    answers = fake_bale.calls_for("answerCallbackQuery")
    assert any("متعلق به شما نیست" in str(a.get("text", "")) for a in answers)


async def test_restart_mid_wizard_state_survives(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    await intake_text(dispatcher)
    submission = await get_submission(ctx)
    sid = submission.short_id
    msg_id = wizard_message_id(fake_bale, GROUP_ID)
    await dispatcher.dispatch(callback_update(f"1|yes|{sid}|", GROUP_ID, msg_id))

    # Simulate a process restart: a brand-new dispatcher and context caches.
    fresh_dispatcher = Dispatcher(ctx)
    await fresh_dispatcher.dispatch(callback_update(f"1|cnt|{sid}|1", GROUP_ID, msg_id))
    buttons = wizard_buttons(fake_bale, GROUP_ID)
    tag_callbacks = [cb for cb in buttons.values() if "|tg|" in cb]
    await fresh_dispatcher.dispatch(callback_update(tag_callbacks[0], GROUP_ID, msg_id))
    await fresh_dispatcher.dispatch(callback_update(f"1|ok|{sid}|", GROUP_ID, msg_id))
    await fresh_dispatcher.dispatch(callback_update(f"1|fin|{sid}|", GROUP_ID, msg_id))
    submission = await get_submission(ctx)
    assert submission.status is SubmissionStatus.COMPLETED


async def test_duplicate_update_processed_once(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    update = Update.model_validate(load_update("text"))
    await dispatcher.dispatch(update)
    await dispatcher.dispatch(update)  # same update_id again
    async with ctx.db.session() as session:
        result = await session.execute(__import__("sqlalchemy").select(Submission))
        assert len(list(result.scalars().all())) == 1


async def test_private_chat_forbidden_falls_back_to_group(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    fake_bale.forbidden_private_chats.add(USER_ID)
    await intake_text(dispatcher)
    # Wizard keyboard appeared inside the group instead.
    markup = fake_bale.last_markup(GROUP_ID)
    assert markup is not None
    flat = [btn for row in markup["inline_keyboard"] for btn in row]
    assert any(btn.get("url") for btn in flat)  # link to the bot's private chat
    submission = await get_submission(ctx)
    assert submission.wizard_chat_id == GROUP_ID


async def test_album_buffer_groups_media(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    photo1 = load_update("image")
    photo2 = load_update("image")
    photo2["message"]["message_id"] = photo1["message"]["message_id"] + 1
    await dispatcher.dispatch(Update.model_validate(photo1))
    await dispatcher.dispatch(Update.model_validate(photo2))
    await asyncio.sleep(0.3)  # window (50ms) + margin
    submission = await get_submission(ctx)
    assert submission.content_type.value == "album"
    assert len(submission.media_files) == 2


async def test_sticker_ignored_by_default(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    await dispatcher.dispatch(Update.model_validate(load_update("sticker")))
    await asyncio.sleep(0.2)
    async with ctx.db.session() as session:
        result = await session.execute(__import__("sqlalchemy").select(Submission))
        assert result.scalars().first() is None
