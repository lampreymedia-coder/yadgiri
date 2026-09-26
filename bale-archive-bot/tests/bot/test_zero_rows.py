"""Section 3 of CLAUDE-BOT-FIX.md: without the full confirmation nothing is written.

Every test here ends with Post, PostHashtag and PostMedia holding exactly 0 rows.
"""

from __future__ import annotations

from app.handlers.wizard import expire_and_remind
from tests.bot.harness import (
    ARCHIVE,
    ARCHIVE_ID,
    GROUP,
    GROUP_ID,
    UNKNOWN_GROUP,
    USER,
    Harness,
)


def assert_no_post(h: Harness) -> None:
    assert h.count("Post") == 0
    assert h.count("PostHashtag") == 0
    assert h.count("PostMedia") == 0


async def test_no_writes_nothing(h: Harness) -> None:
    h.register_group()
    origin = await h.text(GROUP, USER, "یک متن برای آرشیو")
    sid = h.sid()
    await h.press(USER, "n", sid)
    assert_no_post(h)
    assert h.ctx.wizards.get(sid) is None
    assert (GROUP_ID, origin) not in h.deleted()  # original message is never deleted


async def test_cancel_on_first_question_writes_nothing(h: Harness) -> None:
    h.register_group()
    await h.text(GROUP, USER, "متن")
    await h.press(USER, "x", h.sid())
    assert_no_post(h)


async def test_cancel_after_choosing_hashtags_writes_nothing(h: Harness) -> None:
    h.register_group()
    await h.text(GROUP, USER, "متن")
    sid = h.sid()
    await h.press(USER, "y", sid)
    await h.press(USER, "t", sid, "1")
    await h.press(USER, "t", sid, "2")
    await h.press(USER, "x", sid)
    assert_no_post(h)


async def test_cancel_on_preview_writes_nothing(h: Harness) -> None:
    h.register_group()
    await h.send(GROUP, USER, photo=[{"file_id": "p1", "width": 10, "height": 10, "file_size": 100}])
    sid = h.sid()
    await h.press(USER, "y", sid)
    await h.press(USER, "t", sid, "1")
    await h.press(USER, "c", sid)
    await h.press(USER, "x", sid)
    assert_no_post(h)
    assert not h.fake.calls_for("copyMessage") or all(
        int(p["chat_id"]) != ARCHIVE_ID for p in h.fake.calls_for("copyMessage")
    )


async def test_expired_wizard_writes_nothing(h: Harness) -> None:
    h.register_group()
    await h.text(GROUP, USER, "متن")
    sid = h.sid()
    await h.press(USER, "y", sid)
    await h.press(USER, "t", sid, "1")
    await h.press(USER, "c", sid)
    h.ctx.wizards.get(sid).created_at -= 31 * 60  # type: ignore[union-attr]
    await expire_and_remind(h.ctx)
    assert h.ctx.wizards.get(sid) is None
    await h.press(USER, "f", sid)  # a late tap on the old preview
    assert_no_post(h)


async def test_continue_without_hashtag_is_refused(h: Harness) -> None:
    h.register_group()
    await h.text(GROUP, USER, "متن")
    sid = h.sid()
    await h.press(USER, "y", sid)
    await h.press(USER, "c", sid)  # nothing selected
    await h.press(USER, "f", sid)  # final is not reachable from the hashtag step
    assert_no_post(h)
    assert h.ctx.wizards.get(sid) is not None


async def test_restart_forgets_wizard_and_writes_nothing(h: Harness, api, fake_bale, tmp_path) -> None:  # type: ignore[no-untyped-def]
    h.register_group()
    await h.text(GROUP, USER, "متن")
    sid = h.sid()
    await h.press(USER, "y", sid)
    await h.press(USER, "t", sid, "1")
    await h.press(USER, "c", sid)
    restarted = Harness(h.settings, api, fake_bale, h.root)
    try:
        await restarted.press(USER, "f", sid)
        assert_no_post(restarted)
    finally:
        await restarted.close()


async def test_unregistered_group_is_completely_silent(h: Harness) -> None:
    await h.text(UNKNOWN_GROUP, USER, "متن در گروه ثبت‌نشده")
    await h.send(UNKNOWN_GROUP, USER, photo=[{"file_id": "p9", "file_size": 10}])
    assert_no_post(h)
    assert h.count("Person") == 0
    assert h.count("PersonGroup") == 0
    assert h.outbound_calls() == []
    assert len(h.ctx.wizards) == 0


async def test_inactive_group_is_completely_silent(h: Harness) -> None:
    h.register_group(active=0)
    await h.text(GROUP, USER, "متن")
    assert_no_post(h)
    assert h.count("Person") == 0
    assert h.outbound_calls() == []


async def test_archive_group_is_never_recorded(h: Harness) -> None:
    await h.text(ARCHIVE, USER, "پیام در گروه آرشیو")
    assert_no_post(h)
    assert h.count("Person") == 0
    assert h.outbound_calls() == []


async def test_archive_group_is_ignored_even_if_someone_registered_it(h: Harness) -> None:
    h.register_group(bale_group_id=ARCHIVE_ID, name="آرشیو")
    await h.text(ARCHIVE, USER, "پیام در گروه آرشیو")
    assert_no_post(h)
    assert h.count("Person") == 0
    assert h.outbound_calls() == []


async def test_inactive_person_gets_no_wizard(h: Harness) -> None:
    h.register_group()
    h.root.execute(
        "INSERT INTO Person (firstname, bale_user_id, is_active) VALUES (%s, %s, 0)",
        ("علی", USER["id"]),
    )
    await h.text(GROUP, USER, "متن")
    assert len(h.ctx.wizards) == 0
    assert_no_post(h)
