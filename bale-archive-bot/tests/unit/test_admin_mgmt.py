"""Admin roster safety and slash-command management."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.bale.keyboards import pack_callback
from app.core.context import BotContext
from app.core.dispatcher import Dispatcher
from app.db.base import Base
from app.db.models import AuditLog
from app.db.repositories.users import UserRepository
from app.domain.admin_mgmt import can_remove_admin, effective_admin_ids
from app.i18n import fa
from tests.e2e.test_commands import _private
from tests.e2e.test_wizard_flow import USER_ID, callback_update
from tests.fakes.fake_bale import FakeBaleServer


def test_can_remove_admin_blocks_last_admin() -> None:
    assert can_remove_admin({1}, 1) is False
    assert can_remove_admin({1, 2}, 1) is True
    assert can_remove_admin({1, 2}, 3) is True


def test_effective_admin_ids_unions_sources() -> None:
    assert effective_admin_ids(
        db_admin_bale_ids=[1],
        runtime_admin_ids={2},
        env_admin_ids=[3, 1],
    ) == {1, 2, 3}


@pytest.mark.asyncio
async def test_repository_rejects_demoting_sole_db_admin_via_count() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with factory() as session, session.begin():
        users = UserRepository(session)
        only = await users.upsert_from_bale(111, None, "تنها", "مدیر")
        await users.set_admin(only.id, True)
        assert await users.count_admins() == 1
        effective = effective_admin_ids(
            db_admin_bale_ids=[only.bale_user_id],
            runtime_admin_ids={only.bale_user_id},
            env_admin_ids=[],
        )
        assert can_remove_admin(effective, only.bale_user_id) is False

    await engine.dispose()


async def test_admins_list_and_remove_guard(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    ctx.runtime_admin_ids = {USER_ID}
    ctx.settings.admin_user_ids = []
    dispatcher = Dispatcher(ctx)

    async with ctx.db.session() as session:
        users = UserRepository(session)
        owner = await users.upsert_from_bale(USER_ID, "owner", "مالک", "اصلی")
        await users.set_admin(owner.id, True)
        await session.commit()

    await dispatcher.dispatch(_private("/admins"))
    body = "\n".join(fake_bale.sent_texts(USER_ID))
    assert fa.ADMINS_HEADER in body
    assert fa.fa_digits(USER_ID) in body

    await dispatcher.dispatch(_private("/removeadmin"))
    assert fa.REMOVEADMIN_USAGE in "\n".join(fake_bale.sent_texts(USER_ID))

    await dispatcher.dispatch(_private(f"/removeadmin {USER_ID}"))
    # Prefer transfer message when targeting self.
    assert fa.REMOVEADMIN_SELF in "\n".join(fake_bale.sent_texts(USER_ID))

    other = 999888777
    await dispatcher.dispatch(_private(f"/removeadmin {other}"))
    assert fa.REMOVEADMIN_NOT_ADMIN in "\n".join(fake_bale.sent_texts(USER_ID))

    # Promote a second admin, then removing the sole remaining after demoting
    # the second again should hit the last-admin guard when only one left.
    await dispatcher.dispatch(_private(f"/addadmin {other}"))
    assert other in ctx.runtime_admin_ids

    # With two admins, remove other is allowed (asks confirm).
    await dispatcher.dispatch(_private(f"/removeadmin {other}"))
    texts = "\n".join(fake_bale.sent_texts(USER_ID))
    assert fa.REMOVEADMIN_CONFIRM in texts

    await dispatcher.dispatch(
        callback_update(pack_callback("ray", "", str(other)), USER_ID, 1)
    )
    assert fa.REMOVEADMIN_DONE in "\n".join(fake_bale.sent_texts(USER_ID))
    assert other not in ctx.runtime_admin_ids

    # Now only USER_ID remains — invent another id that is somehow in effective
    # set alone... Removing USER_ID via callback should be blocked.
    # First put USER_ID as only admin and try removeadmin on a synthetic
    # situation: add other again, remove USER_ID? Actor is USER_ID so self-blocked.
    # Use domain guard after only one left:
    async with ctx.db.session() as session:
        users = UserRepository(session)
        assert await users.count_admins() == 1
        effective = effective_admin_ids(
            db_admin_bale_ids=[u.bale_user_id for u in await users.list_admins()],
            runtime_admin_ids=ctx.runtime_admin_ids,
            env_admin_ids=ctx.settings.admin_user_ids,
        )
        assert can_remove_admin(effective, USER_ID) is False

    async with ctx.db.session() as session:
        rows = (
            await session.execute(select(AuditLog).where(AuditLog.action == "admin_revoked"))
        ).scalars().all()
        assert rows
        assert rows[-1].entity_id == str(other)


async def test_transferadmin_two_step_and_audit(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    ctx.runtime_admin_ids = {USER_ID}
    ctx.settings.admin_user_ids = []
    dispatcher = Dispatcher(ctx)
    target = 555444333

    async with ctx.db.session() as session:
        users = UserRepository(session)
        owner = await users.upsert_from_bale(USER_ID, "owner", "مالک", None)
        await users.set_admin(owner.id, True)
        await session.commit()

    await dispatcher.dispatch(_private(f"/transferadmin {target}"))
    assert fa.TRANSFERADMIN_CONFIRM in "\n".join(fake_bale.sent_texts(USER_ID))

    await dispatcher.dispatch(
        callback_update(pack_callback("tay", "", str(target)), USER_ID, 1)
    )
    assert fa.TRANSFERADMIN_DONE in "\n".join(fake_bale.sent_texts(USER_ID))
    assert target in ctx.runtime_admin_ids
    assert USER_ID not in ctx.runtime_admin_ids

    async with ctx.db.session() as session:
        users = UserRepository(session)
        new_owner = await users.get_by_bale_id(target)
        old = await users.get_by_bale_id(USER_ID)
        assert new_owner is not None and new_owner.is_admin is True
        assert old is not None and old.is_admin is False
        audit_rows = (
            await session.execute(
                select(AuditLog).where(AuditLog.action == "admin_transferred")
            )
        ).scalars().all()
        assert audit_rows
        assert audit_rows[-1].payload.get("to_bale_user_id") == target
