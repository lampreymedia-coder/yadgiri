"""Confirmed wizards write exactly one Post with its hashtags and files."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from app.db import repo
from app.handlers.wizard import resume_pending
from app.i18n import fa
from tests.bot.harness import ADMIN_ID, ARCHIVE_ID, GROUP, GROUP_ID, MB, USER, Harness


async def test_text_full_flow(h: Harness) -> None:
    group_row = h.register_group()
    origin = await h.text(GROUP, USER, "سلام، این یک متن مهم است https://example.com")
    sid = h.sid()
    wizard_id = h.ctx.wizards.get(sid).wizard_message_id  # type: ignore[union-attr]
    await h.confirm([1, 4])

    posts = h.root.rows(
        "SELECT id, person_id, ehya_group_id, bale_message_id, content_type, content_text, posted_at FROM Post"
    )
    assert len(posts) == 1
    post_id, person_id, ehya_group_id, message_id, ctype, body, posted_at = posts[0]
    assert (ehya_group_id, message_id, ctype) == (group_row, origin, 1)
    assert body.startswith("سلام")
    assert posted_at == datetime(2025, 9, 26, 13, 30)  # Tehran time, not UTC
    assert sorted(r[0] for r in h.root.rows("SELECT hashtag_id FROM PostHashtag WHERE post_id=%s", (post_id,))) == [1, 4]
    assert h.count("PostMedia") == 0
    person = h.root.rows("SELECT id, bale_user_id, bale_username, firstname, is_active FROM Person")
    assert person == [(person_id, USER["id"], "ali", "علی", 1)]

    # «✅ ثبت شد» + hashtags as a reply under the original message in the group.
    replies = [p for p in h.fake.calls_for("sendMessage") if int(p["chat_id"]) == GROUP_ID]
    assert replies[-1]["text"] == "✅ ثبت شد\n#یادگیری #سند"
    assert int(replies[-1]["reply_to_message_id"]) == origin
    # Wizard messages removed, original untouched.
    deleted = h.deleted()
    assert (USER["id"], wizard_id) in deleted
    assert (GROUP_ID, origin) not in deleted
    assert h.ctx.wizards.get(sid) is None


async def test_person_found_by_user_id_not_username(h: Harness) -> None:
    h.register_group()
    await h.text(GROUP, USER, "اول")
    renamed = {**USER, "username": "ali_new", "first_name": "علی‌رضا"}
    await h.text(GROUP, renamed, "دوم")
    rows = h.root.rows("SELECT bale_user_id, bale_username, firstname FROM Person")
    assert rows == [(USER["id"], "ali_new", "علی‌رضا")]
    assert h.count("PersonGroup") == 1


async def test_photo_without_caption_is_stored_on_disk(h: Harness) -> None:
    h.register_group()
    await h.send(GROUP, USER, photo=[{"file_id": "ph1", "width": 800, "height": 600, "file_size": 5000}])
    await h.confirm([3])
    await h.settle()
    (ctype, body), = h.root.rows("SELECT content_type, content_text FROM Post")
    assert (ctype, body) == (2, "")
    (mtype, path, fid, width), = h.root.rows("SELECT media_type, storage_path, bale_file_id, width FROM PostMedia")
    assert (mtype, fid, width) == (1, "ph1", 800)
    media_root = h.settings.media_root
    assert path.startswith(str(media_root)) and path.endswith(".jpg")
    assert Path(path).read_bytes() == b"fake-file-bytes"  # noqa: ASYNC240
    # Backup copy in the archive group.
    assert any(int(p["chat_id"]) == ARCHIVE_ID for p in h.fake.calls_for("copyMessage"))


@pytest.mark.parametrize(
    ("content", "post_type", "media_type"),
    [
        ({"voice": {"file_id": "v1", "duration": 5, "file_size": 100}}, 4, 3),
        ({"audio": {"file_id": "a1", "title": "t", "file_name": "x.mp3", "file_size": 100}}, 4, 3),
        ({"video": {"file_id": "vd1", "duration": 9, "file_size": 100}}, 3, 2),
        ({"animation": {"file_id": "an1", "file_size": 100}}, 3, 2),
        ({"document": {"file_id": "d1", "file_name": "r.pdf", "mime_type": "application/pdf", "file_size": 100}}, 5, 4),
    ],
)
async def test_content_and_media_type_codes(h: Harness, content: dict, post_type: int, media_type: int) -> None:  # type: ignore[type-arg]
    h.register_group()
    await h.send(GROUP, USER, **content)
    await h.confirm([2])
    assert h.root.rows("SELECT content_type, content_text FROM Post") == [(post_type, "")]
    assert [r[0] for r in h.root.rows("SELECT media_type FROM PostMedia")] == [media_type]


async def test_big_file_points_to_archive_copy(h: Harness) -> None:
    h.register_group()
    await h.send(GROUP, USER, video={"file_id": "big", "file_size": 50 * MB}, caption="ویدیو بزرگ")
    await h.confirm([1])
    (path,), = h.root.rows("SELECT storage_path FROM PostMedia")
    archive_copies = [p for p in h.fake.calls_for("copyMessage") if int(p["chat_id"]) == ARCHIVE_ID]
    assert len(archive_copies) == 1
    assert path.startswith(f"bale:{ARCHIVE_ID}/")
    assert not h.fake.calls_for("downloadFile")
    assert h.root.rows("SELECT content_text FROM Post") == [("ویدیو بزرگ",)]


async def test_failed_download_keeps_post_and_points_to_bale(h: Harness) -> None:
    h.register_group()
    h.fake.fail_with("getFile", 400, "nope", times=5)
    await h.send(GROUP, USER, document={"file_id": "d2", "file_name": "a.docx", "file_size": 100})
    await h.confirm([1])
    await h.settle()
    assert h.count("Post") == 1
    (path,), = h.root.rows("SELECT storage_path FROM PostMedia")
    assert path.startswith(f"bale:{ARCHIVE_ID}/")


async def test_album_is_one_post_with_all_files(h: Harness) -> None:
    from app.bale.models import Update

    h.register_group()
    # Two photos inside the album window → one wizard, one Post.
    for message_id, file_id in ((7001, "b1"), (7002, "b2")):
        await h.dispatcher.dispatch(
            Update.model_validate(
                {
                    "update_id": message_id,
                    "message": {
                        "message_id": message_id,
                        "date": 1,
                        "chat": GROUP,
                        "from": USER,
                        "photo": [{"file_id": file_id, "file_size": 10}],
                    },
                }
            )
        )
    await h.settle()
    assert len(h.ctx.wizards) == 1
    await h.confirm([1])
    assert h.root.rows("SELECT bale_message_id, content_type FROM Post") == [(7001, 2)]
    assert sorted(r[0] for r in h.root.rows("SELECT bale_file_id FROM PostMedia")) == ["b1", "b2"]


async def test_duplicate_is_skipped_silently(h: Harness) -> None:
    h.register_group()
    origin = await h.text(GROUP, USER, "متن تکراری")
    await h.confirm([1])
    assert h.count("Post") == 1
    # Same group message again (e.g. Bale resends it after a restart).
    await h.send(GROUP, USER, message_id=origin, text="متن تکراری")
    await h.confirm([2])
    assert h.count("Post") == 1
    assert h.count("PostHashtag") == 1
    assert len(h.ctx.wizards) == 0


async def test_check_constraint_rejection(db, api, fake_bale, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Database still has CHECK 1-4 / 1-3: a document (5/4) is refused, nothing kept."""
    from tests.bot.harness import make_settings
    from tests.conftest import OLD_CHECK_DB

    h = Harness(make_settings(tmp_path, OLD_CHECK_DB), api, fake_bale, db)
    try:
        db.execute(f"USE `{OLD_CHECK_DB}`")
        db.execute(
            "INSERT INTO EhyaGroup (bale_group_id, bale_group_name, level) VALUES (%s, %s, 1)",
            (GROUP_ID, "گروه رصد"),
        )
        origin = await h.send(GROUP, USER, document={"file_id": "d9", "file_name": "a.zip", "file_size": 10})
        await h.confirm([1])
        assert h.count("Post") == 0
        assert h.count("PostHashtag") == 0
        assert h.count("PostMedia") == 0
        assert fa.TYPE_NOT_ALLOWED in h.texts_to(USER["id"])
        assert any("CHECK" in text for text in h.texts_to(ADMIN_ID))
        assert (GROUP_ID, origin) not in h.deleted()
        # the archive copy made before the insert is removed again
        copies = [p for p in fake_bale.calls_for("copyMessage") if int(p["chat_id"]) == ARCHIVE_ID]
        assert len(copies) == 1
        assert any(chat == ARCHIVE_ID for chat, _ in h.deleted())
    finally:
        await h.close()


