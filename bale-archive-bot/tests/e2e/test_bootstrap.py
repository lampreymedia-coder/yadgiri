"""First-run bootstrap: no .env chat ids required."""

from __future__ import annotations

from app.bale.models import Update
from app.core.context import BotContext
from app.core.dispatcher import Dispatcher
from app.db.repositories.misc import AppSettingsRepository
from app.db.repositories.users import UserRepository
from app.i18n import fa
from tests.fakes.fake_bale import FakeBaleServer

OWNER_ID = 4242
ARCHIVE_GROUP = -100700800


def _clear_bootstrap(ctx: BotContext) -> None:
    ctx.runtime_admin_ids.clear()
    ctx.settings.admin_user_ids.clear()
    ctx.archive_chat_id = None
    ctx.admin_notify_chat_id = None


async def test_first_private_start_promotes_owner(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    _clear_bootstrap(ctx)
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900001,
                "message": {
                    "message_id": 1,
                    "date": 1,
                    "chat": {"id": OWNER_ID, "type": "private"},
                    "from": {
                        "id": OWNER_ID,
                        "is_bot": False,
                        "first_name": "مینا",
                    },
                    "text": "/start",
                },
            }
        )
    )
    assert OWNER_ID in ctx.runtime_admin_ids
    assert ctx.admin_notify_chat_id == OWNER_ID
    texts = "\n".join(fake_bale.sent_texts(OWNER_ID))
    assert "/archive" in texts
    async with ctx.db.session() as session:
        user = await UserRepository(session).get_by_bale_id(OWNER_ID)
        assert user is not None
        assert user.is_admin is True
        owner = await AppSettingsRepository(session).get("owner_user_id")
        assert int(owner) == OWNER_ID


async def test_group_archive_command_asks_hashtag_privately(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    _clear_bootstrap(ctx)
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900002,
                "message": {
                    "message_id": 2,
                    "date": 1,
                    "chat": {
                        "id": ARCHIVE_GROUP,
                        "type": "group",
                        "title": "آرشیو خصوصی",
                    },
                    "from": {
                        "id": OWNER_ID,
                        "is_bot": False,
                        "first_name": "مینا",
                    },
                    "text": "/archive",
                },
            }
        )
    )
    assert OWNER_ID in ctx.runtime_admin_ids
    texts = "\n".join(fake_bale.sent_texts(OWNER_ID))
    assert "هشتگ" in texts
    assert fake_bale.last_markup(ARCHIVE_GROUP) is None
    markup = fake_bale.last_markup(OWNER_ID)
    assert markup is not None
    stg = next(
        btn["callback_data"]
        for row in markup["inline_keyboard"]
        for btn in row
        if "|stg|" in btn.get("callback_data", "")
    )
    msg_id = next(
        m.message_id
        for m in fake_bale.messages.values()
        if m.chat_id == OWNER_ID and m.reply_markup and not m.deleted
    )
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 9000021,
                "callback_query": {
                    "id": "cb-stg",
                    "from": {"id": OWNER_ID, "is_bot": False, "first_name": "مینا"},
                    "message": {
                        "message_id": msg_id,
                        "chat": {"id": OWNER_ID, "type": "private"},
                        "text": "pick",
                    },
                    "data": stg,
                },
            }
        )
    )
    assert ctx.archive_chat_id == ARCHIVE_GROUP
    async with ctx.db.session() as session:
        stored = await AppSettingsRepository(session).get("archive_chat_id")
        assert int(stored) == ARCHIVE_GROUP
    assert "ثبت شد" in "\n".join(fake_bale.sent_texts(OWNER_ID))
    assert not any("ثبت شد" in t for t in fake_bale.sent_texts(ARCHIVE_GROUP))


