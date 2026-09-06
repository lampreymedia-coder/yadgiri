"""Owner POST insert keeps the query writer's column order and value map."""

from __future__ import annotations

from app.db.models import ContentType, MediaFile, Submission
from app.db.owner_post import INSERT_POST_SQL, owner_post_values


def test_insert_sql_uses_query_writer_column_order() -> None:
    sql = str(INSERT_POST_SQL)
    assert sql.index("post_id") < sql.index("media_type") < sql.index("bale_file_id")
    assert sql.index("file_name") < sql.index("file_size") < sql.index("mime_type")
    assert sql.index("storage_path") < sql.index("duration") < sql.index("width")
    assert sql.index("width") < sql.index("height") < sql.index("created_at")
    assert "GETDATE()" in sql
    assert "INSERT INTO POST" in sql


def test_owner_post_values_map_bot_fields_without_renaming_columns() -> None:
    submission = Submission(id=41, content_type=ContentType.DOCUMENT)
    media = MediaFile(
        submission_id=41,
        position=0,
        bale_file_id="AgAD123",
        file_name="report.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        file_size_bytes=18506,
        duration_seconds=None,
        width=None,
        height=None,
        storage_key=r"data\media\41\file.xlsx",
    )
    values = owner_post_values(submission, media)
    assert values == {
        "post_id": 41,
        "media_type": "document",
        "bale_file_id": "AgAD123",
        "file_name": "report.xlsx",
        "file_size": 18506,
        "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "storage_path": r"data\media\41\file.xlsx",
        "duration": None,
        "width": None,
        "height": None,
    }


def test_text_post_sends_null_file_columns() -> None:
    submission = Submission(id=7, content_type=ContentType.TEXT)
    values = owner_post_values(submission, None)
    assert values["post_id"] == 7
    assert values["media_type"] == "text"
    assert values["bale_file_id"] is None
    assert values["storage_path"] is None
