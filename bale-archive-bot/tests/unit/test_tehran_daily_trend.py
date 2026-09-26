"""Daily trend must group by Tehran calendar day, not raw UTC date."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import ContentType, Submission, SubmissionStatus, User
from app.domain.reports import TEHRAN_UTC_OFFSET_MINUTES, ReportService


@pytest.mark.asyncio
async def test_daily_trend_counts_utc_2100_on_next_tehran_day() -> None:
    """21:00 UTC → 00:30 Tehran next day; raw CAST(UTC AS date) would be wrong."""
    assert TEHRAN_UTC_OFFSET_MINUTES == 210

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Stay inside the report's 30-day window: 21:00 UTC two days ago
    # becomes 00:30 Tehran on the following calendar day.
    completed_utc = (datetime.now(UTC) - timedelta(days=2)).replace(
        hour=21, minute=0, second=0, microsecond=0
    )
    expected_tehran_day = (completed_utc + timedelta(minutes=210)).date()
    wrong_utc_day = completed_utc.date()
    assert expected_tehran_day == wrong_utc_day + timedelta(days=1)

    async with factory() as session, session.begin():
        user = User(bale_user_id=7, first_name="آزمون", locale="fa")
        session.add(user)
        await session.flush()
        session.add(
            Submission(
                short_id="tehr01",
                user_id=user.id,
                status=SubmissionStatus.COMPLETED,
                content_type=ContentType.TEXT,
                text_content="مرز نیمه‌شب تهران",
                completed_at=completed_utc,
                created_at=completed_utc,
                updated_at=completed_utc,
            )
        )

    async with factory() as session:
        points = await ReportService(session).daily_trend()
        assert points, "expected at least one trend point"
        days = {point.day.date() for point in points}
        assert expected_tehran_day in days
        assert wrong_utc_day not in days
        matched = next(p for p in points if p.day.date() == expected_tehran_day)
        assert matched.items == 1

    await engine.dispose()
