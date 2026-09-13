"""PortableEnum must restore StrEnum members on SQL Server NVARCHAR columns."""

from __future__ import annotations

from sqlalchemy.dialects import mssql

from app.db.models import ContentType, StorageStatus, Submission, SubmissionStatus


def test_mssql_enum_result_is_enum_not_str() -> None:
    dialect = mssql.dialect()
    for column, sample, enum_cls in (
        (Submission.__table__.c.content_type, "text", ContentType),
        (Submission.__table__.c.status, "completed", SubmissionStatus),
    ):
        restored = column.type.process_result_value(sample, dialect)
        assert isinstance(restored, enum_cls)
        assert restored.value == sample
        # The ttl_sweeper bug: str has no .value
        assert restored.value == enum_cls(sample).value


def test_mssql_enum_bind_writes_plain_string() -> None:
    dialect = mssql.dialect()
    col = Submission.__table__.c.content_type
    assert col.type.process_bind_param(ContentType.VOICE, dialect) == "voice"
    assert col.type.process_bind_param(None, dialect) is None


def test_storage_status_enum_roundtrip_mssql() -> None:
    from app.db.models import MediaFile

    dialect = mssql.dialect()
    col = MediaFile.__table__.c.storage_status
    bound = col.type.process_bind_param(StorageStatus.PENDING, dialect)
    assert bound == "pending"
    assert col.type.process_result_value(bound, dialect) is StorageStatus.PENDING
