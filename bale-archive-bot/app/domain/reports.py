"""Admin reports built only from SELECTs on Post, PostHashtag, Hashtag, Person, EhyaGroup."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.timeutil import tehran_now


@dataclass(slots=True)
class PostFilter:
    """Optional limits applied to Post (alias ``p``). Dates are Tehran time."""

    start: datetime | None = None
    end: datetime | None = None
    hashtag_id: int | None = None
    ehya_group_id: int | None = None
    person_id: int | None = None

    def sql(self) -> tuple[str, dict[str, Any]]:
        parts: list[str] = []
        params: dict[str, Any] = {}
        if self.start is not None:
            parts.append("p.created_at >= :f_start")
            params["f_start"] = self.start
        if self.end is not None:
            parts.append("p.created_at < :f_end")
            params["f_end"] = self.end
        if self.hashtag_id is not None:
            parts.append(
                "EXISTS (SELECT 1 FROM PostHashtag fh WHERE fh.post_id = p.id AND fh.hashtag_id = :f_tag)"
            )
            params["f_tag"] = self.hashtag_id
        if self.ehya_group_id is not None:
            parts.append("p.ehya_group_id = :f_group")
            params["f_group"] = self.ehya_group_id
        if self.person_id is not None:
            parts.append("p.person_id = :f_person")
            params["f_person"] = self.person_id
        return (" AND ".join(parts) or "1 = 1"), params


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


async def build_report(
    conn: AsyncConnection, top_n: int = 5, flt: PostFilter | None = None
) -> Report:
    flt = flt or PostFilter()
    where, params = flt.sql()
    report = Report()
    report.total_posts = int(
        (await conn.execute(text(f"SELECT COUNT(*) FROM Post p WHERE {where}"), params)).scalar_one()
    )
    start, end = today_range()
    report.today_posts = int(
        (
            await conn.execute(
                text(
                    f"SELECT COUNT(*) FROM Post p WHERE {where} "
                    "AND p.created_at >= :t_start AND p.created_at < :t_end"
                ),
                {**params, "t_start": start, "t_end": end},
            )
        ).scalar_one()
    )
    users = await conn.execute(
        text(
            "SELECT pe.id, pe.firstname, pe.lastname, pe.bale_username, pe.bale_user_id, "
            f"COUNT(*) AS n FROM Post p JOIN Person pe ON pe.id = p.person_id WHERE {where} "
            "GROUP BY pe.id, pe.firstname, pe.lastname, pe.bale_username, pe.bale_user_id "
            "ORDER BY n DESC, pe.id LIMIT :top"
        ),
        {**params, "top": top_n},
    )
    report.top_users = [(person_label(row), int(row.n)) for row in users]
    tags = await conn.execute(
        text(
            "SELECT h.name, COUNT(p.id) AS n FROM Hashtag h "
            "LEFT JOIN PostHashtag ph ON ph.hashtag_id = h.id "
            f"LEFT JOIN Post p ON p.id = ph.post_id AND {where} "
            "GROUP BY h.id, h.name ORDER BY n DESC, h.id"
        ),
        params,
    )
    report.by_hashtag = [(str(row.name), int(row.n)) for row in tags]
    types = await conn.execute(
        text(
            f"SELECT p.content_type, COUNT(*) AS n FROM Post p WHERE {where} "
            "GROUP BY p.content_type ORDER BY p.content_type"
        ),
        params,
    )
    report.by_content_type = [(int(row.content_type), int(row.n)) for row in types]
    groups = await conn.execute(
        text(
            "SELECT g.bale_group_name, COUNT(p.id) AS n FROM EhyaGroup g "
            f"LEFT JOIN Post p ON p.ehya_group_id = g.id AND {where} "
            "GROUP BY g.id, g.bale_group_name ORDER BY n DESC, g.id"
        ),
        params,
    )
    report.by_group = [(str(row.bale_group_name), int(row.n)) for row in groups]
    return report


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


async def export_rows(conn: AsyncConnection, flt: PostFilter) -> list[ExportRow]:
    where, params = flt.sql()
    result = await conn.execute(
        text(
            "SELECT p.id, p.created_at, p.posted_at, p.content_type, p.content_text, "
            "pe.firstname, pe.lastname, pe.bale_username, pe.bale_user_id, g.bale_group_name, "
            "(SELECT GROUP_CONCAT(h.name ORDER BY h.id SEPARATOR '، ') FROM PostHashtag ph "
            " JOIN Hashtag h ON h.id = ph.hashtag_id WHERE ph.post_id = p.id) AS tags, "
            "(SELECT COUNT(*) FROM PostMedia m WHERE m.post_id = p.id) AS files "
            "FROM Post p JOIN Person pe ON pe.id = p.person_id "
            f"JOIN EhyaGroup g ON g.id = p.ehya_group_id WHERE {where} ORDER BY p.id"
        ),
        params,
    )
    return [
        ExportRow(
            post_id=int(row.id),
            created_at=row.created_at,
            posted_at=row.posted_at,
            sender=person_label(row),
            bale_user_id=row.bale_user_id,
            group_name=str(row.bale_group_name),
            content_type=int(row.content_type),
            hashtags=str(row.tags or ""),
            content_text=str(row.content_text or ""),
            files=int(row.files),
        )
        for row in result
    ]
