"""Admin reports built only from Post, PostHashtag, Hashtag, Person and EhyaGroup."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.timeutil import tehran_now


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


def _person_label(row: object) -> str:
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


async def build_report(conn: AsyncConnection, top_n: int = 5) -> Report:
    report = Report()
    report.total_posts = int((await conn.execute(text("SELECT COUNT(*) FROM Post"))).scalar_one())
    start = tehran_now().replace(hour=0, minute=0, second=0)
    report.today_posts = int(
        (
            await conn.execute(
                text("SELECT COUNT(*) FROM Post WHERE created_at >= :start AND created_at < :end"),
                {"start": start, "end": start + timedelta(days=1)},
            )
        ).scalar_one()
    )
    users = await conn.execute(
        text(
            "SELECT pe.id, pe.firstname, pe.lastname, pe.bale_username, pe.bale_user_id, "
            "COUNT(*) AS n FROM Post p JOIN Person pe ON pe.id = p.person_id "
            "GROUP BY pe.id, pe.firstname, pe.lastname, pe.bale_username, pe.bale_user_id "
            "ORDER BY n DESC, pe.id LIMIT :top"
        ),
        {"top": top_n},
    )
    report.top_users = [(_person_label(row), int(row.n)) for row in users]
    tags = await conn.execute(
        text(
            "SELECT h.name, COUNT(ph.post_id) AS n FROM Hashtag h "
            "LEFT JOIN PostHashtag ph ON ph.hashtag_id = h.id "
            "GROUP BY h.id, h.name ORDER BY n DESC, h.id"
        )
    )
    report.by_hashtag = [(str(row.name), int(row.n)) for row in tags]
    types = await conn.execute(
        text(
            "SELECT content_type, COUNT(*) AS n FROM Post "
            "GROUP BY content_type ORDER BY content_type"
        )
    )
    report.by_content_type = [(int(row.content_type), int(row.n)) for row in types]
    groups = await conn.execute(
        text(
            "SELECT g.bale_group_name, COUNT(p.id) AS n FROM EhyaGroup g "
            "LEFT JOIN Post p ON p.ehya_group_id = g.id "
            "GROUP BY g.id, g.bale_group_name ORDER BY n DESC, g.id"
        )
    )
    report.by_group = [(str(row.bale_group_name), int(row.n)) for row in groups]
    return report
