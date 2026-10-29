"""Row-level SQL on the merged schema — the only place table/column names appear.

Tables: Users, BaleGroups, BaleGroupMembers, Hashtags, Posts, PostHashtags,
PostMedia, OrgUnits (read only). Only SELECT / INSERT / UPDATE / DELETE;
nothing here creates or changes a table. Results are aliased to the bot's
snake_case attribute names so the rest of the code does not know the schema.

Sharing rules with the staff system (CLAUDE-MERGE-SCHEMA.md §2):
* Users rows are never changed, except filling a NULL BaleUsername.
* The bot only creates, lists and deletes Posts with Source = 'bale'.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.schema import SOURCE_BALE
from app.timeutil import tehran_now

# MySQL error numbers.
ER_DUP_ENTRY = 1062
ER_CHECK_CONSTRAINT_VIOLATED = 3819

# Values for a Users row the bot creates for a new Bale member.
NO_LOGIN_PASSWORD_HASH = "!bale-no-login"
DEFAULT_FIRST_NAME = "کاربر بله"


def mysql_errno(exc: BaseException) -> int | None:
    """MySQL error number behind a SQLAlchemy error, if any."""
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", None)
    if args and isinstance(args[0], int):
        return args[0]
    return None


class DuplicatePost(Exception):
    """UQ_Post_BaleMsg: this group message is already archived."""


class ContentTypeRejected(Exception):
    """A CHECK constraint refused ContentType / MediaType."""


def _cut(value: str | None, length: int) -> str | None:
    if value is None:
        return None
    return value[:length]


def _in_list(prefix: str, values: list[int], params: dict[str, object]) -> str:
    keys = []
    for index, value in enumerate(values):
        params[f"{prefix}{index}"] = value
        keys.append(f":{prefix}{index}")
    return ", ".join(keys)


# ─── OrgUnits (read only) ───


@dataclass(frozen=True, slots=True)
class OrgUnitRow:
    id: int
    level_no: int
    name: str


async def active_org_units(conn: AsyncConnection) -> list[OrgUnitRow]:
    result = await conn.execute(
        text(
            "SELECT Id AS id, LevelNo AS level_no, Name AS name FROM OrgUnits "
            "WHERE IsActive = 1 ORDER BY LevelNo, Name, Id"
        )
    )
    return [OrgUnitRow(int(r.id), int(r.level_no or 0), str(r.name)) for r in result]


async def get_active_org_unit(conn: AsyncConnection, org_unit_id: int) -> OrgUnitRow | None:
    result = await conn.execute(
        text(
            "SELECT Id AS id, LevelNo AS level_no, Name AS name FROM OrgUnits "
            "WHERE Id = :id AND IsActive = 1"
        ),
        {"id": org_unit_id},
    )
    row = result.first()
    return OrgUnitRow(int(row.id), int(row.level_no or 0), str(row.name)) if row else None


# ─── BaleGroups ───


@dataclass(frozen=True, slots=True)
class GroupRow:
    id: int
    bale_group_id: int
    name: str
    org_unit_id: int
    is_active: bool
    org_unit_name: str = ""


_GROUP_SELECT = (
    "SELECT g.Id AS id, g.BaleChatId AS bale_group_id, g.Title AS name, "
    "g.OrgUnitId AS org_unit_id, g.IsActive AS is_active, o.Name AS org_unit_name "
    "FROM BaleGroups g LEFT JOIN OrgUnits o ON o.Id = g.OrgUnitId"
)


def _group(row: object) -> GroupRow:
    return GroupRow(
        id=int(row.id),  # type: ignore[attr-defined]
        bale_group_id=int(row.bale_group_id),  # type: ignore[attr-defined]
        name=str(row.name),  # type: ignore[attr-defined]
        org_unit_id=int(row.org_unit_id),  # type: ignore[attr-defined]
        is_active=bool(row.is_active),  # type: ignore[attr-defined]
        org_unit_name=str(row.org_unit_name or ""),  # type: ignore[attr-defined]
    )


async def get_group(conn: AsyncConnection, bale_group_id: int) -> GroupRow | None:
    result = await conn.execute(
        text(f"{_GROUP_SELECT} WHERE g.BaleChatId = :gid"), {"gid": bale_group_id}
    )
    row = result.first()
    return _group(row) if row is not None else None


async def get_active_group(conn: AsyncConnection, bale_group_id: int) -> GroupRow | None:
    group = await get_group(conn, bale_group_id)
    if group is None or not group.is_active:
        return None
    return group


async def get_group_by_id(conn: AsyncConnection, group_id: int) -> GroupRow | None:
    result = await conn.execute(text(f"{_GROUP_SELECT} WHERE g.Id = :id"), {"id": group_id})
    row = result.first()
    return _group(row) if row is not None else None


async def list_groups(conn: AsyncConnection) -> list[GroupRow]:
    result = await conn.execute(text(f"{_GROUP_SELECT} ORDER BY g.IsActive DESC, g.Id"))
    return [_group(row) for row in result]


async def register_group(
    conn: AsyncConnection, bale_group_id: int, title: str, org_unit_id: int
) -> GroupRow:
    """New group: one BaleGroups row. Known group: only IsActive=1 and OrgUnitId change."""
    existing = await get_group(conn, bale_group_id)
    now = tehran_now()
    if existing is None:
        await conn.execute(
            text(
                "INSERT INTO BaleGroups (BaleChatId, Title, OrgUnitId, IsActive, CreatedAt) "
                "VALUES (:gid, :title, :unit, 1, :now)"
            ),
            {"gid": bale_group_id, "title": _cut(title, 200), "unit": org_unit_id, "now": now},
        )
    else:
        await conn.execute(
            text(
                "UPDATE BaleGroups SET IsActive = 1, OrgUnitId = :unit, UpdatedAt = :now "
                "WHERE Id = :id"
            ),
            {"unit": org_unit_id, "now": now, "id": existing.id},
        )
    group = await get_group(conn, bale_group_id)
    assert group is not None
    return group


async def unregister_group(conn: AsyncConnection, bale_group_id: int) -> bool:
    """IsActive = 0. The row is never deleted."""
    result = await conn.execute(
        text(
            "UPDATE BaleGroups SET IsActive = 0, UpdatedAt = :now "
            "WHERE BaleChatId = :gid AND IsActive = 1"
        ),
        {"gid": bale_group_id, "now": tehran_now()},
    )
    return bool(result.rowcount)


async def set_group_org_unit(conn: AsyncConnection, group_id: int, org_unit_id: int) -> None:
    await conn.execute(
        text("UPDATE BaleGroups SET OrgUnitId = :unit, UpdatedAt = :now WHERE Id = :id"),
        {"unit": org_unit_id, "now": tehran_now(), "id": group_id},
    )


async def set_group_active(conn: AsyncConnection, group_id: int, active: bool) -> None:
    await conn.execute(
        text("UPDATE BaleGroups SET IsActive = :active, UpdatedAt = :now WHERE Id = :id"),
        {"active": 1 if active else 0, "now": tehran_now(), "id": group_id},
    )


# ─── Users / BaleGroupMembers ───


@dataclass(frozen=True, slots=True)
class PersonRow:
    """A Users row as the bot sees it. ``is_active`` = IsActive=1 and IsDeleted=0."""

    id: int
    bale_user_id: int
    is_active: bool


_USER_SELECT = (
    "SELECT Id AS id, BaleChatId AS bale_user_id, BaleUsername AS bale_username, "
    "IsActive AS is_active, IsDeleted AS is_deleted FROM Users"
)


def _person(row: object) -> PersonRow:
    active = bool(row.is_active) and not bool(row.is_deleted)  # type: ignore[attr-defined]
    return PersonRow(int(row.id), int(row.bale_user_id), active)  # type: ignore[attr-defined]


async def get_person(conn: AsyncConnection, bale_user_id: int) -> PersonRow | None:
    result = await conn.execute(
        text(f"{_USER_SELECT} WHERE BaleChatId = :cid"), {"cid": bale_user_id}
    )
    row = result.first()
    return _person(row) if row is not None else None


async def ensure_person(
    conn: AsyncConnection,
    bale_user_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
) -> PersonRow:
    """Find a Users row by BaleChatId only; create it for a new Bale member.

    An existing row is never changed, except filling a NULL BaleUsername.
    Id comes from AUTO_INCREMENT; every NOT NULL column is filled explicitly.
    """
    uname = _cut(username or None, 100)
    result = await conn.execute(
        text(f"{_USER_SELECT} WHERE BaleChatId = :cid"), {"cid": bale_user_id}
    )
    row = result.first()
    if row is not None:
        if row.bale_username is None and uname:
            await conn.execute(
                text(
                    "UPDATE Users SET BaleUsername = :uname "
                    "WHERE Id = :id AND BaleUsername IS NULL"
                ),
                {"uname": uname, "id": row.id},
            )
        return _person(row)
    try:
        await conn.execute(
            text(
                "INSERT INTO Users (Username, PasswordHash, FirstName, LastName, BaleChatId, "
                "BaleUsername, IsAdmin, IsActor, MustChangePassword, BaleRequireCode, IsDeleted, "
                "IsActive, NotifyBale, NotifyMeetings, NotifyWeekly, NotifyDelays, FailedLogins, "
                "CreatedAt) VALUES (:login, :pwd, :first, :last, :cid, :uname, 0, 0, 0, 0, 0, "
                "1, 1, 0, 0, 0, 0, :now)"
            ),
            {
                "login": f"bale_{bale_user_id}",
                "pwd": NO_LOGIN_PASSWORD_HASH,
                "first": _cut((first_name or "").strip() or DEFAULT_FIRST_NAME, 50),
                "last": _cut((last_name or "").strip(), 50),
                "cid": bale_user_id,
                "uname": uname,
                "now": tehran_now(),
            },
        )
    except DBAPIError as exc:
        # Two messages at the same moment: the other one created the row.
        if mysql_errno(exc) != ER_DUP_ENTRY:
            raise
    person = await get_person(conn, bale_user_id)
    if person is None:
        msg = f"Users row for BaleChatId {bale_user_id} could not be created"
        raise RuntimeError(msg)
    return person


async def ensure_membership(conn: AsyncConnection, person_id: int, ehya_group_id: int) -> None:
    """One BaleGroupMembers row per (user, group); an existing row is left as is.

    Two messages at the same moment can race; the duplicate-key error is ignored.
    """
    existing = await conn.execute(
        text("SELECT 1 FROM BaleGroupMembers WHERE UserId = :uid AND BaleGroupId = :gid"),
        {"uid": person_id, "gid": ehya_group_id},
    )
    if existing.first() is not None:
        return
    try:
        await conn.execute(
            text(
                "INSERT INTO BaleGroupMembers (UserId, BaleGroupId, IsActive, CreatedAt) "
                "VALUES (:uid, :gid, 1, :now)"
            ),
            {"uid": person_id, "gid": ehya_group_id, "now": tehran_now()},
        )
    except DBAPIError as exc:
        if mysql_errno(exc) != ER_DUP_ENTRY:
            raise


async def pickable_people(conn: AsyncConnection, limit: int = 40) -> list[tuple[int, str]]:
    """(BaleChatId, label) of recent active users that have a Bale account."""
    result = await conn.execute(
        text(
            "SELECT Id AS id, FirstName AS firstname, LastName AS lastname, "
            "BaleUsername AS bale_username, BaleChatId AS bale_user_id FROM Users "
            "WHERE BaleChatId IS NOT NULL AND IsActive = 1 AND IsDeleted = 0 "
            "ORDER BY Id DESC LIMIT :lim"
        ),
        {"lim": limit},
    )
    return [(int(row.bale_user_id), person_label(row)) for row in result]


def person_label(row: object) -> str:
    first = (getattr(row, "firstname", None) or "").strip()
    last = (getattr(row, "lastname", None) or "").strip()
    name = f"{first} {last}".strip()
    username = getattr(row, "bale_username", None)
    if name and username:
        return f"{name} (@{username})"
    if name:
        return name
    if username:
        return f"@{username}"
    return str(getattr(row, "bale_user_id", "") or getattr(row, "id", ""))


# ─── Hashtags ───


@dataclass(frozen=True, slots=True)
class HashtagRow:
    id: int
    name: str


async def active_hashtags(conn: AsyncConnection) -> list[HashtagRow]:
    """Every active hashtag, read fresh each time, ordered by Id. Nothing is hard-coded."""
    result = await conn.execute(
        text("SELECT Id AS id, Name AS name FROM Hashtags WHERE IsActive = 1 ORDER BY Id")
    )
    return [HashtagRow(int(row.id), str(row.name)) for row in result]


async def all_hashtags(conn: AsyncConnection) -> list[tuple[int, str, bool]]:
    result = await conn.execute(
        text("SELECT Id AS id, Name AS name, IsActive AS is_active FROM Hashtags ORDER BY Id")
    )
    return [(int(row.id), str(row.name), bool(row.is_active)) for row in result]


async def add_hashtag(conn: AsyncConnection, name: str) -> bool:
    """False when the name already exists (unique Name)."""
    try:
        await conn.execute(
            text("INSERT INTO Hashtags (Name, IsActive) VALUES (:name, 1)"),
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
            text("UPDATE Hashtags SET Name = :name WHERE Id = :id"),
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
        text("UPDATE Hashtags SET IsActive = :active WHERE Id = :id"),
        {"active": 1 if active else 0, "id": hashtag_id},
    )


# ─── Posts / PostHashtags / PostMedia ───


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
    org_unit_id: int = 0
    user_note: str | None = None
    media: list[NewMedia] = field(default_factory=list)


async def insert_post(conn: AsyncConnection, post: NewPost) -> tuple[int, list[int]]:
    """Write Posts + PostHashtags + PostMedia on ``conn`` (the caller's transaction).

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
                "INSERT INTO Posts (AuthorUserId, BaleGroupId, BaleMessageId, ContentType, Body, "
                "PostedAt, CreatedAt, OrgUnitId, Source, Title, UserNote) "
                "VALUES (:uid, :gid, :mid, :ctype, :body, :posted, :now, :unit, :source, NULL, "
                ":note)"
            ),
            {
                "uid": post.person_id,
                "gid": post.ehya_group_id,
                "mid": post.bale_message_id,
                "ctype": post.content_type,
                "body": post.content_text or "",
                "posted": post.posted_at,
                "now": tehran_now(),
                "unit": post.org_unit_id,
                "source": SOURCE_BALE,
                "note": post.user_note or None,
            },
        )
        post_id = int(result.lastrowid)
        for hashtag_id in sorted(set(post.hashtag_ids)):
            await conn.execute(
                text("INSERT INTO PostHashtags (PostId, HashtagId) VALUES (:pid, :hid)"),
                {"pid": post_id, "hid": hashtag_id},
            )
        media_ids: list[int] = []
        for item in post.media:
            media_result = await conn.execute(
                text(
                    "INSERT INTO PostMedia (PostId, MediaType, BaleFileId, FileName, FileSize, "
                    "MimeType, StoragePath, Duration, Width, Height, CreatedAt) "
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
        text("SELECT 1 FROM Posts WHERE BaleGroupId = :gid AND BaleMessageId = :mid"),
        {"gid": ehya_group_id, "mid": bale_message_id},
    )
    return result.first() is not None


async def set_storage_path(conn: AsyncConnection, media_id: int, storage_path: str) -> None:
    await conn.execute(
        text("UPDATE PostMedia SET StoragePath = :path WHERE Id = :id"),
        {"path": _cut(storage_path, 1000), "id": media_id},
    )


# ─── A user's own posts (private menu) — Source='bale' only ───


@dataclass(frozen=True, slots=True)
class OwnPost:
    id: int
    created_at: datetime
    content_type: int
    content_text: str
    group_name: str
    hashtags: str
    user_note: str | None = None


async def own_posts(conn: AsyncConnection, person_id: int, limit: int = 10) -> list[OwnPost]:
    result = await conn.execute(
        text(
            "SELECT p.Id AS id, p.CreatedAt AS created_at, p.ContentType AS content_type, "
            "p.Body AS body, p.UserNote AS user_note, g.Title AS group_name, "
            "(SELECT GROUP_CONCAT(h.Name ORDER BY h.Id SEPARATOR ' ') FROM PostHashtags ph "
            " JOIN Hashtags h ON h.Id = ph.HashtagId WHERE ph.PostId = p.Id) AS tags "
            "FROM Posts p JOIN BaleGroups g ON g.Id = p.BaleGroupId "
            "WHERE p.AuthorUserId = :uid AND p.Source = :source ORDER BY p.Id DESC LIMIT :lim"
        ),
        {"uid": person_id, "source": SOURCE_BALE, "lim": limit},
    )
    return [
        OwnPost(
            int(row.id),
            row.created_at,
            int(row.content_type),
            str(row.body or ""),
            str(row.group_name),
            str(row.tags or ""),
            row.user_note,
        )
        for row in result
    ]


async def delete_own_post(conn: AsyncConnection, post_id: int, person_id: int) -> list[str] | None:
    """Undo one of this user's Source='bale' posts on the caller's transaction.

    Order: PostHashtags, PostMedia, then Posts. Returns the storage paths of
    the removed files, or None when the post is not this user's bale post.
    """
    owner = await conn.execute(
        text(
            "SELECT 1 FROM Posts WHERE Id = :id AND AuthorUserId = :uid AND Source = :source"
        ),
        {"id": post_id, "uid": person_id, "source": SOURCE_BALE},
    )
    if owner.first() is None:
        return None
    paths = [
        str(row.storage_path)
        for row in await conn.execute(
            text("SELECT StoragePath AS storage_path FROM PostMedia WHERE PostId = :id"),
            {"id": post_id},
        )
    ]
    await conn.execute(text("DELETE FROM PostHashtags WHERE PostId = :id"), {"id": post_id})
    await conn.execute(text("DELETE FROM PostMedia WHERE PostId = :id"), {"id": post_id})
    await conn.execute(
        text("DELETE FROM Posts WHERE Id = :id AND AuthorUserId = :uid AND Source = :source"),
        {"id": post_id, "uid": person_id, "source": SOURCE_BALE},
    )
    return paths


# ─── PostMedia after download / compression / manual upload ───


async def set_media_compressed(
    conn: AsyncConnection,
    media_id: int,
    storage_path: str,
    size: int,
    mime_type: str | None,
    width: int | None,
    height: int | None,
) -> None:
    """After compression/conversion: only existing PostMedia columns (NULL = keep)."""
    await conn.execute(
        text(
            "UPDATE PostMedia SET StoragePath = :path, FileSize = :size, "
            "MimeType = COALESCE(:mime, MimeType), Width = COALESCE(:w, Width), "
            "Height = COALESCE(:h, Height) WHERE Id = :id"
        ),
        {
            "path": _cut(storage_path, 1000),
            "size": size,
            "mime": _cut(mime_type, 100),
            "w": width,
            "h": height,
            "id": media_id,
        },
    )


async def set_media_uploaded(
    conn: AsyncConnection,
    media_id: int,
    storage_path: str,
    size: int,
    mime_type: str | None,
    width: int | None,
    height: int | None,
    duration: int | None,
) -> bool:
    """A file the admin uploaded by hand replaces its bale: reference (only that row)."""
    result = await conn.execute(
        text(
            "UPDATE PostMedia SET StoragePath = :path, FileSize = :size, MimeType = :mime, "
            "Width = COALESCE(:w, Width), Height = COALESCE(:h, Height), "
            "Duration = COALESCE(:d, Duration) "
            "WHERE Id = :id AND StoragePath LIKE 'bale:%'"
        ),
        {
            "path": _cut(storage_path, 1000),
            "size": size,
            "mime": _cut(mime_type, 100),
            "w": width,
            "h": height,
            "d": duration,
            "id": media_id,
        },
    )
    return bool(result.rowcount)


@dataclass(frozen=True, slots=True)
class MediaRow:
    id: int
    post_id: int
    media_type: int
    file_name: str | None
    file_size: int | None
    mime_type: str | None
    storage_path: str
    duration: int | None


def _media(row: object) -> MediaRow:
    return MediaRow(
        id=int(row.id),  # type: ignore[attr-defined]
        post_id=int(row.post_id),  # type: ignore[attr-defined]
        media_type=int(row.media_type),  # type: ignore[attr-defined]
        file_name=row.file_name,  # type: ignore[attr-defined]
        file_size=row.file_size,  # type: ignore[attr-defined]
        mime_type=row.mime_type,  # type: ignore[attr-defined]
        storage_path=str(row.storage_path),  # type: ignore[attr-defined]
        duration=row.duration,  # type: ignore[attr-defined]
    )


_MEDIA_COLUMNS = (
    "m.Id AS id, m.PostId AS post_id, m.MediaType AS media_type, m.FileName AS file_name, "
    "m.FileSize AS file_size, m.MimeType AS mime_type, m.StoragePath AS storage_path, "
    "m.Duration AS duration"
)


async def get_media(conn: AsyncConnection, media_id: int) -> MediaRow | None:
    result = await conn.execute(
        text(f"SELECT {_MEDIA_COLUMNS} FROM PostMedia m WHERE m.Id = :id"), {"id": media_id}
    )
    row = result.first()
    return _media(row) if row is not None else None


async def pending_upload_rows(
    conn: AsyncConnection, media_ids: list[int] | None = None, limit: int = 50
) -> list[MediaRow]:
    """Files only held in Bale (StoragePath 'bale:…'), newest first."""
    where = "m.StoragePath LIKE 'bale:%'"
    params: dict[str, object] = {"lim": limit}
    if media_ids is not None:
        if not media_ids:
            return []
        where += f" AND m.Id IN ({_in_list('m', media_ids, params)})"
    result = await conn.execute(
        text(
            f"SELECT {_MEDIA_COLUMNS} FROM PostMedia m WHERE {where} ORDER BY m.Id DESC LIMIT :lim"
        ),
        params,
    )
    return [_media(row) for row in result]


async def media_for_posts(conn: AsyncConnection, post_ids: list[int]) -> dict[int, list[MediaRow]]:
    if not post_ids:
        return {}
    params: dict[str, object] = {}
    keys = _in_list("p", post_ids, params)
    result = await conn.execute(
        text(f"SELECT {_MEDIA_COLUMNS} FROM PostMedia m WHERE m.PostId IN ({keys}) ORDER BY m.Id"),
        params,
    )
    grouped: dict[int, list[MediaRow]] = {}
    for row in result:
        media = _media(row)
        grouped.setdefault(media.post_id, []).append(media)
    return grouped


async def local_media_rows(conn: AsyncConnection) -> list[MediaRow]:
    """Every PostMedia row whose file should be on this server's disk."""
    result = await conn.execute(
        text(
            f"SELECT {_MEDIA_COLUMNS} FROM PostMedia m "
            "WHERE m.StoragePath NOT LIKE 'bale:%' ORDER BY m.Id"
        )
    )
    return [_media(row) for row in result]


# ─── Counts for the startup check ───


async def count_active_hashtags(conn: AsyncConnection) -> int:
    result = await conn.execute(text("SELECT COUNT(*) FROM Hashtags WHERE IsActive = 1"))
    return int(result.scalar_one())


async def count_active_org_units(conn: AsyncConnection) -> int:
    result = await conn.execute(text("SELECT COUNT(*) FROM OrgUnits WHERE IsActive = 1"))
    return int(result.scalar_one())
