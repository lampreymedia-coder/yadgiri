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


async def bind_archives(ctx: BotContext) -> None:
    from app.handlers.admin import persist_archive_chat
    from app.i18n.fa import SEED_TAGS

    async with ctx.db.session() as session:
        for slug, _title, _hashtag in SEED_TAGS:
            await persist_archive_chat(ctx, session, ARCHIVE_ID, slug=slug)


async def test_gateway_keeps_original_and_opens_private_wizard(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    await intake_text(dispatcher)
    methods = [name for name, _ in fake_bale.calls]
    assert "copyMessage" not in methods
    assert "deleteMessage" not in methods
    assert fake_bale.last_markup(USER_ID) is not None
    assert fake_bale.last_markup(GROUP_ID) is None
    submission = await get_submission(ctx)
    assert submission.status is SubmissionStatus.AWAITING_DECISION
    assert submission.wizard_chat_id == USER_ID
    assert submission.archive_message_id is None


async def test_copy_failure_on_confirm_still_saves_sql(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    await bind_archives(ctx)
    fake_bale.fail_with("copyMessage", 400, "archive unavailable", times=99)
    await intake_text(dispatcher)
    submission = await get_submission(ctx)
    sid = submission.short_id
    msg_id = wizard_message_id(fake_bale, USER_ID)
    await dispatcher.dispatch(callback_update(f"1|yes|{sid}|", USER_ID, msg_id))
    buttons = wizard_buttons(fake_bale, USER_ID)
    tag_cb = next(cb for cb in buttons.values() if "|tg|" in cb)
    await dispatcher.dispatch(callback_update(tag_cb, USER_ID, msg_id))
    await dispatcher.dispatch(callback_update(f"1|ok|{sid}|", USER_ID, msg_id))
    await dispatcher.dispatch(callback_update(f"1|fin|{sid}|", USER_ID, msg_id))
    submission = await get_submission(ctx)
    assert submission.status is SubmissionStatus.COMPLETED
    async with ctx.db.session() as session:
        outbox = OutboxRepository(session)
        assert await outbox.pending_count() >= 1


async def test_full_happy_path_two_tags(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    await bind_archives(ctx)
    await intake_text(dispatcher)
    submission = await get_submission(ctx)
    sid = submission.short_id
    msg_id = wizard_message_id(fake_bale, USER_ID)

    # Step 1: yes → hashtags immediately (no count step)
    await dispatcher.dispatch(callback_update(f"1|yes|{sid}|", USER_ID, msg_id))
    buttons = wizard_buttons(fake_bale, USER_ID)
    assert not any("|cnt|" in cb for cb in buttons.values())
    tag_callbacks = [cb for cb in buttons.values() if "|tg|" in cb]
    assert len(tag_callbacks) == 4
    labels = list(buttons)
    assert any("یادگیری" in label for label in labels)
    assert any("سند" in label for label in labels)
    assert any("شبکه" in label for label in labels)
    assert any("محتوایی" in label for label in labels)

    # Step 2: toggle two tags; a third is also allowed (no count limit).
    await dispatcher.dispatch(callback_update(tag_callbacks[0], USER_ID, msg_id))
    await dispatcher.dispatch(callback_update(tag_callbacks[1], USER_ID, msg_id))

    # Step 3: continue → preview with edit
    await dispatcher.dispatch(callback_update(f"1|ok|{sid}|", USER_ID, msg_id))
    buttons = wizard_buttons(fake_bale, USER_ID)
    assert any("|fin|" in cb for cb in buttons.values())
    assert any("|edt|" in cb for cb in buttons.values())

    # Back keeps selections.
    await dispatcher.dispatch(callback_update(f"1|bk|{sid}|", USER_ID, msg_id))
    markup = fake_bale.last_markup(USER_ID)
    assert markup is not None
    checked = [
        btn["text"]
        for row in markup["inline_keyboard"]
        for btn in row
        if btn["text"].startswith("✅")
    ]
    assert len(checked) == 2

    # Continue again and confirm.
    await dispatcher.dispatch(callback_update(f"1|ok|{sid}|", USER_ID, msg_id))
    await dispatcher.dispatch(callback_update(f"1|fin|{sid}|", USER_ID, msg_id))

    submission = await get_submission(ctx)
    assert submission.status is SubmissionStatus.COMPLETED
    assert len(submission.tags) == 2
    assert submission.published_message_id is None
    copies = [c for c in fake_bale.calls_for("copyMessage") if int(c["chat_id"]) == ARCHIVE_ID]
    assert len(copies) == 2
    assert any("موفقیت" in t for t in fake_bale.sent_texts(USER_ID))
    assert not any("مجموع امروز" in t for t in fake_bale.sent_texts(USER_ID))
    async with ctx.db.session() as session:
        outbox = OutboxRepository(session)
        assert await outbox.pending_count() >= 1

    # Clicking the old keyboard after completion → expired toast, no crash.
    await dispatcher.dispatch(callback_update(f"1|yes|{sid}|", USER_ID, msg_id))
    answers = fake_bale.calls_for("answerCallbackQuery")
    assert any("منقضی" in str(a.get("text", "")) for a in answers)


async def test_decline_leaves_original_in_group(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    await intake_text(dispatcher)
    submission = await get_submission(ctx)
    msg_id = wizard_message_id(fake_bale, USER_ID)
    await dispatcher.dispatch(callback_update(f"1|no|{submission.short_id}|", USER_ID, msg_id))
    submission = await get_submission(ctx)
    assert submission.status is SubmissionStatus.DECLINED
    assert submission.published_message_id is None
    assert fake_bale.calls_for("copyMessage") == []


async def test_cancel_removes_everything(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    await intake_text(dispatcher)
    submission = await get_submission(ctx)
    msg_id = wizard_message_id(fake_bale, USER_ID)
    await dispatcher.dispatch(callback_update(f"1|cx|{submission.short_id}|", USER_ID, msg_id))
    submission = await get_submission(ctx)
    assert submission.status is SubmissionStatus.CANCELLED
    assert submission.published_message_id is None


async def test_foreign_user_click_rejected(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    await intake_text(dispatcher)
    submission = await get_submission(ctx)
    msg_id = wizard_message_id(fake_bale, USER_ID)
    foreign = Update.model_validate(
        {
            "update_id": next(_update_seq),
            "callback_query": {
                "id": "cb-foreign",
                "from": {"id": 999888, "is_bot": False, "first_name": "غریبه"},
                "message": {
                    "message_id": msg_id,
                    "chat": {"id": USER_ID, "type": "private"},
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
    msg_id = wizard_message_id(fake_bale, USER_ID)
    await dispatcher.dispatch(callback_update(f"1|yes|{sid}|", USER_ID, msg_id))

    fresh_dispatcher = Dispatcher(ctx)
    buttons = wizard_buttons(fake_bale, USER_ID)
    tag_callbacks = [cb for cb in buttons.values() if "|tg|" in cb]
    await fresh_dispatcher.dispatch(callback_update(tag_callbacks[0], USER_ID, msg_id))
    await fresh_dispatcher.dispatch(callback_update(f"1|ok|{sid}|", USER_ID, msg_id))
    await fresh_dispatcher.dispatch(callback_update(f"1|fin|{sid}|", USER_ID, msg_id))
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


async def test_private_chat_forbidden_posts_url_hint(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    fake_bale.forbidden_private_chats.add(USER_ID)
    await intake_text(dispatcher)
    markup = fake_bale.last_markup(GROUP_ID)
    assert markup is not None
    flat = [btn for row in markup["inline_keyboard"] for btn in row]
    assert any(btn.get("url") for btn in flat)
    assert not any("|yes|" in (btn.get("callback_data") or "") for btn in flat)
    submission = await get_submission(ctx)
    assert submission.wizard_chat_id == USER_ID
    assert submission.wizard_message_id is None


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


async def test_voice_opens_private_wizard_immediately(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    await dispatcher.dispatch(Update.model_validate(load_update("voice")))
    submission = await get_submission(ctx)
    assert submission.content_type.value == "voice"
    assert fake_bale.last_markup(USER_ID) is not None
    assert any("|yes|" in cb for cb in wizard_buttons(fake_bale, USER_ID).values())


async def test_contact_and_location_open_private_wizard(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    await dispatcher.dispatch(Update.model_validate(load_update("contact")))
    assert fake_bale.last_markup(USER_ID) is not None
    await dispatcher.dispatch(Update.model_validate(load_update("location")))
    submission = await get_submission(ctx)
    assert submission.content_type.value == "location"


async def test_sticker_ignored_by_default(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    await dispatcher.dispatch(Update.model_validate(load_update("sticker")))
    await asyncio.sleep(0.2)
    async with ctx.db.session() as session:
        result = await session.execute(__import__("sqlalchemy").select(Submission))
        assert result.scalars().first() is None


async def test_gif_animation_ignored(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    await dispatcher.dispatch(Update.model_validate(load_update("animation")))
    async with ctx.db.session() as session:
        result = await session.execute(__import__("sqlalchemy").select(Submission))
        assert result.scalars().first() is None


async def test_edit_tags_from_preview(
    dispatcher: Dispatcher, ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    await intake_text(dispatcher)
    submission = await get_submission(ctx)
    sid = submission.short_id
    msg_id = wizard_message_id(fake_bale, USER_ID)
    await dispatcher.dispatch(callback_update(f"1|yes|{sid}|", USER_ID, msg_id))
    buttons = wizard_buttons(fake_bale, USER_ID)
    tag_callbacks = [cb for cb in buttons.values() if "|tg|" in cb]
    await dispatcher.dispatch(callback_update(tag_callbacks[0], USER_ID, msg_id))
    await dispatcher.dispatch(callback_update(f"1|ok|{sid}|", USER_ID, msg_id))
    assert any("|edt|" in cb for cb in wizard_buttons(fake_bale, USER_ID).values())
    await dispatcher.dispatch(callback_update(f"1|edt|{sid}|", USER_ID, msg_id))
    labels = list(wizard_buttons(fake_bale, USER_ID))
    assert any("سند" in label for label in labels)
    assert any("|tg|" in cb for cb in wizard_buttons(fake_bale, USER_ID).values())
