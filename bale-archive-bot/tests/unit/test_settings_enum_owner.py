"""App settings JSON + claimowner + MSSQL-shaped submission completion."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import mssql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.bale.models import Update
from app.core.context import BotContext
from app.core.dispatcher import Dispatcher
from app.db.base import Base, _PortableJSON
from app.db.models import AuditLog, ContentType, Submission, SubmissionStatus
from app.db.repositories.groups import GroupRepository
from app.db.repositories.misc import AppSettingsRepository
from app.db.repositories.submissions import SubmissionRepository
from app.db.repositories.tags import TagRepository
from app.db.repositories.users import UserRepository
from app.i18n import fa
from app.workers.ttl_sweeper import run_reminders_once
from tests.e2e.test_commands import _private
from tests.e2e.test_wizard_flow import USER_ID, load_update
from tests.fakes.fake_bale import FakeBaleServer


def _private_as(user_id: int, text: str) -> Update:
    payload = load_update("text")
    payload["message"]["chat"] = {"id": user_id, "type": "private"}
    payload["message"]["from"]["id"] = user_id
    payload["message"]["text"] = text
    return Update.model_validate(payload)


@pytest.mark.asyncio
async def test_app_settings_int_roundtrip_and_mssql_bind() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    owner_id = 1_290_496_049
    async with factory() as session, session.begin():
        repo = AppSettingsRepository(session)
        await repo.set("owner_user_id", owner_id)
        await repo.set("admin_notify_chat_id", owner_id)

    async with factory() as session:
        repo = AppSettingsRepository(session)
        assert await repo.get("owner_user_id") == owner_id
        assert int(await repo.get("owner_user_id")) == owner_id

    # MSSQL bind must be ISJSON-safe object text, not a bare digit string.
    dialect = mssql.dialect()
    col = _PortableJSON()
    bound = col.process_bind_param(owner_id, dialect)
    assert isinstance(bound, str)
    assert json.loads(bound) == {"__scalar__": owner_id}
    assert col.process_result_value(bound, dialect) == owner_id

    await engine.dispose()


async def test_claimowner_sets_owner_when_unset(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    ctx.runtime_admin_ids = set()
    ctx.settings.admin_user_ids = []
    dispatcher = Dispatcher(ctx)

    await dispatcher.dispatch(_private("/claimowner"))
    assert fa.CLAIMOWNER_DONE in "\n".join(fake_bale.sent_texts(USER_ID))
    assert USER_ID in ctx.runtime_admin_ids

    async with ctx.db.session() as session:
        stored = AppSettingsRepository(session)
        assert int(await stored.get("owner_user_id")) == USER_ID
        users = UserRepository(session)
        user = await users.get_by_bale_id(USER_ID)
        assert user is not None and user.is_admin is True
        audits = (
            await session.execute(select(AuditLog).where(AuditLog.action == "owner_claimed"))
        ).scalars().all()
        assert audits

    stranger = 424242
    await dispatcher.dispatch(_private_as(stranger, "/claimowner"))
    assert fa.CLAIMOWNER_DENIED in "\n".join(fake_bale.sent_texts(stranger))


async def test_owner_cannot_be_removed_without_transfer(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    ctx.runtime_admin_ids = {USER_ID}
    ctx.settings.admin_user_ids = []
    dispatcher = Dispatcher(ctx)
    other = 888777666

    async with ctx.db.session() as session:
        users = UserRepository(session)
        owner = await users.upsert_from_bale(USER_ID, None, "مالک", None)
        await users.set_admin(owner.id, True)
        helper = await users.upsert_from_bale(other, None, "کمک", None)
        await users.set_admin(helper.id, True)
        await AppSettingsRepository(session).set("owner_user_id", USER_ID)
        await session.commit()

    ctx.runtime_admin_ids.add(other)
    await dispatcher.dispatch(_private(f"/removeadmin {USER_ID}"))
    assert fa.REMOVEADMIN_SELF in "\n".join(fake_bale.sent_texts(USER_ID))

    await dispatcher.dispatch(_private_as(other, f"/removeadmin {USER_ID}"))
    assert fa.REMOVEADMIN_OWNER in "\n".join(fake_bale.sent_texts(other))


@pytest.mark.asyncio
async def test_submission_reaches_completed_with_mssql_enum_simulation(
    ctx: BotContext,
) -> None:
    """Create → tag → complete, and prove MSSQL enum processors keep .value safe."""
    dialect = mssql.dialect()
    content_col = Submission.__table__.c.content_type
    status_col = Submission.__table__.c.status

    async with ctx.db.session() as session:
        users = UserRepository(session)
        user = await users.upsert_from_bale(USER_ID, "ali", "علی", None)
        groups = GroupRepository(session)
        group = await groups.upsert(-1001, "گروه", "group")
        subs = SubmissionRepository(session)
        submission = await subs.create_draft(
            user_id=user.id,
            group_id=group.id,
            content_type=ContentType.TEXT,
            content_subtype=None,
            text_content="سنجش مسیر تکمیل",
            text_normalized="سنجش مسیر تکمیل",
            caption=None,
            urls=[],
            is_forwarded=False,
            forward_source=None,
            original_message_id=1,
            raw_update={"probe": True},
            ttl_minutes=30,
        )
        tags = TagRepository(session)
        active = await tags.list_active()
        await subs.set_tags(submission, [active[0].id])
        await subs.set_status(submission, SubmissionStatus.COMPLETED)
        short_id = submission.short_id
        await session.commit()

    # Simulate what SQL Server returns (plain strings) then rehydrate.
    raw_type = content_col.type.process_bind_param(ContentType.TEXT, dialect)
    raw_status = status_col.type.process_bind_param(SubmissionStatus.COMPLETED, dialect)
    assert raw_type == "text"
    assert raw_status == "completed"
    hydrated_type = content_col.type.process_result_value(raw_type, dialect)
    hydrated_status = status_col.type.process_result_value(raw_status, dialect)
    assert hydrated_type is ContentType.TEXT
    assert hydrated_status is SubmissionStatus.COMPLETED
    # ttl_sweeper line must not crash:
    assert hydrated_type.value == "text"

    async with ctx.db.session() as session:
        loaded = (
            await session.execute(select(Submission).where(Submission.short_id == short_id))
        ).scalar_one()
        assert loaded.status is SubmissionStatus.COMPLETED
        assert loaded.content_type is ContentType.TEXT
        assert loaded.content_type.value == "text"

    # Reminder path builds content_type.value for in-progress rows without error.
    async with ctx.db.session() as session:
        users = UserRepository(session)
        user = await users.get_by_bale_id(USER_ID)
        assert user is not None
        groups = GroupRepository(session)
        group = await groups.upsert(-1002, "گروه۲", "group")
        subs = SubmissionRepository(session)
        draft = await subs.create_draft(
            user_id=user.id,
            group_id=group.id,
            content_type=ContentType.VOICE,
            content_subtype=None,
            text_content=None,
            text_normalized=None,
            caption=None,
            urls=[],
            is_forwarded=False,
            forward_source=None,
            original_message_id=2,
            raw_update=None,
            ttl_minutes=30,
        )
        draft.wizard_chat_id = USER_ID
        from datetime import UTC, datetime, timedelta

        draft.created_at = datetime.now(UTC) - timedelta(minutes=20)
        await session.commit()

    # Force reminded path: list_needing_reminder uses age; run_reminders_once
    # must read .value successfully even if dialect returned str (processor tested above).
    sent = await run_reminders_once(ctx)
    assert sent >= 0
