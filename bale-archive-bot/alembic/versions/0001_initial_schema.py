"""Initial schema: users, groups, tags, submissions, media, state, outbox, audit.

Revision ID: 0001
Revises:
Create Date: 2026-08-19

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

CONTENT_TYPES = (
    "text", "link", "image", "video", "animation", "voice", "audio",
    "document", "sticker", "contact", "location", "album", "other",
)
SUBMISSION_STATUSES = (
    "draft", "awaiting_decision", "awaiting_tag_count", "awaiting_tags",
    "awaiting_confirm", "completed", "declined", "cancelled", "expired", "failed",
)
STORAGE_STATUSES = (
    "pending", "downloading", "stored", "skipped_too_large", "failed", "duplicate",
)


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        # Extension for Persian trigram search. Requires appropriate rights;
        # on managed DBaaS run it once as the maintenance user if this fails.
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    content_type_enum = sa.Enum(*CONTENT_TYPES, name="content_type_enum")
    submission_status_enum = sa.Enum(*SUBMISSION_STATUSES, name="submission_status_enum")
    storage_status_enum = sa.Enum(*STORAGE_STATUSES, name="storage_status_enum")

    json_type = postgresql.JSONB(astext_type=sa.Text()) if is_pg else sa.JSON()
    urls_type = postgresql.ARRAY(sa.Text()) if is_pg else sa.JSON()

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("bale_user_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("username", sa.Text()),
        sa.Column("first_name", sa.Text()),
        sa.Column("last_name", sa.Text()),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_forgotten", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("has_private_chat", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("locale", sa.Text(), nullable=False, server_default="fa"),
        sa.Column(
            "first_seen_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()") if is_pg else sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()") if is_pg else sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    if is_pg:
        op.execute(
            "ALTER TABLE users ADD COLUMN display_name TEXT GENERATED ALWAYS AS "
            "(btrim(coalesce(first_name,'') || ' ' || coalesce(last_name,''))) STORED"
        )

    op.create_table(
        "groups",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("bale_chat_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("title", sa.Text()),
        sa.Column("chat_type", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("bot_can_delete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("settings", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()") if is_pg else sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("hashtag", sa.Text(), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
        sa.Column("emoji", sa.Text()),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("tags.id", ondelete="SET NULL")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()") if is_pg else sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_table(
        "submissions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("short_id", sa.Text(), nullable=False, unique=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("group_id", sa.BigInteger(), sa.ForeignKey("groups.id")),
        sa.Column("status", submission_status_enum, nullable=False, server_default="draft"),
        sa.Column("content_type", content_type_enum, nullable=False),
        sa.Column("content_subtype", sa.Text()),
        sa.Column("text_content", sa.Text()),
        sa.Column("text_normalized", sa.Text()),
        sa.Column("caption", sa.Text()),
        sa.Column(
            "urls", urls_type, nullable=False,
            server_default=sa.text("'{}'") if is_pg else sa.text("'[]'"),
        ),
        sa.Column("is_forwarded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("forward_source", sa.Text()),
        sa.Column("original_message_id", sa.BigInteger()),
        sa.Column("archive_chat_id", sa.BigInteger()),
        sa.Column("archive_message_id", sa.BigInteger()),
        sa.Column("published_message_id", sa.BigInteger()),
        sa.Column("wizard_chat_id", sa.BigInteger()),
        sa.Column("wizard_message_id", sa.BigInteger()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()") if is_pg else sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()") if is_pg else sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("reminded_at", sa.DateTime(timezone=True)),
        sa.Column("meta", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("raw_update", json_type),
    )

    op.create_table(
        "submission_tags",
        sa.Column(
            "submission_id", sa.BigInteger(),
            sa.ForeignKey("submissions.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column("tag_id", sa.Integer(), sa.ForeignKey("tags.id"), primary_key=True),
        sa.Column(
            "tagged_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()") if is_pg else sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_table(
        "media_files",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "submission_id", sa.BigInteger(),
            sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("position", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("bale_file_id", sa.Text(), nullable=False),
        sa.Column("bale_file_unique", sa.Text()),
        sa.Column("file_name", sa.Text()),
        sa.Column("mime_type", sa.Text()),
        sa.Column("file_size_bytes", sa.BigInteger()),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("sha256", sa.Text()),
        sa.Column("storage_bucket", sa.Text()),
        sa.Column("storage_key", sa.Text()),
        sa.Column("storage_status", storage_status_enum, nullable=False, server_default="pending"),
        sa.Column("storage_attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()") if is_pg else sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("stored_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "conversation_states",
        sa.Column("chat_id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("history", json_type, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("payload", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()") if is_pg else sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "processed_updates",
        sa.Column("update_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column(
            "processed_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()") if is_pg else sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_table(
        "outbox",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("target_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("payload", json_type, nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column(
            "next_retry_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()") if is_pg else sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()") if is_pg else sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("actor_user_id", sa.BigInteger()),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text()),
        sa.Column("entity_id", sa.Text()),
        sa.Column("payload", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()") if is_pg else sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_table(
        "app_settings",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", json_type, nullable=False),
        sa.Column("updated_by", sa.BigInteger()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()") if is_pg else sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # ─── Indexes ───
    op.create_index("idx_sub_user_created", "submissions", ["user_id", sa.text("created_at DESC")])
    op.create_index("idx_sub_group_created", "submissions", ["group_id", sa.text("created_at DESC")])
    op.create_index("idx_sub_type_created", "submissions", ["content_type", sa.text("created_at DESC")])
    op.create_index("idx_subtags_tag", "submission_tags", ["tag_id", "submission_id"])
    op.create_index("idx_media_sub", "media_files", ["submission_id", "position"])
    if is_pg:
        op.create_index(
            "idx_sub_status", "submissions", ["status"],
            postgresql_where=sa.text("status <> 'completed'"),
        )
        op.create_index(
            "idx_sub_completed_at", "submissions", [sa.text("completed_at DESC")],
            postgresql_where=sa.text("status = 'completed'"),
        )
        op.create_index(
            "idx_media_status", "media_files", ["storage_status"],
            postgresql_where=sa.text("storage_status IN ('pending','failed')"),
        )
        op.create_index(
            "idx_media_sha", "media_files", ["sha256"],
            postgresql_where=sa.text("sha256 IS NOT NULL"),
        )
        op.create_index(
            "idx_outbox_ready", "outbox", ["next_retry_at"],
            postgresql_where=sa.text("status = 'pending'"),
        )
        op.execute(
            "CREATE INDEX idx_sub_meta_gin ON submissions USING GIN (meta jsonb_path_ops)"
        )
        op.execute(
            "CREATE INDEX idx_sub_text_trgm ON submissions USING GIN "
            "(text_normalized gin_trgm_ops)"
        )
    else:
        op.create_index("idx_sub_status", "submissions", ["status"])
        op.create_index("idx_sub_completed_at", "submissions", ["completed_at"])
        op.create_index("idx_media_status", "media_files", ["storage_status"])
        op.create_index("idx_media_sha", "media_files", ["sha256"])
        op.create_index("idx_outbox_ready", "outbox", ["next_retry_at"])


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        op.execute("DROP INDEX IF EXISTS idx_sub_text_trgm")
        op.execute("DROP INDEX IF EXISTS idx_sub_meta_gin")

    for table in (
        "app_settings", "audit_log", "outbox", "processed_updates",
        "conversation_states", "media_files", "submission_tags",
        "submissions", "tags", "groups", "users",
    ):
        op.drop_table(table)

    if is_pg:
        for enum_name in ("storage_status_enum", "submission_status_enum", "content_type_enum"):
            sa.Enum(name=enum_name).drop(bind, checkfirst=True)