async def test_persian_archive_word_registers_chat(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    _clear_bootstrap(ctx)
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900003,
                "message": {
                    "message_id": 3,
                    "date": 1,
                    "chat": {
                        "id": ARCHIVE_GROUP,
                        "type": "group",
                        "title": "آرشیو خصوصی",
                    },
                    "from": {
                        "id": OWNER_ID,
                        "is_bot": False,
                        "first_name": "مینا",
                    },
                    "text": "آرشیوم",
                },
            }
        )
    )
    assert OWNER_ID in ctx.runtime_admin_ids
    texts = "\n".join(fake_bale.sent_texts(OWNER_ID))
    assert "هشتگ" in texts
    assert fake_bale.last_markup(ARCHIVE_GROUP) is None


async def test_group_start_asks_role(ctx: BotContext, fake_bale: FakeBaleServer) -> None:
    _clear_bootstrap(ctx)
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900010,
                "message": {
                    "message_id": 4,
                    "date": 1,
                    "chat": {"id": -100200300, "type": "group", "title": "رصد"},
                    "from": {
                        "id": OWNER_ID,
                        "is_bot": False,
                        "first_name": "مینا",
                    },
                    "text": "/start",
                },
            }
        )
    )
    texts = "\n".join(fake_bale.sent_texts(OWNER_ID))
    assert "نقش این گروه" in texts
    markup = fake_bale.last_markup(OWNER_ID)
    assert markup is not None
    labels = [btn["text"] for row in markup["inline_keyboard"] for btn in row]
    assert any("رصد" in label for label in labels)
    assert any("آرشیو" in label for label in labels)
    assert fake_bale.last_markup(-100200300) is None


async def test_group_start_without_chat_type_still_asks_role(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    _clear_bootstrap(ctx)
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900012,
                "message": {
                    "message_id": 6,
                    "date": 1,
                    "chat": {"id": -100200302, "title": "رصد بدون نوع"},
                    "from": {
                        "id": OWNER_ID,
                        "is_bot": False,
                        "first_name": "مینا",
                    },
                    "text": "/start",
                },
            }
        )
    )
    texts = "\n".join(fake_bale.sent_texts(OWNER_ID))
    assert "نقش این گروه" in texts
    assert fake_bale.last_markup(-100200302) is None


async def test_bot_added_singular_member_asks_role(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    _clear_bootstrap(ctx)
    ctx.bot_user_id = fake_bale.bot_id
    fake_bale.set_chat_member_status(-100200301, OWNER_ID, "creator")
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900011,
                "message": {
                    "message_id": 5,
                    "date": 1,
                    "chat": {"id": -100200301, "type": "group", "title": "تیم"},
                    "from": {
                        "id": OWNER_ID,
                        "is_bot": False,
                        "first_name": "مینا",
                    },
                    "new_chat_member": {
                        "id": fake_bale.bot_id,
                        "is_bot": True,
                        "first_name": "Archive",
                    },
                },
            }
        )
    )
    texts = "\n".join(fake_bale.sent_texts(OWNER_ID))
    assert "نقش این گروه" in texts
    assert fake_bale.last_markup(-100200301) is None
    assert fake_bale.calls_for("leaveChat") == []


async def test_non_admin_cannot_add_bot_to_group(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    ctx.bot_user_id = fake_bale.bot_id
    ctx.runtime_admin_ids = {111}
    dispatcher = Dispatcher(ctx)
    stranger = 999001
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900020,
                "message": {
                    "message_id": 20,
                    "date": 1,
                    "chat": {"id": -100200399, "type": "group", "title": "گروه غریبه"},
                    "from": {
                        "id": stranger,
                        "is_bot": False,
                        "first_name": "مهمان",
                    },
                    "new_chat_member": {
                        "id": fake_bale.bot_id,
                        "is_bot": True,
                        "first_name": "Archive",
                    },
                },
            }
        )
    )
    leave_calls = fake_bale.calls_for("leaveChat")
    assert leave_calls
    assert str(-100200399) in str(leave_calls[0].get("chat_id"))
    assert "نقش این گروه" not in "\n".join(fake_bale.sent_texts(stranger))
    assert any("خارج" in t for t in fake_bale.sent_texts(-100200399))
    assert any("مدیر" in t for t in fake_bale.sent_texts(stranger))
    assert any("گروه غریبه" in t for t in fake_bale.sent_texts(111))