async def test_post_hashtag_media_are_one_transaction(h: Harness) -> None:
    group_row = h.register_group()
    h.root.execute("INSERT INTO Person (firstname, bale_user_id, is_active) VALUES ('x', 1, 1)")
    (person_id,), = h.root.rows("SELECT id FROM Person")
    post = repo.NewPost(
        person_id=person_id,
        ehya_group_id=group_row,
        bale_message_id=42,
        content_type=1,
        content_text="t",
        posted_at=datetime(2026, 1, 1),
        hashtag_ids=[1, 99],  # 99 does not exist → PostHashtag insert fails
    )
    with pytest.raises(Exception):  # noqa: B017
        async with h.db.tx() as conn:
            await repo.insert_post(conn, post)
    assert h.count("Post") == 0
    assert h.count("PostHashtag") == 0


async def test_private_chat_closed_shows_group_hint_then_resumes(h: Harness) -> None:
    h.register_group()
    h.fake.forbidden_private_chats.add(USER["id"])
    origin = await h.text(GROUP, USER, "متن")
    hints = [p for p in h.fake.calls_for("sendMessage") if int(p["chat_id"]) == GROUP_ID]
    assert len(hints) == 1 and int(hints[0]["reply_to_message_id"]) == origin
    assert h.count("Post") == 0
    h.fake.forbidden_private_chats.clear()
    await h.private(USER, "/start")
    session = h.ctx.wizards.for_user(USER["id"])[0]
    assert session.wizard_message_id is not None
    assert session.hint_message_id is None
    await h.confirm([1])
    assert h.count("Post") == 1
    assert await resume_pending(h.ctx, USER["id"]) == 0


async def test_hashtag_keyboard_follows_the_table(h: Harness) -> None:
    h.register_group()
    h.root.execute("INSERT INTO Hashtag (name, is_active) VALUES ('تازه', 1)")
    h.root.execute("UPDATE Hashtag SET is_active = 0 WHERE name = 'محتوایی'")
    await h.text(GROUP, USER, "متن")
    await h.press(USER, "y", h.sid())
    labels = h.fake.markup_labels(h.fake.last_markup(USER["id"]))
    tag_labels = [label for label in labels if label.startswith(("⬜️", "☑️"))]
    assert len(tag_labels) == 4
    assert any("تازه" in label for label in tag_labels)
    assert not any("محتوایی" in label for label in tag_labels)


async def test_only_sender_can_answer(h: Harness) -> None:
    from tests.bot.harness import OTHER_USER

    h.register_group()
    await h.text(GROUP, USER, "متن")
    sid = h.sid()
    await h.press(OTHER_USER, "y", sid)
    await h.press(OTHER_USER, "n", sid)
    assert h.ctx.wizards.get(sid) is not None
    assert h.ctx.wizards.get(sid).step == "decision"  # type: ignore[union-attr]
