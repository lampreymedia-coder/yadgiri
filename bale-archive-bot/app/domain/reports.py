"""Reporting queries (spec section 9) and text bar-chart rendering.

The mandated SQL is implemented verbatim with bound parameters. These
queries target PostgreSQL (FILTER/LATERAL/similarity); integration tests
run them against a real Postgres via testcontainers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_BLOCKS = "█▉▊▋▌▍▎▏"


def text_bar(share: float, max_width: int = 10) -> str:
    """Render a bar with block characters; ``share`` is 0..1."""
    share = max(0.0, min(1.0, share))
    eighths = round(share * max_width * 8)
    full, remainder = divmod(eighths, 8)
    bar = _BLOCKS[0] * full
    if remainder:
        bar += _BLOCKS[8 - remainder]
    return bar


@dataclass(slots=True)
class OverallStats:
    total: int
    today: int
    week: int
    contributors: int
    groups: int
    total_bytes: int


@dataclass(slots=True)
class TagStat:
    title_fa: str
    hashtag: str
    items: int
    contributors: int
    last_item_at: datetime | None
    share_pct: float
    is_active: bool


@dataclass(slots=True)
class UserStat:
    display_name: str
    username: str | None
    bale_user_id: int
    items: int
    tags_used: int
    texts: int
    images: int
    audios: int
    videos: int
    documents: int
    last_activity: datetime | None


@dataclass(slots=True)
class TypeMatrixRow:
    title_fa: str
    text_count: int
    link_count: int
    image_count: int
    video_count: int
    audio_count: int
    document_count: int
    total: int


@dataclass(slots=True)
class TrendPoint:
    day: datetime
    items: int


@dataclass(slots=True)
class SearchHit:
    short_id: str
    content_type: str
    completed_at: datetime | None
    snippet: str
    score: float


@dataclass(slots=True)
class HealthStats:
    in_progress: int
    failed: int
    outbox_pending: int
    media_backlog: int
    last_update_id: int | None
    db_size: str


_OVERALL_SQL = text("""
    SELECT
        count(*)                                                        AS total,
        count(*) FILTER (WHERE created_at >= now() - interval '1 day')  AS today,
        count(*) FILTER (WHERE created_at >= now() - interval '7 days') AS week,
        count(DISTINCT user_id)                                         AS contributors,
        count(DISTINCT group_id)                                        AS groups,
        coalesce(sum(m.total_bytes), 0)                                 AS total_bytes
    FROM submissions s
    LEFT JOIN LATERAL (
        SELECT sum(file_size_bytes) AS total_bytes
        FROM media_files WHERE submission_id = s.id
    ) m ON TRUE
    WHERE s.status = 'completed'
      AND (CAST(:from_ts AS timestamptz) IS NULL OR s.completed_at >= :from_ts)
      AND (CAST(:to_ts AS timestamptz) IS NULL OR s.completed_at < :to_ts)
    """)

_TOP_TAGS_SQL = text("""
    SELECT t.title_fa, t.hashtag, t.is_active,
           count(st.submission_id)                      AS items,
           count(DISTINCT s.user_id)                    AS contributors,
           max(s.completed_at)                          AS last_item_at,
           round(100.0 * count(st.submission_id)
                 / NULLIF(sum(count(st.submission_id)) OVER (), 0), 1) AS share_pct
    FROM tags t
    LEFT JOIN submission_tags st ON st.tag_id = t.id
    LEFT JOIN submissions s ON s.id = st.submission_id AND s.status = 'completed'
        AND (CAST(:from_ts AS timestamptz) IS NULL OR s.completed_at >= :from_ts)
        AND (CAST(:to_ts AS timestamptz) IS NULL OR s.completed_at < :to_ts)
    WHERE t.is_active OR :include_inactive
    GROUP BY t.id, t.title_fa, t.hashtag, t.is_active
    ORDER BY items DESC
    """)

_TOP_USERS_SQL = text("""
    SELECT coalesce(u.display_name, '') AS display_name, u.username, u.bale_user_id,
           count(DISTINCT s.id)                                 AS items,
           count(DISTINCT st.tag_id)                            AS tags_used,
           count(DISTINCT s.id) FILTER (WHERE s.content_type = 'text')      AS texts,
           count(DISTINCT s.id) FILTER (WHERE s.content_type IN ('image','album')) AS images,
           count(DISTINCT s.id) FILTER (WHERE s.content_type IN ('voice','audio'))  AS audios,
           count(DISTINCT s.id) FILTER (WHERE s.content_type = 'video')     AS videos,
           count(DISTINCT s.id) FILTER (WHERE s.content_type = 'document')  AS documents,
           max(s.completed_at)                                  AS last_activity
    FROM users u
    JOIN submissions s ON s.user_id = u.id AND s.status = 'completed'
    LEFT JOIN submission_tags st ON st.submission_id = s.id
    WHERE (CAST(:from_ts AS timestamptz) IS NULL OR s.completed_at >= :from_ts)
      AND (CAST(:to_ts AS timestamptz) IS NULL OR s.completed_at < :to_ts)
    GROUP BY u.id
    ORDER BY items DESC
    LIMIT :limit
    """)

_TYPE_MATRIX_SQL = text("""
    SELECT t.title_fa,
           count(*) FILTER (WHERE s.content_type = 'text')     AS text_count,
           count(*) FILTER (WHERE s.content_type = 'link')     AS link_count,
           count(*) FILTER (WHERE s.content_type IN ('image','album')) AS image_count,
           count(*) FILTER (WHERE s.content_type = 'video')    AS video_count,
           count(*) FILTER (WHERE s.content_type IN ('voice','audio')) AS audio_count,
           count(*) FILTER (WHERE s.content_type = 'document') AS document_count,
           count(*)                                            AS total
    FROM tags t
    JOIN submission_tags st ON st.tag_id = t.id
    JOIN submissions s ON s.id = st.submission_id AND s.status = 'completed'
    GROUP BY t.id, t.title_fa, t.sort_order
    ORDER BY t.sort_order
    """)

_TREND_SQL = text("""
    SELECT date_trunc('day', completed_at AT TIME ZONE 'Asia/Tehran') AS day,
           count(*) AS items
    FROM submissions
    WHERE status = 'completed' AND completed_at >= now() - interval '30 days'
    GROUP BY 1 ORDER BY 1
    """)

_SEARCH_SQL = text("""
    SELECT s.short_id, s.content_type, s.completed_at,
           left(s.text_normalized, 120) AS snippet,
           similarity(s.text_normalized, :q) AS score
    FROM submissions s
    WHERE s.status = 'completed' AND s.text_normalized % :q
    ORDER BY score DESC, s.completed_at DESC
    LIMIT 20
    """)

_SEARCH_FALLBACK_SQL = text("""
    SELECT s.short_id, s.content_type, s.completed_at,
           left(s.text_normalized, 120) AS snippet,
           0.0 AS score
    FROM submissions s
    WHERE s.status = 'completed' AND s.text_normalized ILIKE '%' || :q || '%'
    ORDER BY s.completed_at DESC
    LIMIT 20
    """)

_HEALTH_SQL = text("""
    SELECT
      (SELECT count(*) FROM submissions WHERE status IN
          ('draft','awaiting_decision','awaiting_tag_count','awaiting_tags','awaiting_confirm'))
          AS in_progress,
      (SELECT count(*) FROM submissions WHERE status = 'failed')                    AS failed,
      (SELECT count(*) FROM outbox WHERE status = 'pending')          AS outbox_pending,
      (SELECT count(*) FROM media_files WHERE storage_status IN ('pending','failed'))
          AS media_backlog,
      (SELECT max(update_id) FROM processed_updates)                  AS last_update_id,
      (SELECT pg_size_pretty(pg_database_size(current_database())))                 AS db_size
    """)


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def overall(
        self, from_ts: datetime | None = None, to_ts: datetime | None = None
    ) -> OverallStats:
        row = (
            await self._session.execute(_OVERALL_SQL, {"from_ts": from_ts, "to_ts": to_ts})
        ).one()
        return OverallStats(
            total=int(row.total),
            today=int(row.today),
            week=int(row.week),
            contributors=int(row.contributors),
            groups=int(row.groups),
            total_bytes=int(row.total_bytes),
        )

    async def top_tags(
        self,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
        include_inactive: bool = True,
    ) -> list[TagStat]:
        rows = await self._session.execute(
            _TOP_TAGS_SQL,
            {"from_ts": from_ts, "to_ts": to_ts, "include_inactive": include_inactive},
        )
        return [
            TagStat(
                title_fa=row.title_fa,
                hashtag=row.hashtag,
                items=int(row.items),
                contributors=int(row.contributors),
                last_item_at=row.last_item_at,
                share_pct=float(row.share_pct or 0.0),
                is_active=bool(row.is_active),
            )
            for row in rows
        ]

    async def top_users(
        self,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
        limit: int = 10,
    ) -> list[UserStat]:
        rows = await self._session.execute(
            _TOP_USERS_SQL, {"from_ts": from_ts, "to_ts": to_ts, "limit": limit}
        )
        return [
            UserStat(
                display_name=row.display_name,
                username=row.username,
                bale_user_id=int(row.bale_user_id),
                items=int(row.items),
                tags_used=int(row.tags_used),
                texts=int(row.texts),
                images=int(row.images),
                audios=int(row.audios),
                videos=int(row.videos),
                documents=int(row.documents),
                last_activity=row.last_activity,
            )
            for row in rows
        ]

    async def type_matrix(self) -> list[TypeMatrixRow]:
        rows = await self._session.execute(_TYPE_MATRIX_SQL)
        return [
            TypeMatrixRow(
                title_fa=row.title_fa,
                text_count=int(row.text_count),
                link_count=int(row.link_count),
                image_count=int(row.image_count),
                video_count=int(row.video_count),
                audio_count=int(row.audio_count),
                document_count=int(row.document_count),
                total=int(row.total),
            )
            for row in rows
        ]

    async def daily_trend(self) -> list[TrendPoint]:
        rows = await self._session.execute(_TREND_SQL)
        return [TrendPoint(day=row.day, items=int(row.items)) for row in rows]

    async def search(self, query: str, use_trigram: bool = True) -> list[SearchHit]:
        sql = _SEARCH_SQL if use_trigram else _SEARCH_FALLBACK_SQL
        rows = await self._session.execute(sql, {"q": query})
        return [
            SearchHit(
                short_id=row.short_id,
                content_type=str(row.content_type),
                completed_at=row.completed_at,
                snippet=row.snippet or "",
                score=float(row.score or 0.0),
            )
            for row in rows
        ]

    async def health(self) -> HealthStats:
        row = (await self._session.execute(_HEALTH_SQL)).one()
        return HealthStats(
            in_progress=int(row.in_progress),
            failed=int(row.failed),
            outbox_pending=int(row.outbox_pending),
            media_backlog=int(row.media_backlog),
            last_update_id=int(row.last_update_id) if row.last_update_id is not None else None,
            db_size=str(row.db_size),
        )

    async def submissions_for_export(
        self, from_ts: datetime | None = None, to_ts: datetime | None = None
    ) -> list[dict[str, Any]]:
        sql = text("""
            SELECT s.short_id, s.content_type, s.content_subtype, s.status,
                   s.text_content, s.caption, s.created_at, s.completed_at,
                   u.bale_user_id, coalesce(u.display_name, '') AS display_name, u.username,
                   g.title AS group_title,
                   (SELECT string_agg(t.hashtag, ' ')
                    FROM submission_tags st JOIN tags t ON t.id = st.tag_id
                    WHERE st.submission_id = s.id) AS hashtags,
                   (SELECT coalesce(sum(mf.file_size_bytes), 0)
                    FROM media_files mf WHERE mf.submission_id = s.id) AS total_bytes
            FROM submissions s
            JOIN users u ON u.id = s.user_id
            LEFT JOIN groups g ON g.id = s.group_id
            WHERE s.status = 'completed'
              AND (CAST(:from_ts AS timestamptz) IS NULL OR s.completed_at >= :from_ts)
              AND (CAST(:to_ts AS timestamptz) IS NULL OR s.completed_at < :to_ts)
            ORDER BY s.completed_at DESC
            """)
        rows = await self._session.execute(sql, {"from_ts": from_ts, "to_ts": to_ts})
        return [dict(row._mapping) for row in rows]