async def test_admin_add_keeps_bot_and_asks_role(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    ctx.bot_user_id = fake_bale.bot_id
    ctx.runtime_admin_ids = {111}
    fake_bale.set_chat_member_status(-100200400, 111, "creator")
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900021,
                "message": {
                    "message_id": 21,
                    "date": 1,
                    "chat": {"id": -100200400, "type": "group", "title": "رصد تازه"},
                    "from": {
                        "id": 111,
                        "is_bot": False,
                        "first_name": "مدیر",
                    },
                    "new_chat_member": {
                        "id": fake_bale.bot_id,
                        "is_bot": True,
                        "first_name": "Archive",
                    },
                },
            }
        )
    )
    assert fake_bale.calls_for("leaveChat") == []
    assert "نقش این گروه" in "\n".join(fake_bale.sent_texts(111))
    assert "ادمین" in "\n".join(fake_bale.sent_texts(111))


async def test_non_owner_group_admin_can_add_and_choose_role(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    ctx.bot_user_id = fake_bale.bot_id
    ctx.runtime_admin_ids = {111}
    chat_id = -100200403
    fake_bale.set_chat_member_status(chat_id, 111, "administrator")
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900027,
                "message": {
                    "message_id": 27,
                    "date": 1,
                    "chat": {"id": chat_id, "type": "group", "title": "مالک دیگر"},
                    "from": {
                        "id": 111,
                        "is_bot": False,
                        "first_name": "مدیر",
                    },
                    "new_chat_member": {
                        "id": fake_bale.bot_id,
                        "is_bot": True,
                        "first_name": "Archive",
                    },
                },
            }
        )
    )
    assert fake_bale.calls_for("leaveChat") == []
    text = "\n".join(fake_bale.sent_texts(111))
    assert "نقش این گروه" in text
    assert "مالک‌بودن" not in text


async def test_bot_admin_who_is_not_group_admin_cannot_add(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    ctx.bot_user_id = fake_bale.bot_id
    ctx.runtime_admin_ids = {111}
    chat_id = -100200404
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900028,
                "message": {
                    "message_id": 28,
                    "date": 1,
                    "chat": {"id": chat_id, "type": "group", "title": "بدون مدیر گروه"},
                    "from": {
                        "id": 111,
                        "is_bot": False,
                        "first_name": "مدیر ربات",
                    },
                    "new_chat_member": {
                        "id": fake_bale.bot_id,
                        "is_bot": True,
                        "first_name": "Archive",
                    },
                },
            }
        )
    )
    assert fake_bale.calls_for("leaveChat")
    assert "نقش این گروه" not in "\n".join(fake_bale.sent_texts(111))


async def test_group_admin_add_auto_registers_research_and_accepts_ordinary_forward(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    import asyncio

    from sqlalchemy import select

    from app.db.models import Submission

    ctx.bot_user_id = fake_bale.bot_id
    ctx.runtime_admin_ids = {111}
    chat_id = -100200401
    admin_id = 777
    fake_bale.set_chat_member_status(chat_id, admin_id, "administrator")
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900023,
                "message": {
                    "message_id": 23,
                    "date": 1,
                    "chat": {"id": chat_id, "type": "group", "title": "رصد مالک"},
                    "from": {
                        "id": admin_id,
                        "is_bot": False,
                        "first_name": "مدیر",
                    },
                    "new_chat_member": {
                        "id": fake_bale.bot_id,
                        "is_bot": True,
                        "first_name": "Archive",
                    },
                },
            }
        )
    )
    assert fake_bale.calls_for("leaveChat") == []
    admin_text = "\n".join(fake_bale.sent_texts(admin_id))
    assert "رصد فعال شد" in admin_text
    assert "بدون منشن" in admin_text

    for update_id, message_id, user_id, payload in (
        (900024, 24, 778, {"text": "متن عادی گروه مالک"}),
        (
            900025,
            25,
            779,
            {
                "text": "متن فورواردشده",
                "forward_from_chat": {
                    "id": -800,
                    "type": "channel",
                    "title": "منبع",
                },
                "forward_from_message_id": 10,
                "forward_date": 1,
            },
        ),
    ):
        await dispatcher.dispatch(
            Update.model_validate(
                {
                    "update_id": update_id,
                    "message": {
                        "message_id": message_id,
                        "date": 1,
                        "chat": {
                            "id": chat_id,
                            "type": "group",
                            "title": "رصد مالک",
                        },
                        "from": {
                            "id": user_id,
                            "is_bot": False,
                            "first_name": "عضو",
                        },
                        **payload,
                    },
                }
            )
        )
    await asyncio.sleep(0.2)
    assert fake_bale.last_markup(778) is not None
    assert fake_bale.last_markup(779) is not None
    async with ctx.db.session() as session:
        submissions = (
            (
                await session.execute(
                    select(Submission)
                    .where(Submission.original_message_id.in_([24, 25]))
                    .order_by(Submission.original_message_id)
                )
            )
            .scalars()
            .all()
        )
        assert [item.text_content for item in submissions] == [
            "متن عادی گروه مالک",
            "متن فورواردشده",
        ]
        assert [item.is_forwarded for item in submissions] == [False, True]


