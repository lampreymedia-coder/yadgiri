"""Edge-case scenarios from spec section 11-11."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from app.bale.models import Update
from app.core.context import BotContext
from app.core.dispatcher import Dispatcher, parse_command
from app.db.models import Submission, SubmissionStatus
from app.db.repositories.outbox import OutboxRepository
from app.domain.submission import CAPTION_LIMIT, SubmissionService
from app.workers.outbox import run_outbox_once
from app.workers.ttl_sweeper import run_expiry_once, run_reminders_once
from tests.e2e.test_wizard_flow import (
    GROUP_ID,
    USER_ID,
    callback_update,
    get_submission,
    load_update,
    wizard_message_id,
)
from tests.fakes.fake_bale import FakeBaleServer

FIXTURES = Path(__file__).parent.parent / "fixtures" / "updates"


@pytest.fixture
def dispatcher(ctx: BotContext) -> Dispatcher:
    return Dispatcher(ctx)


def test_parse_command() -> None:
    assert parse_command("/stats today") == ("stats", ["today"])
    assert parse_command("/start@archive_bot") == ("start", [])
    assert parse_command("plain text") is None
    assert parse_command("آرشیو") == ("archive", [])
    assert parse_command("ارشیوم") == ("archive", [])


async def test_empty_and_whitespace_message_ignored(
    dispatcher: Dispatcher, ctx: BotContext
) -> None:
    update = load_update("text")
    update["message"]["text"] = "   "
    await dispatcher.dispatch(Update.model_validate(update))
    await asyncio.sleep(0.15)
    async with ctx.db.session() as session:
        assert (await session.execute(select(Submission))).scalars().first() is None


async def test_max_length_text_4096(dispatcher: Dispatcher, ctx: BotContext) -> None:
    update = load_update("text")
    update["message"]["text"] = "آ" * 4096
    await dispatcher.dispatch(Update.model_validate(update))
    submission = await get_submission(ctx)
    assert submission.text_content is not None
    assert len(submission.text_content) == 4096


async def test_caption_over_1024_splits_into_reply(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    update = load_update("image")
    update["message"]["caption"] = "ب" * 1500
    await dispatcher.dispatch(Update.model_validate(update))
    await asyncio.sleep(0.2)  # album window
    submission = await get_submission(ctx)
    sid = submission.short_id
    msg_id = wizard_message_id(fake_bale, GROUP_ID)
    await dispatcher.dispatch(callback_update(f"1|yes|{sid}|", GROUP_ID, msg_id))
    await dispatcher.dispatch(callback_update(f"1|cnt|{sid}|1", GROUP_ID, msg_id))
    markup = fake_bale.last_markup(GROUP_ID)
    assert markup is not None
    tag_cb = next(
        btn["callback_data"]
        for row in markup["inline_keyboard"]
        for btn in row
        if "|tg|" in btn.get("callback_data", "")
    )
    await dispatcher.dispatch(callback_update(tag_cb, GROUP_ID, msg_id))
    await dispatcher.dispatch(callback_update(f"1|ok|{sid}|", GROUP_ID, msg_id))
    await dispatcher.dispatch(callback_update(f"1|fin|{sid}|", GROUP_ID, msg_id))

    submission = await get_submission(ctx)
    assert submission.status is SubmissionStatus.COMPLETED
    # The media was copied with a short caption and the long text was sent
    # as a separate reply.
    copy_calls = [c for c in fake_bale.calls_for("copyMessage") if int(c["chat_id"]) == GROUP_ID]
    assert copy_calls
    assert len(str(copy_calls[-1].get("caption", ""))) <= CAPTION_LIMIT
    reply_calls = [c for c in fake_bale.calls_for("sendMessage") if c.get("reply_to_message_id")]
    assert reply_calls


async def test_undo_within_window(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    # Complete a submission quickly via the service layer.
    await dispatcher.dispatch(Update.model_validate(load_update("text")))
    submission = await get_submission(ctx)
    sid = submission.short_id
    msg_id = wizard_message_id(fake_bale, GROUP_ID)
    await dispatcher.dispatch(callback_update(f"1|yes|{sid}|", GROUP_ID, msg_id))
    await dispatcher.dispatch(callback_update(f"1|cnt|{sid}|1", GROUP_ID, msg_id))
    markup = fake_bale.last_markup(GROUP_ID)
    assert markup is not None
    tag_cb = next(
        btn["callback_data"]
        for row in markup["inline_keyboard"]
        for btn in row
        if "|tg|" in btn.get("callback_data", "")
    )
    await dispatcher.dispatch(callback_update(tag_cb, GROUP_ID, msg_id))
    await dispatcher.dispatch(callback_update(f"1|ok|{sid}|", GROUP_ID, msg_id))
    await dispatcher.dispatch(callback_update(f"1|fin|{sid}|", GROUP_ID, msg_id))

    undo_update = load_update("text")
    undo_update["message"]["chat"] = {"id": USER_ID, "type": "private"}
    undo_update["message"]["text"] = f"/undo {sid}"
    await dispatcher.dispatch(Update.model_validate(undo_update))
    submission = await get_submission(ctx)
    assert submission.status is SubmissionStatus.CANCELLED
    texts = fake_bale.sent_texts(USER_ID)
    assert any("↩️" in t for t in texts)


async def test_undo_after_window_rejected(dispatcher: Dispatcher, ctx: BotContext) -> None:
    async with ctx.db.session() as session:
        service = SubmissionService(session, ctx.api, ctx.settings)
        user = await service.users.upsert_from_bale(USER_ID, "ali", "علی", None)
        submission = await service.submissions.create_draft(
            user_id=user.id,
            group_id=None,
            content_type=__import__("app.db.models", fromlist=["ContentType"]).ContentType.TEXT,
            content_subtype=None,
            text_content="x",
            text_normalized="x",
            caption=None,
            urls=[],
            is_forwarded=False,
            forward_source=None,
            original_message_id=None,
            raw_update=None,
            ttl_minutes=30,
        )
        await service.submissions.set_status(submission, SubmissionStatus.COMPLETED)
        submission.completed_at = datetime.now(UTC) - timedelta(minutes=20)
        sid = submission.short_id

    undo_update = load_update("text")
    undo_update["message"]["chat"] = {"id": USER_ID, "type": "private"}
    undo_update["message"]["text"] = f"/undo {sid}"
    await dispatcher.dispatch(Update.model_validate(undo_update))
    async with ctx.db.session() as session:
        service = SubmissionService(session, ctx.api, ctx.settings)
        reloaded = await service.submissions.get_by_short_id(sid)
        assert reloaded is not None
        assert reloaded.status is SubmissionStatus.COMPLETED  # unchanged


async def test_spam_limit_enforced(ctx: BotContext, fake_bale: FakeBaleServer) -> None:
    ctx.spam_guard._max = 2  # tighten for the test
    dispatcher = Dispatcher(ctx)
    for _ in range(4):
        await dispatcher.dispatch(Update.model_validate(load_update("text")))
    async with ctx.db.session() as session:
        submissions = list((await session.execute(select(Submission))).scalars().all())
        assert len(submissions) == 2
    assert any("سقف" in t for t in fake_bale.sent_texts(GROUP_ID))


async def test_expiry_republishes(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    await dispatcher.dispatch(Update.model_validate(load_update("text")))
    async with ctx.db.session() as session:
        submission = (await session.execute(select(Submission))).scalars().one()
        submission.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        sid = submission.short_id

    handled = await run_expiry_once(ctx)
    assert handled == 1
    async with ctx.db.session() as session:
        service = SubmissionService(session, ctx.api, ctx.settings)
        reloaded = await service.submissions.get_by_short_id(sid)
        assert reloaded is not None
        assert reloaded.status is SubmissionStatus.EXPIRED
        assert reloaded.published_message_id is not None


async def test_reminder_sent_once(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    await dispatcher.dispatch(Update.model_validate(load_update("text")))
    async with ctx.db.session() as session:
        submission = (await session.execute(select(Submission))).scalars().one()
        submission.created_at = datetime.now(UTC) - timedelta(minutes=15)

    assert await run_reminders_once(ctx) == 1
    assert await run_reminders_once(ctx) == 0  # not repeated


async def test_outbox_worker_sends_and_batches(ctx: BotContext, fake_bale: FakeBaleServer) -> None:
    async with ctx.db.session() as session:
        outbox = OutboxRepository(session)
        for i in range(7):  # above the batch threshold of 5
            await outbox.enqueue("admin_notify", -600, {"text": f"پیام {i}"})
    handled = await run_outbox_once(ctx)
    assert handled == 7
    admin_texts = fake_bale.sent_texts(-600)
    # One aggregate message instead of seven.
    assert len(admin_texts) == 1
    async with ctx.db.session() as session:
        outbox = OutboxRepository(session)
        assert await outbox.pending_count() == 0


async def test_outbox_worker_retries_on_failure(ctx: BotContext, fake_bale: FakeBaleServer) -> None:
    async with ctx.db.session() as session:
        outbox = OutboxRepository(session)
        await outbox.enqueue("user_notify", USER_ID, {"text": "سلام"})
    fake_bale.fail_with("sendMessage", 500, "boom", times=99)
    handled = await run_outbox_once(ctx)
    assert handled == 0
    async with ctx.db.session() as session:
        outbox = OutboxRepository(session)
        assert await outbox.pending_count() == 1  # scheduled for retry


async def test_double_click_second_ignored_while_locked(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    await dispatcher.dispatch(Update.model_validate(load_update("text")))
    submission = await get_submission(ctx)
    sid = submission.short_id
    msg_id = wizard_message_id(fake_bale, GROUP_ID)
    first = dispatcher.dispatch(callback_update(f"1|yes|{sid}|", GROUP_ID, msg_id))
    second = dispatcher.dispatch(callback_update(f"1|yes|{sid}|", GROUP_ID, msg_id))
    await asyncio.gather(first, second)
    submission = await get_submission(ctx)
    # Exactly one forward transition happened.
    assert submission.status is SubmissionStatus.AWAITING_TAG_COUNT


async def test_forwarded_message_intake(dispatcher: Dispatcher, ctx: BotContext) -> None:
    await dispatcher.dispatch(Update.model_validate(load_update("forwarded_text")))
    submission = await get_submission(ctx)
    assert submission.is_forwarded is True
    assert submission.forward_source is not None


async def test_my_command_lists_items(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    await dispatcher.dispatch(Update.model_validate(load_update("text")))
    my_update: dict[str, Any] = load_update("text")
    my_update["message"]["chat"] = {"id": USER_ID, "type": "private"}
    my_update["message"]["text"] = "/my"
    await dispatcher.dispatch(Update.model_validate(my_update))
    texts = fake_bale.sent_texts(USER_ID)
    assert any("🗂" in t for t in texts)


async def test_admin_command_hidden_from_non_admin(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    stats_update = load_update("text")
    stats_update["message"]["chat"] = {"id": USER_ID, "type": "private"}
    stats_update["message"]["text"] = "/stats"
    await dispatcher.dispatch(Update.model_validate(stats_update))
    texts = fake_bale.sent_texts(USER_ID)
    # Generic invalid-command reply — no admin info leaked.
    assert any("دستور نامعتبر" in t for t in texts)


async def test_malformed_callback_answered_gracefully(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    bad = callback_update("garbage-data", USER_ID, 1)
    await dispatcher.dispatch(bad)  # must not raise
    answers = fake_bale.calls_for("answerCallbackQuery")
    assert answers


async def test_raw_update_stored_lossless(dispatcher: Dispatcher, ctx: BotContext) -> None:
    original = load_update("document")
    await dispatcher.dispatch(Update.model_validate(original))
    await asyncio.sleep(0.2)
    submission = await get_submission(ctx)
    assert submission.raw_update is not None
    stored = json.dumps(submission.raw_update, ensure_ascii=False)
    assert "report.pdf" in stored
