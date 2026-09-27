"""Reads and writes on the seven bot tables of ``Bale_Archive``.

Only row-level SQL lives here (SELECT / INSERT / UPDATE). Table and column
names follow the staff schema exactly (appendix A of CLAUDE-BOT-FIX.md);
nothing in this module creates or changes a table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.timeutil import tehran_now

# MySQL error numbers.
ER_DUP_ENTRY = 1062
ER_CHECK_CONSTRAINT_VIOLATED = 3819


def mysql_errno(exc: BaseException) -> int | None:
    """MySQL error number behind a SQLAlchemy error, if any."""
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", None)
    if args and isinstance(args[0], int):
        return args[0]
    return None


class DuplicatePost(Exception):
    """UQ_Post_group_message: this group message is already archived."""


class ContentTypeRejected(Exception):
    """A CHECK constraint refused content_type / media_type."""


def _cut(value: str | None, length: int) -> str | None:
    if value is None:
        return None
    return value[:length]


# ─── EhyaGroup ───


@dataclass(frozen=True, slots=True)
class GroupRow:
    id: int
    bale_group_id: int
    name: str
    level: int
    is_active: bool


def _group(row: object) -> GroupRow:
    return GroupRow(
        id=int(row.id),  # type: ignore[attr-defined]
        bale_group_id=int(row.bale_group_id),  # type: ignore[attr-defined]
        name=str(row.bale_group_name),  # type: ignore[attr-defined]
        level=int(row.level),  # type: ignore[attr-defined]
        is_active=bool(row.is_active),  # type: ignore[attr-defined]
    )


async def get_group(conn: AsyncConnection, bale_group_id: int) -> GroupRow | None:
    result = await conn.execute(
        text(
            "SELECT id, bale_group_id, bale_group_name, level, is_active "
            "FROM EhyaGroup WHERE bale_group_id = :gid"
        ),
        {"gid": bale_group_id},
    )
    row = result.first()
    return _group(row) if row is not None else None


async def get_active_group(conn: AsyncConnection, bale_group_id: int) -> GroupRow | None:
    group = await get_group(conn, bale_group_id)
    if group is None or not group.is_active:
        return None
    return group


async def list_groups(conn: AsyncConnection) -> list[GroupRow]:
    result = await conn.execute(
        text(
            "SELECT id, bale_group_id, bale_group_name, level, is_active "
            "FROM EhyaGroup ORDER BY is_active DESC, id"
        )
    )
    return [_group(row) for row in result]


async def register_group(
    conn: AsyncConnection, bale_group_id: int, name: str, level: int
) -> GroupRow:
    """Add one EhyaGroup row, or re-activate and update the existing one."""
    existing = await get_group(conn, bale_group_id)
    now = tehran_now()
    if existing is None:
        await conn.execute(
            text(
                "INSERT INTO EhyaGroup "
                "(bale_group_id, bale_group_name, level, is_active, created_at) "
                "VALUES (:gid, :name, :level, 1, :now)"
            ),
            {"gid": bale_group_id, "name": _cut(name, 200), "level": level, "now": now},
        )
    else:
        await conn.execute(
            text(
                "UPDATE EhyaGroup SET bale_group_name = :name, level = :level, "
                "is_active = 1, updated_at = :now WHERE id = :id"
            ),
            {"name": _cut(name, 200), "level": level, "now": now, "id": existing.id},
        )
    group = await get_group(conn, bale_group_id)
    assert group is not None
    return group


async def unregister_group(conn: AsyncConnection, bale_group_id: int) -> bool:
    """Set is_active = 0. The row is never deleted."""
    result = await conn.execute(
        text(
            "UPDATE EhyaGroup SET is_active = 0, updated_at = :now "
            "WHERE bale_group_id = :gid AND is_active = 1"
        ),
        {"gid": bale_group_id, "now": tehran_now()},
    )
    return bool(result.rowcount)


# ─── Person / PersonGroup ───


@dataclass(frozen=True, slots=True)
class PersonRow:
    id: int
    bale_user_id: int
    is_active: bool


async def get_person(conn: AsyncConnection, bale_user_id: int) -> PersonRow | None:
    result = await conn.execute(
        text(
            "SELECT id, bale_user_id, bale_username, firstname, lastname, is_active "
            "FROM Person WHERE bale_user_id = :uid ORDER BY id LIMIT 1"
        ),
        {"uid": bale_user_id},
    )
    row = result.first()
    if row is None:
        return None
    # NULL is_active (rows typed in by staff) counts as active; only 0 blocks.
    return PersonRow(
        int(row.id), int(row.bale_user_id), row.is_active is None or bool(row.is_active)
    )


async def ensure_person(
    conn: AsyncConnection,
    bale_user_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
) -> PersonRow:
    """Find by bale_user_id only; add or refresh display fields.

    ``id`` comes from AUTO_INCREMENT — the bot never computes it.
    """
    first = _cut(first_name or None, 50)
    last = _cut(last_name or None, 50)
    uname = _cut(username or None, 100)
    result = await conn.execute(
        text(
            "SELECT id, bale_username, firstname, lastname, is_active "
            "FROM Person WHERE bale_user_id = :uid ORDER BY id LIMIT 1"
        ),
        {"uid": bale_user_id},
    )
    row = result.first()
    if row is None:
        await conn.execute(
            text(
                "INSERT INTO Person "
                "(firstname, lastname, bale_user_id, bale_username, created_at, is_active) "
                "VALUES (:first, :last, :uid, :uname, :now, 1)"
            ),
            {
                "first": first,
                "last": last,
                "uid": bale_user_id,
                "uname": uname,
                "now": tehran_now(),
            },
        )
        person = await get_person(conn, bale_user_id)
        assert person is not None
        return person
    if (row.bale_username, row.firstname, row.lastname) != (uname, first, last):
        await conn.execute(
            text(
                "UPDATE Person SET bale_username = :uname, firstname = :first, "
                "lastname = :last WHERE id = :id"
            ),
            {"uname": uname, "first": first, "last": last, "id": row.id},
        )
    return PersonRow(int(row.id), bale_user_id, row.is_active is None or bool(row.is_active))


async def ensure_membership(conn: AsyncConnection, person_id: int, ehya_group_id: int) -> None:
    """One PersonGroup row per (person, group); an existing row is left as is.

    Callers hold the per-user lock, so check-then-insert cannot race here.
    """
    existing = await conn.execute(
        text("SELECT 1 FROM PersonGroup WHERE person_id = :pid AND ehya_group_id = :gid"),
        {"pid": person_id, "gid": ehya_group_id},
    )
    if existing.first() is not None:
        return
    await conn.execute(
        text(
            "INSERT INTO PersonGroup (person_id, ehya_group_id, created_at, is_active) "
            "VALUES (:pid, :gid, :now, 1)"
        ),
        {"pid": person_id, "gid": ehya_group_id, "now": tehran_now()},
    )


# ─── Hashtag ───


@dataclass(frozen=True, slots=True)
class HashtagRow:
    id: int
    name: str


async def active_hashtags(conn: AsyncConnection) -> list[HashtagRow]:
    """Every active hashtag, read fresh each time. Nothing is hard-coded."""
    result = await conn.execute(
        text("SELECT id, name FROM Hashtag WHERE is_active = 1 ORDER BY id")
    )
    return [HashtagRow(int(row.id), str(row.name)) for row in result]


# ─── Post / PostHashtag / PostMedia ───


@dataclass(slots=True)
class NewMedia:
    media_type: int
    storage_path: str
    bale_file_id: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    mime_type: str | None = None
    duration: int | None = None
    width: int | None = None
    height: int | None = None


@dataclass(slots=True)
class NewPost:
    person_id: int
    ehya_group_id: int
    bale_message_id: int
    content_type: int
    content_text: str
    posted_at: datetime
    hashtag_ids: list[int]
    media: list[NewMedia] = field(default_factory=list)


async def insert_post(conn: AsyncConnection, post: NewPost) -> tuple[int, list[int]]:
    """Write Post + PostHashtag + PostMedia on ``conn`` (the caller's transaction).

    Returns (post_id, media_ids). Raises :class:`DuplicatePost` or
    :class:`ContentTypeRejected`; the caller's transaction then rolls back
    so nothing at all is kept.
    """
    if not post.hashtag_ids:
        msg = "a post needs at least one hashtag"
        raise ValueError(msg)
    try:
        result = await conn.execute(
            text(
                "INSERT INTO Post (person_id, ehya_group_id, bale_message_id, content_type, "
                "content_text, posted_at, created_at) "
                "VALUES (:pid, :gid, :mid, :ctype, :body, :posted, :now)"
            ),
            {
                "pid": post.person_id,
                "gid": post.ehya_group_id,
                "mid": post.bale_message_id,
                "ctype": post.content_type,
                "body": post.content_text or "",
                "posted": post.posted_at,
                "now": tehran_now(),
            },
        )
        post_id = int(result.lastrowid)
        for hashtag_id in sorted(set(post.hashtag_ids)):
            await conn.execute(
                text("INSERT INTO PostHashtag (post_id, hashtag_id) VALUES (:pid, :hid)"),
                {"pid": post_id, "hid": hashtag_id},
            )
        media_ids: list[int] = []
        for item in post.media:
            media_result = await conn.execute(
                text(
                    "INSERT INTO PostMedia (post_id, media_type, bale_file_id, file_name, "
                    "file_size, mime_type, storage_path, duration, width, height, created_at) "
                    "VALUES (:pid, :mtype, :fid, :fname, :fsize, :mime, :path, :dur, :w, :h, :now)"
                ),
                {
                    "pid": post_id,
                    "mtype": item.media_type,
                    "fid": _cut(item.bale_file_id, 500),
                    "fname": _cut(item.file_name, 255),
                    "fsize": item.file_size,
                    "mime": _cut(item.mime_type, 100),
                    "path": _cut(item.storage_path, 1000),
                    "dur": item.duration,
                    "w": item.width,
                    "h": item.height,
                    "now": tehran_now(),
                },
            )
            media_ids.append(int(media_result.lastrowid))
    except DBAPIError as exc:
        code = mysql_errno(exc)
        if code == ER_DUP_ENTRY:
            raise DuplicatePost from exc
        if code == ER_CHECK_CONSTRAINT_VIOLATED:
            raise ContentTypeRejected(str(exc.orig)) from exc
        raise
    return post_id, media_ids


async def post_exists(conn: AsyncConnection, ehya_group_id: int, bale_message_id: int) -> bool:
    result = await conn.execute(
        text("SELECT 1 FROM Post WHERE ehya_group_id = :gid AND bale_message_id = :mid"),
        {"gid": ehya_group_id, "mid": bale_message_id},
    )
    return result.first() is not None


async def set_storage_path(conn: AsyncConnection, media_id: int, storage_path: str) -> None:
    await conn.execute(
        text("UPDATE PostMedia SET storage_path = :path WHERE id = :id"),
        {"path": _cut(storage_path, 1000), "id": media_id},
    )


# ─── Admin panel: hashtag and group upkeep (single-row INSERT/UPDATE only) ───


async def all_hashtags(conn: AsyncConnection) -> list[tuple[int, str, bool]]:
    result = await conn.execute(text("SELECT id, name, is_active FROM Hashtag ORDER BY id"))
    return [(int(row.id), str(row.name), bool(row.is_active)) for row in result]


async def add_hashtag(conn: AsyncConnection, name: str) -> bool:
    """False when the name already exists (UQ_Hashtag_name)."""
    try:
        await conn.execute(
            text("INSERT INTO Hashtag (name, is_active) VALUES (:name, 1)"),
            {"name": _cut(name, 100)},
        )
    except DBAPIError as exc:
        if mysql_errno(exc) == ER_DUP_ENTRY:
            return False
        raise
    return True


async def rename_hashtag(conn: AsyncConnection, hashtag_id: int, name: str) -> bool:
    try:
        result = await conn.execute(
            text("UPDATE Hashtag SET name = :name WHERE id = :id"),
            {"name": _cut(name, 100), "id": hashtag_id},
        )
    except DBAPIError as exc:
        if mysql_errno(exc) == ER_DUP_ENTRY:
            return False
        raise
    return bool(result.rowcount)


async def set_hashtag_active(conn: AsyncConnection, hashtag_id: int, active: bool) -> None:
    """Hashtags are never deleted, only switched off."""
    await conn.execute(
        text("UPDATE Hashtag SET is_active = :active WHERE id = :id"),
        {"active": 1 if active else 0, "id": hashtag_id},
    )


async def get_group_by_id(conn: AsyncConnection, group_id: int) -> GroupRow | None:
    result = await conn.execute(
        text(
            "SELECT id, bale_group_id, bale_group_name, level, is_active "
            "FROM EhyaGroup WHERE id = :id"
        ),
        {"id": group_id},
    )
    row = result.first()
    return _group(row) if row is not None else None


async def set_group_level(conn: AsyncConnection, group_id: int, level: int) -> None:
    await conn.execute(
        text("UPDATE EhyaGroup SET level = :level, updated_at = :now WHERE id = :id"),
        {"level": level, "now": tehran_now(), "id": group_id},
    )


async def set_group_active(conn: AsyncConnection, group_id: int, active: bool) -> None:
    await conn.execute(
        text("UPDATE EhyaGroup SET is_active = :active, updated_at = :now WHERE id = :id"),
        {"active": 1 if active else 0, "now": tehran_now(), "id": group_id},
    )


# ─── A user's own posts (private menu) ───


@dataclass(frozen=True, slots=True)
class OwnPost:
    id: int
    created_at: datetime
    content_type: int
    content_text: str
    group_name: str
    hashtags: str


async def own_posts(conn: AsyncConnection, person_id: int, limit: int = 10) -> list[OwnPost]:
    result = await conn.execute(
        text(
            "SELECT p.id, p.created_at, p.content_type, p.content_text, g.bale_group_name, "
            "(SELECT GROUP_CONCAT(h.name ORDER BY h.id SEPARATOR ' ') FROM PostHashtag ph "
            " JOIN Hashtag h ON h.id = ph.hashtag_id WHERE ph.post_id = p.id) AS tags "
            "FROM Post p JOIN EhyaGroup g ON g.id = p.ehya_group_id "
            "WHERE p.person_id = :pid ORDER BY p.id DESC LIMIT :lim"
        ),
        {"pid": person_id, "lim": limit},
    )
    return [
        OwnPost(
            int(row.id),
            row.created_at,
            int(row.content_type),
            str(row.content_text or ""),
            str(row.bale_group_name),
            str(row.tags or ""),
        )
        for row in result
    ]


async def delete_own_post(conn: AsyncConnection, post_id: int, person_id: int) -> list[str] | None:
    """Undo one post of this person on the caller's transaction.

    Order: PostHashtag, PostMedia, then Post. Returns the storage paths of the
    removed files, or None when the post is not this person's.
    """
    owner = await conn.execute(
        text("SELECT 1 FROM Post WHERE id = :id AND person_id = :pid"),
        {"id": post_id, "pid": person_id},
    )
    if owner.first() is None:
        return None
    paths = [
        str(row.storage_path)
        for row in await conn.execute(
            text("SELECT storage_path FROM PostMedia WHERE post_id = :id"), {"id": post_id}
        )
    ]
    await conn.execute(text("DELETE FROM PostHashtag WHERE post_id = :id"), {"id": post_id})
    await conn.execute(text("DELETE FROM PostMedia WHERE post_id = :id"), {"id": post_id})
    await conn.execute(
        text("DELETE FROM Post WHERE id = :id AND person_id = :pid"),
        {"id": post_id, "pid": person_id},
    )
    return paths
