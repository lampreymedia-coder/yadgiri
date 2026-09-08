"""ReportService must run on SQLite (the live Cloud Agent database)."""

from __future__ import annotations

from app.db.models import ContentType, SubmissionStatus
from app.db.repositories.groups import GroupRepository
from app.db.repositories.submissions import SubmissionRepository
from app.db.repositories.tags import TagRepository
from app.db.repositories.users import UserRepository
from app.db.session import Database
from app.domain.reports import ReportService, is_postgres


async def test_sqlite_reports_cover_every_panel_query(seeded_db: Database) -> None:
    async with seeded_db.session() as session:
        assert is_postgres(session) is False
        users = UserRepository(session)
        user = await users.upsert_from_bale(1, "ali", "علی", "احمدی")
        groups = GroupRepository(session)
        group = await groups.upsert(-100, "پژوهش", "group")
        subs = SubmissionRepository(session)
        submission = await subs.create_draft(
            user_id=user.id,
            group_id=group.id,
            content_type=ContentType.TEXT,
            content_subtype=None,
            text_content="متن آزمایشی درباره‌ی هوش مصنوعی",
            text_normalized="متن ازمایشی درباره ی هوش مصنوعی",
            caption=None,
            urls=[],
            is_forwarded=False,
            forward_source=None,
            original_message_id=None,
            raw_update={"probe": True},
            ttl_minutes=30,
        )
        tags = TagRepository(session)
        active = await tags.list_active()
        await subs.set_tags(submission, [active[0].id])
        await subs.set_status(submission, SubmissionStatus.COMPLETED)
        short_id = submission.short_id

    async with seeded_db.session() as session:
        service = ReportService(session)
        overall = await service.overall()
        assert overall.total == 1
        assert overall.contributors == 1
        assert overall.today == 1
        assert overall.week == 1

        top_tags = await service.top_tags()
        used = [row for row in top_tags if row.items > 0]
        assert used[0].items == 1
        assert used[0].share_pct == 100.0

        top_users = await service.top_users(limit=5)
        assert top_users[0].items == 1
        assert top_users[0].display_name == "علی احمدی"
        assert top_users[0].texts == 1

        matrix = await service.type_matrix()
        assert matrix[0].text_count == 1

        trend = await service.daily_trend()
        assert trend[0].items == 1

        hits = await service.search("هوش", use_trigram=True)
        assert hits and hits[0].short_id == short_id

        health = await service.health()
        assert health.in_progress == 0
        assert health.failed == 0
        assert health.db_size

        export_rows = await service.submissions_for_export()
        assert len(export_rows) == 1
        assert export_rows[0]["display_name"] == "علی احمدی"
        assert export_rows[0]["short_id"] == short_id
        assert "#" in str(export_rows[0]["hashtags"] or "")
