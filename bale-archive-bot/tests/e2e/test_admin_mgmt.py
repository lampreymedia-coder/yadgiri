"""E2E: last admin cannot be removed even after confirmation attempt."""

from __future__ import annotations

from app.bale.keyboards import pack_callback
from app.core.context import BotContext
from app.core.dispatcher import Dispatcher
from app.db.repositories.users import UserRepository
from app.domain.admin_mgmt import can_remove_admin, effective_admin_ids
from app.i18n import fa
from tests.e2e.test_commands import _private
from tests.e2e.test_wizard_flow import USER_ID, callback_update
from tests.fakes.fake_bale import FakeBaleServer


async def test_last_admin_cannot_be_removed(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    ctx.runtime_admin_ids = {USER_ID}
    ctx.settings.admin_user_ids = []
    dispatcher = Dispatcher(ctx)

    async with ctx.db.session() as session:
        users = UserRepository(session)
        owner = await users.upsert_from_bale(USER_ID, "solo", "تنها", "مدیر")
        await users.set_admin(owner.id, True)
        await session.commit()

    # Second admin exists briefly so confirm keyboard can be shown, then we
    # demote them and attempt to revoke the sole remaining admin via callback
    # forged with ray — confirm_removeadmin must refuse.
    other = 700600500
    await dispatcher.dispatch(_private(f"/addadmin {other}"))
    await dispatcher.dispatch(_private(f"/removeadmin {other}"))
    await dispatcher.dispatch(
        callback_update(pack_callback("ray", "", str(other)), USER_ID, 1)
    )

    # Forge a remove-confirm for the last remaining admin (same user).
    await dispatcher.dispatch(
        callback_update(pack_callback("ray", "", str(USER_ID)), USER_ID, 1)
    )
    texts = "\n".join(fake_bale.sent_texts(USER_ID))
    # Self-remove is blocked (owner should use /transferadmin); last-admin
    # guard also applies when actor != target.
    assert fa.REMOVEADMIN_SELF in texts or fa.REMOVEADMIN_LAST in texts or fa.REMOVEADMIN_OWNER in texts

    async with ctx.db.session() as session:
        users = UserRepository(session)
        owner = await users.get_by_bale_id(USER_ID)
        assert owner is not None and owner.is_admin is True
        assert await users.count_admins() == 1
        effective = effective_admin_ids(
            db_admin_bale_ids=[USER_ID],
            runtime_admin_ids=ctx.runtime_admin_ids,
            env_admin_ids=[],
        )
        assert can_remove_admin(effective, USER_ID) is False