async def test_bot_added_as_member_waits_for_admin_promotion_without_leaving(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    from app.db.repositories.groups import GroupRepository

    ctx.bot_user_id = fake_bale.bot_id
    ctx.runtime_admin_ids = {111}
    chat_id = -100200402
    fake_bale.set_chat_member_status(chat_id, fake_bale.bot_id, "member")
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900026,
                "message": {
                    "message_id": 26,
                    "date": 1,
                    "chat": {"id": chat_id, "type": "group", "title": "بدون دسترسی"},
                    "from": {
                        "id": 111,
                        "is_bot": False,
                        "first_name": "مدیر",
                    },
                    "new_chat_member": {
                        "id": fake_bale.bot_id,
                        "is_bot": True,
                        "first_name": "Archive",
                    },
                },
            }
        )
    )
    assert fake_bale.calls_for("leaveChat") == []
    texts = "\n".join(fake_bale.sent_texts(111))
    assert "خارج نمی‌شود" in texts
    assert "ارتقا" in texts
    async with ctx.db.session() as session:
        group = await GroupRepository(session).get_by_bale_id(chat_id)
        assert group is not None
        assert group.is_active is True
        assert group.settings.get("pending_admin") is True


async def test_group_admin_can_add_then_promote_and_first_plain_text_is_processed(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    import asyncio

    from app.db.repositories.groups import GroupRepository

    ctx.bot_user_id = fake_bale.bot_id
    ctx.runtime_admin_ids = {111}
    chat_id = -100200405
    admin_id = 777
    fake_bale.set_chat_member_status(chat_id, fake_bale.bot_id, "member")
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900029,
                "message": {
                    "message_id": 29,
                    "date": 1,
                    "chat": {"id": chat_id, "type": "group", "title": "افزودن سپس مدیر"},
                    "from": {
                        "id": admin_id,
                        "is_bot": False,
                        "first_name": "مدیر گروه",
                    },
                    "new_chat_member": {
                        "id": fake_bale.bot_id,
                        "is_bot": True,
                        "first_name": "Archive",
                    },
                },
            }
        )
    )
    assert fake_bale.calls_for("leaveChat") == []

    fake_bale.set_chat_member_status(chat_id, fake_bale.bot_id, "administrator")
    fake_bale.set_chat_member_status(chat_id, admin_id, "administrator")
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900030,
                "message": {
                    "message_id": 30,
                    "date": 1,
                    "chat": {"id": chat_id, "type": "group", "title": "افزودن سپس مدیر"},
                    "from": {
                        "id": 778,
                        "is_bot": False,
                        "first_name": "عضو",
                    },
                    "text": "اولین متن عادی بعد از مدیرشدن",
                },
            }
        )
    )
    await asyncio.sleep(0.2)
    assert fake_bale.last_markup(778) is not None
    async with ctx.db.session() as session:
        group = await GroupRepository(session).get_by_bale_id(chat_id)
        assert group is not None
        assert group.settings.get("pending_admin") is False
        assert group.settings.get("role") == "research"


