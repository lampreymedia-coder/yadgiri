"""SQLAlchemy 2.0 ORM models mirroring the mandated SQL schema.

Notes:

* ``users.display_name`` is a Postgres generated column; it is created in
  the Alembic migration and computed in Python here so SQLite tests work.
* ``submissions.urls`` is ``TEXT[]`` on Postgres (see migration) and JSON
  on other dialects; both round-trip Python ``list[str]``.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntPK, PortableJSON


def utcnow() -> datetime:
    return datetime.now(UTC)


class ContentType(enum.StrEnum):
    TEXT = "text"
    LINK = "link"
    IMAGE = "image"
    VIDEO = "video"
    ANIMATION = "animation"
    VOICE = "voice"
    AUDIO = "audio"
    DOCUMENT = "document"
    STICKER = "sticker"
    CONTACT = "contact"
    LOCATION = "location"
    ALBUM = "album"
    OTHER = "other"


class SubmissionStatus(enum.StrEnum):
    DRAFT = "draft"
    AWAITING_DECISION = "awaiting_decision"
    AWAITING_TAG_COUNT = "awaiting_tag_count"
    AWAITING_TAGS = "awaiting_tags"
    AWAITING_CONFIRM = "awaiting_confirm"
    COMPLETED = "completed"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAILED = "failed"


IN_PROGRESS_STATUSES: tuple[SubmissionStatus, ...] = (
    SubmissionStatus.DRAFT,
    SubmissionStatus.AWAITING_DECISION,
    SubmissionStatus.AWAITING_TAG_COUNT,
    SubmissionStatus.AWAITING_TAGS,
    SubmissionStatus.AWAITING_CONFIRM,
)


class StorageStatus(enum.StrEnum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    STORED = "stored"
    SKIPPED_TOO_LARGE = "skipped_too_large"
    FAILED = "failed"
    DUPLICATE = "duplicate"


def _enum(py_enum: type[enum.StrEnum], name: str) -> Enum:
    return Enum(
        py_enum,
        name=name,
        values_callable=lambda e: [member.value for member in e],
        native_enum=True,
        create_constraint=True,
        validate_strings=True,
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigIntPK(), primary_key=True, autoincrement=True)
    bale_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(Text)
    first_name: Mapped[str | None] = mapped_column(Text)
    last_name: Mapped[str | None] = mapped_column(Text)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_forgotten: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_private_chat: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    locale: Mapped[str] = mapped_column(Text, nullable=False, default="fa")
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    submissions: Mapped[list[Submission]] = relationship(back_populates="user")

    @property
    def display_name(self) -> str:
        """Mirror of the Postgres generated column, computed in Python."""
        return f"{self.first_name or ''} {self.last_name or ''}".strip()


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(BigIntPK(), primary_key=True, autoincrement=True)
    bale_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    chat_type: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    bot_can_delete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    settings: Mapped[dict[str, Any]] = mapped_column(PortableJSON(), nullable=False, default=dict)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    hashtag: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    emoji: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tags.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(BigIntPK(), primary_key=True, autoincrement=True)
    short_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    group_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("groups.id"))
    status: Mapped[SubmissionStatus] = mapped_column(
        _enum(SubmissionStatus, "submission_status_enum"),
        nullable=False,
        default=SubmissionStatus.DRAFT,
    )
    content_type: Mapped[ContentType] = mapped_column(
        _enum(ContentType, "content_type_enum"), nullable=False
    )
    content_subtype: Mapped[str | None] = mapped_column(Text)
    text_content: Mapped[str | None] = mapped_column(Text)
    text_normalized: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)
    urls: Mapped[list[str]] = mapped_column(
        JSON().with_variant(ARRAY(Text()), "postgresql"), nullable=False, default=list
    )
    is_forwarded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    forward_source: Mapped[str | None] = mapped_column(Text)
    # Message tracking
    original_message_id: Mapped[int | None] = mapped_column(BigInteger)
    archive_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    archive_message_id: Mapped[int | None] = mapped_column(BigInteger)
    published_message_id: Mapped[int | None] = mapped_column(BigInteger)
    wizard_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    wizard_message_id: Mapped[int | None] = mapped_column(BigInteger)
    # Timing
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    meta: Mapped[dict[str, Any]] = mapped_column(PortableJSON(), nullable=False, default=dict)
    raw_update: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON())

    user: Mapped[User] = relationship(back_populates="submissions")
    group: Mapped[Group | None] = relationship()
    tags: Mapped[list[Tag]] = relationship(secondary="submission_tags")
    media_files: Mapped[list[MediaFile]] = relationship(
        back_populates="submission", order_by="MediaFile.position"
    )

    __table_args__ = (
        Index("idx_sub_user_created", "user_id", created_at.desc()),
        Index("idx_sub_group_created", "group_id", created_at.desc()),
        Index(
            "idx_sub_status",
            "status",
            postgresql_where=text("status <> 'completed'"),
        ),
        Index("idx_sub_type_created", "content_type", created_at.desc()),
        Index(
            "idx_sub_completed_at",
            completed_at.desc(),
            postgresql_where=text("status = 'completed'"),
        ),
    )


class SubmissionTag(Base):
    __tablename__ = "submission_tags"

    submission_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("submissions.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(Integer, ForeignKey("tags.id"), primary_key=True)
    tagged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (Index("idx_subtags_tag", "tag_id", "submission_id"),)


class MediaFile(Base):
    __tablename__ = "media_files"

    id: Mapped[int] = mapped_column(BigIntPK(), primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    bale_file_id: Mapped[str] = mapped_column(Text, nullable=False)
    bale_file_unique: Mapped[str | None] = mapped_column(Text)
    file_name: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(Text)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(Text)
    storage_bucket: Mapped[str | None] = mapped_column(Text)
    storage_key: Mapped[str | None] = mapped_column(Text)
    storage_status: Mapped[StorageStatus] = mapped_column(
        _enum(StorageStatus, "storage_status_enum"),
        nullable=False,
        default=StorageStatus.PENDING,
    )
    storage_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    stored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    submission: Mapped[Submission] = relationship(back_populates="media_files")

    __table_args__ = (
        Index("idx_media_sub", "submission_id", "position"),
        Index(
            "idx_media_status",
            "storage_status",
            postgresql_where=text("storage_status IN ('pending','failed')"),
        ),
        Index("idx_media_sha", "sha256", postgresql_where=text("sha256 IS NOT NULL")),
    )


class ConversationState(Base):
    __tablename__ = "conversation_states"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    history: Mapped[list[str]] = mapped_column(PortableJSON(), nullable=False, default=list)
    payload: Mapped[dict[str, Any]] = mapped_column(PortableJSON(), nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProcessedUpdate(Base):
    __tablename__ = "processed_updates"

    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class OutboxItem(Base):
    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(BigIntPK(), primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    target_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(PortableJSON(), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    next_retry_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        Index("idx_outbox_ready", "next_retry_at", postgresql_where=text("status = 'pending'")),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigIntPK(), primary_key=True, autoincrement=True)
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(PortableJSON(), nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[Any] = mapped_column(PortableJSON(), nullable=False)
    updated_by: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
