"""Admin panel buttons must return real content on SQLite, not a degraded spool."""

from __future__ import annotations

from app.bale.models import Update
from app.core.context import BotContext
from app.core.dispatcher import Dispatcher
from app.db.models import ContentType, SubmissionStatus
from app.db.repositories.groups import GroupRepository
from app.db.repositories.submissions import SubmissionRepository
from app.db.repositories.tags import TagRepository
from app.db.repositories.users import UserRepository
from app.i18n import fa
from tests.e2e.test_commands import _private
from tests.e2e.test_wizard_flow import USER_ID, callback_update, wizard_buttons
from tests.fakes.fake_bale import FakeBaleServer


async def _seed_completed_item(ctx: BotContext) -> None:
    async with ctx.db.session() as session:
        users = UserRepository(session)
        user = await users.upsert_from_bale(USER_ID, "ali", "علی", "احمدی")
        groups = GroupRepository(session)
        group = await groups.upsert(-100200300, "گروه پژوهش", "group")
        subs = SubmissionRepository(session)
        submission = await subs.create_draft(
            user_id=user.id,
            group_id=group.id,
            content_type=ContentType.TEXT,
            content_subtype=None,
            text_content="یادداشت آزمایشی",
            text_normalized="یادداشت ازمایشی",
            caption=None,
            urls=[],
            is_forwarded=False,
            forward_source=None,
            original_message_id=11,
            raw_update=None,
            ttl_minutes=30,
        )
        tags = TagRepository(session)
        active = await tags.list_active()
        await subs.set_tags(submission, [active[0].id])
        await subs.set_status(submission, SubmissionStatus.COMPLETED)


def _tap(buttons: dict[str, str], label: str) -> Update:
    return callback_update(buttons[label], USER_ID, 1)


async def test_admin_panel_buttons_return_content(
    ctx: BotContext, fake_bale: FakeBaleServer
) -> None:
    ctx.runtime_admin_ids = {USER_ID}
    await _seed_completed_item(ctx)
    dispatcher = Dispatcher(ctx)

    await dispatcher.dispatch(_private("/panel"))
    assert fa.PANEL_HEADER in "\n".join(fake_bale.sent_texts(USER_ID))
    buttons = wizard_buttons(fake_bale, USER_ID)
    for label in (
        fa.BTN_PANEL_STATS,
        fa.BTN_PANEL_TOP_USERS,
        fa.BTN_PANEL_TOP_TAGS,
        fa.BTN_PANEL_TAGS,
        fa.BTN_PANEL_GROUPS,
        fa.BTN_PANEL_HEALTH,
        fa.BTN_PANEL_SETTINGS,
        fa.BTN_PANEL_EXPORT,
    ):
        assert label in buttons

    await dispatcher.dispatch(_tap(buttons, fa.BTN_PANEL_STATS))
    await dispatcher.dispatch(_tap(buttons, fa.BTN_PANEL_TOP_USERS))
    await dispatcher.dispatch(_tap(buttons, fa.BTN_PANEL_TOP_TAGS))
    await dispatcher.dispatch(_tap(buttons, fa.BTN_PANEL_TAGS))
    await dispatcher.dispatch(_tap(buttons, fa.BTN_PANEL_GROUPS))
    await dispatcher.dispatch(_tap(buttons, fa.BTN_PANEL_HEALTH))
    await dispatcher.dispatch(_tap(buttons, fa.BTN_PANEL_SETTINGS))
    await dispatcher.dispatch(_tap(buttons, fa.BTN_PANEL_EXPORT))

    texts = "\n".join(fake_bale.sent_texts(USER_ID))
    assert fa.ERR_DEGRADED not in texts
    assert fa.ERR_GENERIC not in texts
    assert "گزارش کلی آرشیو" in texts
    assert fa.TOP_USERS_HEADER in texts
    assert fa.TOP_TAGS_HEADER in texts
    assert fa.TAGS_HEADER in texts
    assert fa.GROUPS_HEADER in texts
    assert fa.HEALTH_HEADER in texts
    assert fa.SETTINGS_HEADER in texts
    assert fa.EXPORT_PREPARING in texts
    assert "علی احمدی" in texts
    assert "یادگیری" in texts
    assert fake_bale.calls_for("sendDocument")


async def test_admin_slash_health_and_export(ctx: BotContext, fake_bale: FakeBaleServer) -> None:
    ctx.runtime_admin_ids = {USER_ID}
    await _seed_completed_item(ctx)
    dispatcher = Dispatcher(ctx)
    await dispatcher.dispatch(_private("/health"))
    await dispatcher.dispatch(_private("/export"))
    texts = "\n".join(fake_bale.sent_texts(USER_ID))
    assert fa.HEALTH_HEADER in texts
    assert fa.EXPORT_PREPARING in texts
    assert fa.ERR_DEGRADED not in texts
    assert fake_bale.calls_for("sendDocument")