async def test_member_start_has_no_add_to_group_button(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900022,
                "message": {
                    "message_id": 22,
                    "date": 1,
                    "chat": {"id": 55555, "type": "private"},
                    "from": {
                        "id": 55555,
                        "is_bot": False,
                        "first_name": "عضو",
                    },
                    "text": "/start",
                },
            }
        )
    )
    markup = fake_bale.last_markup(55555)
    labels = []
    if markup:
        labels = [btn["text"] for row in markup["inline_keyboard"] for btn in row]
    assert fa.BTN_ADD_TO_GROUP not in labels


async def test_admin_start_has_add_to_group_button(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    ctx.runtime_admin_ids = {111}
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900023,
                "message": {
                    "message_id": 23,
                    "date": 1,
                    "chat": {"id": 111, "type": "private"},
                    "from": {
                        "id": 111,
                        "is_bot": False,
                        "first_name": "مدیر",
                    },
                    "text": "/start",
                },
            }
        )
    )
    markup = fake_bale.last_markup(111)
    assert markup is not None
    labels = [btn["text"] for row in markup["inline_keyboard"] for btn in row]
    assert fa.BTN_ADD_TO_GROUP in labels


async def test_group_content_opens_wizard_in_private(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    import asyncio

    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900004,
                "message": {
                    "message_id": 11,
                    "date": 1,
                    "chat": {"id": -100200300, "type": "group", "title": "رصد"},
                    "from": {
                        "id": 12345,
                        "is_bot": False,
                        "first_name": "علی",
                    },
                    "text": "این یک متن آزمایشی برای بایگانی است",
                },
            }
        )
    )
    await asyncio.sleep(0.2)
    markup = fake_bale.last_markup(12345)
    assert markup is not None
    data = [btn.get("callback_data", "") for row in markup["inline_keyboard"] for btn in row]
    assert any("|yes|" in item for item in data)
    assert fake_bale.last_markup(-100200300) is None


async def test_second_research_group_content_opens_its_own_wizard(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    import asyncio

    from app.db.repositories.groups import GroupRepository
    from app.handlers.admin import persist_research_chat

    dispatcher = Dispatcher(ctx)
    first = -100200300
    second = -100200399
    async with ctx.db.session() as session:
        await persist_research_chat(session, first, title="رصد یک")
        await persist_research_chat(session, second, title="رصد دو")

    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900040,
                "message": {
                    "message_id": 40,
                    "date": 1,
                    "chat": {"id": second, "type": "group", "title": "رصد دو"},
                    "from": {
                        "id": 12345,
                        "is_bot": False,
                        "first_name": "علی",
                    },
                    "text": "پیام گروه رصد دوم",
                },
            }
        )
    )
    await asyncio.sleep(0.2)
    assert fake_bale.last_markup(12345) is not None
    private = "\n".join(fake_bale.sent_texts(12345))
    assert "رصد دو" in private
    async with ctx.db.session() as session:
        groups = GroupRepository(session)
        found = await groups.get_by_bale_id(second)
        assert found is not None
        assert found.settings.get("role") == "research"


async def test_start_in_existing_research_group_asks_to_admin_not_role(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    _clear_bootstrap(ctx)
    from app.handlers.admin import persist_research_chat

    async with ctx.db.session() as session:
        await persist_research_chat(session, -100200300, title="رصد")
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900041,
                "message": {
                    "message_id": 41,
                    "date": 1,
                    "chat": {"id": -100200300, "type": "group", "title": "رصد"},
                    "from": {
                        "id": OWNER_ID,
                        "is_bot": False,
                        "first_name": "مینا",
                    },
                    "text": "/start",
                },
            }
        )
    )
    texts = "\n".join(fake_bale.sent_texts(OWNER_ID))
    assert "ادمین" in texts
    assert "نقش این گروه" not in texts
    assert fake_bale.last_markup(OWNER_ID) is None


