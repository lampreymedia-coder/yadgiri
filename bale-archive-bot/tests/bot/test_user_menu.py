"""2-5: user's private chat — start, my posts, my stats, undo within 10 minutes."""

from __future__ import annotations

from pathlib import Path

from app.i18n import fa
from tests.bot.harness import GROUP, OTHER_USER, USER, Harness


async def _save_photo(h: Harness) -> None:
    await h.send(GROUP, USER, photo=[{"file_id": "ph", "file_size": 50}], caption="عکس")
    await h.confirm([1, 2])
    await h.settle()


async def test_start_is_warm_and_shows_buttons(h: Harness) -> None:
    await h.private(USER, "/start")
    assert "خوش آمدید" in h.texts_to(USER["id"])[-1]
    labels = h.fake.markup_labels(h.fake.last_markup(USER["id"]))
    assert labels == [fa.BTN_MY_POSTS, fa.BTN_MY_STATS, fa.BTN_UNDO_LAST, fa.BTN_HELP]


async def test_my_posts_and_my_stats(h: Harness) -> None:
    h.register_group()
    await h.text(GROUP, USER, "متن اول")
    await h.confirm([1])
    await h.private(USER, fa.BTN_MY_POSTS)
    assert "متن اول" in h.texts_to(USER["id"])[-1] and "#یادگیری" in h.texts_to(USER["id"])[-1]
    await h.private(USER, fa.BTN_MY_STATS)
    assert "کل ثبت‌ها: ۱" in h.texts_to(USER["id"])[-1]
    await h.private(USER, fa.BTN_HELP)
    assert "لغو آخرین ارسال" in h.texts_to(USER["id"])[-1]


async def test_undo_removes_rows_and_file(h: Harness) -> None:
    h.register_group()
    await _save_photo(h)
    (post_id,), = h.root.rows("SELECT id FROM Post")
    (path,), = h.root.rows("SELECT storage_path FROM PostMedia")
    assert Path(path).exists()
    await h.private(USER, fa.BTN_UNDO_LAST)
    await h.press(USER, "un", "", str(post_id))
    assert h.count("Post") == 0 and h.count("PostHashtag") == 0 and h.count("PostMedia") == 0
    assert not Path(path).exists()
    assert h.count("Person") == 1  # the person row stays
    assert fa.UNDO_DONE in h.texts_to(USER["id"])


async def test_undo_after_10_minutes_is_refused(h: Harness) -> None:
    h.register_group()
    await h.text(GROUP, USER, "متن")
    await h.confirm([1])
    h.root.execute("UPDATE Post SET created_at = created_at - INTERVAL 11 MINUTE")
    (post_id,), = h.root.rows("SELECT id FROM Post")
    await h.private(USER, fa.BTN_UNDO_LAST)
    assert fa.UNDO_NOTHING in h.texts_to(USER["id"])
    await h.press(USER, "un", "", str(post_id))
    assert h.count("Post") == 1


async def test_undo_only_own_post(h: Harness) -> None:
    h.register_group()
    await h.text(GROUP, USER, "متن علی")
    await h.confirm([1])
    (post_id,), = h.root.rows("SELECT id FROM Post")
    await h.private(OTHER_USER, "/start")
    await h.press(OTHER_USER, "un", "", str(post_id))
    assert h.count("Post") == 1


async def test_keep_answer_changes_nothing(h: Harness) -> None:
    h.register_group()
    await h.text(GROUP, USER, "متن")
    await h.confirm([1])
    await h.private(USER, fa.BTN_UNDO_LAST)
    await h.press(USER, "un", "", "0")
    assert h.count("Post") == 1
