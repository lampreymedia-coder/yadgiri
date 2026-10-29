"""Report and export queries — SELECT only, and only on the bot's own posts (Source='bale')."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.repo import person_label
from app.db.schema import SOURCE_BALE
from app.timeutil import tehran_now


@dataclass(slots=True)
class PostFilter:
    """Optional limits on Posts (alias ``p``). Dates are Tehran time.

    Every filter also keeps only Source = 'bale': staff posts never show up here.
    """

    start: datetime | None = None
    end: datetime | None = None
    hashtag_id: int | None = None
    ehya_group_id: int | None = None
    person_id: int | None = None

    def sql(self) -> tuple[str, dict[str, Any]]:
        parts: list[str] = ["p.Source = :f_source"]
        params: dict[str, Any] = {"f_source": SOURCE_BALE}
        if self.start is not None:
            parts.append("p.CreatedAt >= :f_start")
            params["f_start"] = self.start
        if self.end is not None:
            parts.append("p.CreatedAt < :f_end")
            params["f_end"] = self.end
        if self.hashtag_id is not None:
            parts.append(
                "EXISTS (SELECT 1 FROM PostHashtags fh WHERE fh.PostId = p.Id "
                "AND fh.HashtagId = :f_tag)"
            )
            params["f_tag"] = self.hashtag_id
        if self.ehya_group_id is not None:
            parts.append("p.BaleGroupId = :f_group")
            params["f_group"] = self.ehya_group_id
        if self.person_id is not None:
            parts.append("p.AuthorUserId = :f_person")
            params["f_person"] = self.person_id
        return " AND ".join(parts), params


def today_range(now: datetime | None = None) -> tuple[datetime, datetime]:
    start = (now or tehran_now()).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


@dataclass(slots=True)
class Report:
    total_posts: int = 0
    today_posts: int = 0
    top_users: list[tuple[str, int]] = field(default_factory=list)
    by_hashtag: list[tuple[str, int]] = field(default_factory=list)
    by_content_type: list[tuple[int, int]] = field(default_factory=list)
    by_group: list[tuple[str, int]] = field(default_factory=list)

    @property
    def top_hashtag(self) -> tuple[str, int] | None:
        used = [item for item in self.by_hashtag if item[1] > 0]
        return used[0] if used else None


_PERSON_COLUMNS = (
    "u.Id AS id, u.FirstName AS firstname, u.LastName AS lastname, "
    "u.BaleUsername AS bale_username, u.BaleChatId AS bale_user_id"
)


async def build_report(
    conn: AsyncConnection, top_n: int = 5, flt: PostFilter | None = None
) -> Report:
    flt = flt or PostFilter()
    where, params = flt.sql()
    report = Report()
    report.total_posts = int(
        (await conn.execute(text(f"SELECT COUNT(*) FROM Posts p WHERE {where}"), params)).scalar_one()
    )
    start, end = today_range()
    report.today_posts = int(
        (
            await conn.execute(
                text(
                    f"SELECT COUNT(*) FROM Posts p WHERE {where} "
                    "AND p.CreatedAt >= :t_start AND p.CreatedAt < :t_end"
                ),
                {**params, "t_start": start, "t_end": end},
            )
        ).scalar_one()
    )
    users = await conn.execute(
        text(
            f"SELECT {_PERSON_COLUMNS}, COUNT(*) AS n FROM Posts p "
            f"JOIN Users u ON u.Id = p.AuthorUserId WHERE {where} "
            "GROUP BY u.Id, u.FirstName, u.LastName, u.BaleUsername, u.BaleChatId "
            "ORDER BY n DESC, u.Id LIMIT :top"
        ),
        {**params, "top": top_n},
    )
    report.top_users = [(person_label(row), int(row.n)) for row in users]
    tags = await conn.execute(
        text(
            "SELECT h.Name AS name, COUNT(p.Id) AS n FROM Hashtags h "
            "LEFT JOIN PostHashtags ph ON ph.HashtagId = h.Id "
            f"LEFT JOIN Posts p ON p.Id = ph.PostId AND {where} "
            "GROUP BY h.Id, h.Name ORDER BY n DESC, h.Id"
        ),
        params,
    )
    report.by_hashtag = [(str(row.name), int(row.n)) for row in tags]
    types = await conn.execute(
        text(
            f"SELECT p.ContentType AS content_type, COUNT(*) AS n FROM Posts p WHERE {where} "
            "GROUP BY p.ContentType ORDER BY p.ContentType"
        ),
        params,
    )
    report.by_content_type = [(int(row.content_type), int(row.n)) for row in types]
    groups = await conn.execute(
        text(
            "SELECT g.Title AS title, COUNT(p.Id) AS n FROM BaleGroups g "
            f"LEFT JOIN Posts p ON p.BaleGroupId = g.Id AND {where} "
            "GROUP BY g.Id, g.Title ORDER BY n DESC, g.Id"
        ),
        params,
    )
    report.by_group = [(str(row.title), int(row.n)) for row in groups]
    return report


async def top_people(
    conn: AsyncConnection, limit: int = 15, flt: PostFilter | None = None
) -> list[tuple[int, str, int]]:
    """(Users.Id, label, number of bale posts), most active first."""
    where, params = (flt or PostFilter()).sql()
    result = await conn.execute(
        text(
            f"SELECT {_PERSON_COLUMNS}, COUNT(p.Id) AS n FROM Users u "
            f"JOIN Posts p ON p.AuthorUserId = u.Id WHERE {where} "
            "GROUP BY u.Id, u.FirstName, u.LastName, u.BaleUsername, u.BaleChatId "
            "ORDER BY n DESC, u.Id LIMIT :lim"
        ),
        {**params, "lim": limit},
    )
    return [(int(row.id), person_label(row), int(row.n)) for row in result]


@dataclass(slots=True)
class ExportRow:
    post_id: int
    created_at: datetime
    posted_at: datetime
    sender: str
    bale_user_id: int | None
    group_name: str
    content_type: int
    hashtags: str
    content_text: str
    files: int
    user_note: str = ""


async def export_rows(conn: AsyncConnection, flt: PostFilter) -> list[ExportRow]:
    where, params = flt.sql()
    result = await conn.execute(
        text(
            "SELECT p.Id AS post_id, p.CreatedAt AS created_at, p.PostedAt AS posted_at, "
            "p.ContentType AS content_type, p.Body AS body, p.UserNote AS user_note, "
            f"{_PERSON_COLUMNS}, g.Title AS group_name, "
            "(SELECT GROUP_CONCAT(h.Name ORDER BY h.Id SEPARATOR '، ') FROM PostHashtags ph "
            " JOIN Hashtags h ON h.Id = ph.HashtagId WHERE ph.PostId = p.Id) AS tags, "
            "(SELECT COUNT(*) FROM PostMedia m WHERE m.PostId = p.Id) AS files "
            "FROM Posts p JOIN Users u ON u.Id = p.AuthorUserId "
            f"JOIN BaleGroups g ON g.Id = p.BaleGroupId WHERE {where} ORDER BY p.Id"
        ),
        params,
    )
    return [
        ExportRow(
            post_id=int(row.post_id),
            created_at=row.created_at,
            posted_at=row.posted_at,
            sender=person_label(row),
            bale_user_id=row.bale_user_id,
            group_name=str(row.group_name),
            content_type=int(row.content_type),
            hashtags=str(row.tags or ""),
            content_text=str(row.body or ""),
            files=int(row.files),
            user_note=str(row.user_note or ""),
        )
        for row in result
    ]