async def test_bare_mention_in_research_group_asks_to_admin_not_role(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    from app.handlers.admin import persist_research_chat

    async with ctx.db.session() as session:
        await persist_research_chat(session, -100200300, title="رصد")
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900042,
                "message": {
                    "message_id": 42,
                    "date": 1,
                    "chat": {"id": -100200300, "type": "group", "title": "رصد"},
                    "from": {
                        "id": 111,
                        "is_bot": False,
                        "first_name": "مدیر",
                    },
                    "text": f"@{fake_bale.bot_username}",
                },
            }
        )
    )
    texts = "\n".join(fake_bale.sent_texts(111))
    assert "ادمین" in texts
    assert "نقش این گروه" not in texts
    assert fake_bale.last_markup(111) is None


async def test_research_choice_then_content_opens_wizard(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    import asyncio

    ctx.bot_user_id = fake_bale.bot_id
    ctx.runtime_admin_ids = {111}
    chat_id = -100200777
    fake_bale.set_chat_member_status(chat_id, 111, "creator")
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900043,
                "message": {
                    "message_id": 43,
                    "date": 1,
                    "chat": {"id": chat_id, "type": "group", "title": "رصد سوم"},
                    "from": {
                        "id": 111,
                        "is_bot": False,
                        "first_name": "مدیر",
                    },
                    "new_chat_member": {
                        "id": fake_bale.bot_id,
                        "is_bot": True,
                        "first_name": "Archive",
                    },
                },
            }
        )
    )
    markup = fake_bale.last_markup(111)
    assert markup is not None
    srg = next(
        btn["callback_data"]
        for row in markup["inline_keyboard"]
        for btn in row
        if "|srg|" in btn.get("callback_data", "")
    )
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900044,
                "callback_query": {
                    "id": "cb-srg",
                    "from": {"id": 111, "is_bot": False, "first_name": "مدیر"},
                    "message": {
                        "message_id": 1,
                        "chat": {"id": 111, "type": "private"},
                        "text": "role",
                    },
                    "data": srg,
                },
            }
        )
    )
    after_choice = "\n".join(fake_bale.sent_texts(111))
    assert "رصد سوم" in after_choice
    assert "ادمین" in after_choice
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900045,
                "message": {
                    "message_id": 45,
                    "date": 1,
                    "chat": {"id": chat_id, "type": "group", "title": "رصد سوم"},
                    "from": {
                        "id": 12345,
                        "is_bot": False,
                        "first_name": "علی",
                    },
                    "text": "متن برای بایگانی در گروه سوم",
                },
            }
        )
    )
    await asyncio.sleep(0.2)
    assert fake_bale.last_markup(12345) is not None
    assert "رصد سوم" in "\n".join(fake_bale.sent_texts(12345))


async def test_mention_with_content_opens_wizard_without_archiving_mention(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    import asyncio

    from sqlalchemy import select

    from app.db.models import Submission
    from app.handlers.admin import persist_research_chat

    chat_id = -100200778
    async with ctx.db.session() as session:
        await persist_research_chat(session, chat_id, title="رصد منشن")
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(
        Update.model_validate(
            {
                "update_id": 900046,
                "message": {
                    "message_id": 46,
                    "date": 1,
                    "chat": {"id": chat_id, "type": "group", "title": "رصد منشن"},
                    "from": {
                        "id": 12346,
                        "is_bot": False,
                        "first_name": "سارا",
                    },
                    "text": f"@{fake_bale.bot_username} متن مسیر جایگزین",
                },
            }
        )
    )
    await asyncio.sleep(0.2)
    assert fake_bale.last_markup(12346) is not None
    async with ctx.db.session() as session:
        submission = (
            await session.execute(
                select(Submission).where(Submission.original_message_id == 46)
            )
        ).scalar_one()
        assert submission.text_content == "متن مسیر جایگزین"
        assert fake_bale.bot_username not in submission.text_content
