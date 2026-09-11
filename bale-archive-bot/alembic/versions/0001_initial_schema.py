"""Initial schema: users, groups, tags, submissions, media, state, outbox, audit.

Revision ID: 0001
Revises:
Create Date: 2026-08-19

On Microsoft SQL Server every textual column is NVARCHAR (never VARCHAR)
so Persian round-trips intact. Unicode string literals use the N'…' prefix.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.mssql import NVARCHAR

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


def _now_sql(is_pg: bool, is_mssql: bool) -> sa.TextClause:
    if is_pg:
        return sa.text("now()")
    if is_mssql:
        return sa.text("SYSUTCDATETIME()")
    return sa.text("CURRENT_TIMESTAMP")


def _n_literal(value: str, *, is_mssql: bool) -> sa.TextClause:
    """SQL string literal; N'…' on SQL Server so Unicode is preserved."""
    if is_mssql:
        return sa.text(f"N'{value}'")
    return sa.text(f"'{value}'")


def _nvarchar_in_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"N'{item}'" for item in values)


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    is_mssql = bind.dialect.name == "mssql"
    now_sql = _now_sql(is_pg, is_mssql)
    json_empty = _n_literal("{}", is_mssql=is_mssql)
    json_array = _n_literal("[]", is_mssql=is_mssql)

    # Explicit unicode text: NVARCHAR on SQL Server, UnicodeText elsewhere.
    text_col: sa.types.TypeEngine[object]
    enum_col: sa.types.TypeEngine[object]
    if is_mssql:
        text_col = NVARCHAR(None)
        enum_col = NVARCHAR(30)
    else:
        text_col = sa.UnicodeText()
        enum_col = sa.Unicode(30)

    if is_pg:
        # Extension for Persian trigram search. Requires appropriate rights;
        # on managed DBaaS run it once as the maintenance user if this fails.
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        content_type_type: sa.types.TypeEngine[object] = sa.Enum(
            *CONTENT_TYPES, name="content_type_enum"
        )
        submission_status_type: sa.types.TypeEngine[object] = sa.Enum(
            *SUBMISSION_STATUSES, name="submission_status_enum"
        )
        storage_status_type: sa.types.TypeEngine[object] = sa.Enum(
            *STORAGE_STATUSES, name="storage_status_enum"
        )
        json_type: sa.types.TypeEngine[object] = postgresql.JSONB(
            astext_type=sa.UnicodeText()
        )
        urls_type: sa.types.TypeEngine[object] = postgresql.ARRAY(sa.UnicodeText())
    elif is_mssql:
        content_type_type = enum_col
        submission_status_type = enum_col
        storage_status_type = enum_col
        json_type = NVARCHAR(None)
        urls_type = NVARCHAR(None)
    else:
        content_type_type = sa.Enum(
            *CONTENT_TYPES, name="content_type_enum", native_enum=False
        )
        submission_status_type = sa.Enum(
            *SUBMISSION_STATUSES, name="submission_status_enum", native_enum=False
        )
        storage_status_type = sa.Enum(
            *STORAGE_STATUSES, name="storage_status_enum", native_enum=False
        )
        json_type = sa.JSON()
        urls_type = sa.JSON()

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("bale_user_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("username", text_col),
        sa.Column("first_name", text_col),
        sa.Column("last_name", text_col),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_forgotten", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("has_private_chat", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "locale",
            text_col,
            nullable=False,
            server_default=_n_literal("fa", is_mssql=is_mssql),
        ),
        sa.Column(
            "first_seen_at", sa.DateTime(timezone=True), nullable=False,
            server_default=now_sql,
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), nullable=False,
            server_default=now_sql,
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
        sa.Column("title", text_col),
        sa.Column("chat_type", text_col, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("bot_can_delete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("settings", json_type, nullable=False, server_default=json_empty),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), nullable=False,
            server_default=now_sql,
        ),
    )

    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("slug", text_col, nullable=False, unique=True),
        sa.Column("title_fa", text_col, nullable=False),
        sa.Column("hashtag", text_col, nullable=False, unique=True),
        sa.Column("description", text_col),
        sa.Column("emoji", text_col),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("tags.id", ondelete="SET NULL")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=now_sql,
        ),
    )

    op.create_table(
        "submissions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("short_id", text_col, nullable=False, unique=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("group_id", sa.BigInteger(), sa.ForeignKey("groups.id")),
        sa.Column(
            "status",
            submission_status_type,
            nullable=False,
            server_default=_n_literal("draft", is_mssql=is_mssql),
        ),
        sa.Column("content_type", content_type_type, nullable=False),
        sa.Column("content_subtype", text_col),
        sa.Column("text_content", text_col),
        sa.Column("text_normalized", text_col),
        sa.Column("caption", text_col),
        sa.Column(
            "urls", urls_type, nullable=False,
            server_default=sa.text("'{}'") if is_pg else json_array,
        ),
        sa.Column("is_forwarded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("forward_source", text_col),
        sa.Column("original_message_id", sa.BigInteger()),
        sa.Column("archive_chat_id", sa.BigInteger()),
        sa.Column("archive_message_id", sa.BigInteger()),
        sa.Column("published_message_id", sa.BigInteger()),
        sa.Column("wizard_chat_id", sa.BigInteger()),
        sa.Column("wizard_message_id", sa.BigInteger()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=now_sql,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=now_sql,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("reminded_at", sa.DateTime(timezone=True)),
        sa.Column("meta", json_type, nullable=False, server_default=json_empty),
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
            server_default=now_sql,
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
        sa.Column("bale_file_id", text_col, nullable=False),
        sa.Column("bale_file_unique", text_col),
        sa.Column("file_name", text_col),
        sa.Column("mime_type", text_col),
        sa.Column("file_size_bytes", sa.BigInteger()),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("sha256", text_col),
        sa.Column("storage_bucket", text_col),
        sa.Column("storage_key", text_col),
        sa.Column(
            "storage_status",
            storage_status_type,
            nullable=False,
            server_default=_n_literal("pending", is_mssql=is_mssql),
        ),
        sa.Column("storage_attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("last_error", text_col),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=now_sql,
        ),
        sa.Column("stored_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "conversation_states",
        sa.Column("chat_id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("state", text_col, nullable=False),
        sa.Column("history", json_type, nullable=False, server_default=json_array),
        sa.Column("payload", json_type, nullable=False, server_default=json_empty),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=now_sql,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "processed_updates",
        sa.Column("update_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column(
            "processed_at", sa.DateTime(timezone=True), nullable=False,
            server_default=now_sql,
        ),
    )

    op.create_table(
        "outbox",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("kind", text_col, nullable=False),
        sa.Column("target_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("payload", json_type, nullable=False),
        sa.Column(
            "status",
            text_col,
            nullable=False,
            server_default=_n_literal("pending", is_mssql=is_mssql),
        ),
        sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("last_error", text_col),
        sa.Column(
            "next_retry_at", sa.DateTime(timezone=True), nullable=False,
            server_default=now_sql,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=now_sql,
        ),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("actor_user_id", sa.BigInteger()),
        sa.Column("action", text_col, nullable=False),
        sa.Column("entity_type", text_col),
        sa.Column("entity_id", text_col),
        sa.Column("payload", json_type, nullable=False, server_default=json_empty),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=now_sql,
        ),
    )

    op.create_table(
        "app_settings",
        sa.Column("key", text_col, primary_key=True),
        sa.Column("value", json_type, nullable=False),
        sa.Column("updated_by", sa.BigInteger()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=now_sql,
        ),
    )

    if is_mssql:
        op.create_check_constraint(
            "ck_submissions_status",
            "submissions",
            f"status IN ({_nvarchar_in_list(SUBMISSION_STATUSES)})",
        )
        op.create_check_constraint(
            "ck_submissions_content_type",
            "submissions",
            f"content_type IN ({_nvarchar_in_list(CONTENT_TYPES)})",
        )
        op.create_check_constraint(
            "ck_media_files_storage_status",
            "media_files",
            f"storage_status IN ({_nvarchar_in_list(STORAGE_STATUSES)})",
        )
        for table, column in (
            ("groups", "settings"),
            ("submissions", "meta"),
            ("submissions", "urls"),
            ("conversation_states", "history"),
            ("conversation_states", "payload"),
            ("outbox", "payload"),
            ("audit_log", "payload"),
            ("app_settings", "value"),
        ):
            op.create_check_constraint(
                f"ck_{table}_{column}_isjson",
                table,
                f"({column} IS NULL OR ISJSON({column}) = 1)",
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
    is_mssql = bind.dialect.name == "mssql"

    if is_pg:
        op.execute("DROP INDEX IF EXISTS idx_sub_text_trgm")
        op.execute("DROP INDEX IF EXISTS idx_sub_meta_gin")

    if is_mssql:
        for name, table in (
            ("ck_app_settings_value_isjson", "app_settings"),
            ("ck_audit_log_payload_isjson", "audit_log"),
            ("ck_outbox_payload_isjson", "outbox"),
            ("ck_conversation_states_payload_isjson", "conversation_states"),
            ("ck_conversation_states_history_isjson", "conversation_states"),
            ("ck_submissions_urls_isjson", "submissions"),
            ("ck_submissions_meta_isjson", "submissions"),
            ("ck_groups_settings_isjson", "groups"),
            ("ck_media_files_storage_status", "media_files"),
            ("ck_submissions_content_type", "submissions"),
            ("ck_submissions_status", "submissions"),
        ):
            op.drop_constraint(name, table, type_="check")

    for table in (
        "app_settings", "audit_log", "outbox", "processed_updates",
        "conversation_states", "media_files", "submission_tags",
        "submissions", "tags", "groups", "users",
    ):
        op.drop_table(table)

    if is_pg:
        for enum_name in ("storage_status_enum", "submission_status_enum", "content_type_enum"):
            sa.Enum(name=enum_name).drop(bind, checkfirst=True)
