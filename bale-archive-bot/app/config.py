"""Application configuration loaded from environment variables.

All settings are validated at startup; a missing/invalid required value
aborts the process with a clear error instead of failing later at runtime.
"""

from __future__ import annotations

import secrets
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class RunMode(StrEnum):
    POLLING = "polling"
    WEBHOOK = "webhook"


class IngestMode(StrEnum):
    GROUP_GATEWAY = "group_gateway"
    PRIVATE_FIRST = "private_first"
    HYBRID = "hybrid"


class ExpiredPolicy(StrEnum):
    REPUBLISH = "republish"
    AUTO_TAG = "auto_tag"
    KEEP_DRAFT = "keep_draft"


class StorageBackend(StrEnum):
    LOCAL = "local"
    S3 = "s3"


class Settings(BaseSettings):
    """Environment-driven settings. See .env.example for documentation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Bale ───
    bale_bot_token: str = Field(alias="BALE_BOT_TOKEN")
    bale_api_base: str = Field(default="https://tapi.bale.ai", alias="BALE_API_BASE")
    run_mode: RunMode = Field(default=RunMode.POLLING, alias="RUN_MODE")
    webhook_base_url: str = Field(default="", alias="WEBHOOK_BASE_URL")
    webhook_secret_path: str = Field(default="", alias="WEBHOOK_SECRET_PATH")
    polling_idle_sleep: float = Field(default=2.0, alias="POLLING_IDLE_SLEEP")
    polling_busy_sleep: float = Field(default=0.3, alias="POLLING_BUSY_SLEEP")

    # ─── Chats ───
    archive_chat_id: int | None = Field(default=None, alias="ARCHIVE_CHAT_ID")
    admin_chat_id: int | None = Field(default=None, alias="ADMIN_CHAT_ID")
    admin_user_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list, alias="ADMIN_USER_IDS"
    )
    allowed_group_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list, alias="ALLOWED_GROUP_IDS"
    )

    # ─── Behaviour ───
    ingest_mode: IngestMode = Field(default=IngestMode.HYBRID, alias="INGEST_MODE")
    submission_ttl_minutes: int = Field(default=30, alias="SUBMISSION_TTL_MINUTES")
    reminder_after_minutes: int = Field(default=10, alias="REMINDER_AFTER_MINUTES")
    expired_policy: ExpiredPolicy = Field(default=ExpiredPolicy.REPUBLISH, alias="EXPIRED_POLICY")
    undo_window_minutes: int = Field(default=10, alias="UNDO_WINDOW_MINUTES")
    private_summary_ttl_seconds: int = Field(default=30, alias="PRIVATE_SUMMARY_TTL_SECONDS")
    album_window_ms: int = Field(default=2500, alias="ALBUM_WINDOW_MS")
    ignore_stickers: bool = Field(default=True, alias="IGNORE_STICKERS")
    formatting_enabled: bool = Field(default=False, alias="FORMATTING_ENABLED")

    # ─── Database (local Postgres on this Windows machine) ───
    database_url: str = Field(alias="DATABASE_URL")
    db_pool_size: int = Field(default=10, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, alias="DB_MAX_OVERFLOW")

    # Conversation state always lives in conversation_states (Postgres).
    # The name is kept so existing .env files stay valid.
    state_backend: str = Field(default="postgres", alias="STATE_BACKEND")

    # ─── Local media (switch STORAGE_BACKEND=s3 later if needed) ───
    storage_backend: StorageBackend = Field(default=StorageBackend.LOCAL, alias="STORAGE_BACKEND")
    media_root: str = Field(default="data/media", alias="MEDIA_ROOT")
    media_download_enabled: bool = Field(default=True, alias="MEDIA_DOWNLOAD_ENABLED")
    s3_endpoint_url: str = Field(default="", alias="S3_ENDPOINT_URL")
    s3_access_key: str = Field(default="", alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field(default="", alias="S3_SECRET_KEY")
    s3_bucket_media: str = Field(default="bale-archive-media", alias="S3_BUCKET_MEDIA")
    s3_max_download_mb: int = Field(default=20, alias="S3_MAX_DOWNLOAD_MB")

    # ─── Limits ───
    rate_global_rps: float = Field(default=20.0, alias="RATE_GLOBAL_RPS")
    rate_per_chat_per_sec: float = Field(default=1.0, alias="RATE_PER_CHAT_PER_SEC")
    rate_per_group_per_min: float = Field(default=20.0, alias="RATE_PER_GROUP_PER_MIN")
    max_submissions_per_user_per_hour: int = Field(
        default=60, alias="MAX_SUBMISSIONS_PER_USER_PER_HOUR"
    )
    admin_notify_batch_threshold: int = Field(default=5, alias="ADMIN_NOTIFY_BATCH_THRESHOLD")

    # ─── Operations ───
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="json", alias="LOG_FORMAT")
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")
    tz: str = Field(default="Asia/Tehran", alias="TZ")
    metrics_enabled: bool = Field(default=True, alias="METRICS_ENABLED")
    backup_dir: str = Field(default="data/backups", alias="BACKUP_DIR")

    # ─── Internal (not user-facing) ───
    spool_dir: str = Field(default="data/spool", alias="SPOOL_DIR")

    @field_validator("admin_user_ids", "allowed_group_ids", mode="before")
    @classmethod
    def _parse_id_list(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(part) for part in value.replace(" ", "").split(",") if part]
        return value

    @field_validator("archive_chat_id", "admin_chat_id", mode="before")
    @classmethod
    def _empty_str_chat_id(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("state_backend", mode="before")
    @classmethod
    def _force_postgres_state(cls, value: object) -> str:
        return "postgres"

    @field_validator("bale_bot_token")
    @classmethod
    def _token_not_empty(cls, value: str) -> str:
        if not value.strip():
            msg = "BALE_BOT_TOKEN must be set"
            raise ValueError(msg)
        return value.strip()

    @model_validator(mode="after")
    def _validate_webhook(self) -> Settings:
        if self.run_mode is RunMode.WEBHOOK:
            if not self.webhook_base_url:
                msg = "WEBHOOK_BASE_URL is required when RUN_MODE=webhook"
                raise ValueError(msg)
            if not self.webhook_secret_path:
                object.__setattr__(self, "webhook_secret_path", secrets.token_urlsafe(24))
        return self

    @property
    def webhook_path(self) -> str:
        return "/webhook/" + self.webhook_secret_path

    @property
    def webhook_url(self) -> str:
        return self.webhook_base_url.rstrip("/") + self.webhook_path

    @property
    def max_download_bytes(self) -> int:
        return self.s3_max_download_mb * 1024 * 1024

    @property
    def media_root_path(self) -> Path:
        return Path(self.media_root)

    @property
    def spool_dir_path(self) -> Path:
        return Path(self.spool_dir)

    @property
    def backup_dir_path(self) -> Path:
        return Path(self.backup_dir)

    def is_admin_user(self, bale_user_id: int) -> bool:
        return bale_user_id in self.admin_user_ids


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide validated settings instance."""
    return Settings()
