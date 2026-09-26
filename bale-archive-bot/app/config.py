"""Application configuration loaded from environment variables (``.env``).

All settings are validated at startup; a missing/invalid required value
aborts the process with a clear error instead of failing later at runtime.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

EXPECTED_DATABASE = "Bale_Archive"


class Settings(BaseSettings):
    """Environment-driven settings. See ``deploy/env.template``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Bale ───
    bale_bot_token: str = Field(alias="BALE_BOT_TOKEN")
    bale_api_base: str = Field(default="https://tapi.bale.ai", alias="BALE_API_BASE")
    run_mode: str = Field(default="polling", alias="RUN_MODE")
    polling_idle_sleep: float = Field(default=2.0, alias="POLLING_IDLE_SLEEP")
    polling_busy_sleep: float = Field(default=0.3, alias="POLLING_BUSY_SLEEP")

    # ─── Chats / people ───
    archive_chat_id: int | None = Field(default=None, alias="ARCHIVE_CHAT_ID")
    admin_user_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list, alias="ADMIN_USER_IDS"
    )

    # ─── Behaviour ───
    wizard_ttl_minutes: int = Field(default=30, alias="WIZARD_TTL_MINUTES")
    reminder_after_minutes: int = Field(default=10, alias="REMINDER_AFTER_MINUTES")
    album_window_ms: int = Field(default=2500, alias="ALBUM_WINDOW_MS")
    max_submissions_per_user_per_hour: int = Field(
        default=60, alias="MAX_SUBMISSIONS_PER_USER_PER_HOUR"
    )

    # ─── Database: MySQL 8, database Bale_Archive ───
    database_url: str = Field(alias="DATABASE_URL")
    db_pool_size: int = Field(default=5, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=5, alias="DB_MAX_OVERFLOW")

    # ─── Local files (never the database) ───
    data_dir: str = Field(default="/var/lib/balebot", alias="DATA_DIR")
    media_download_enabled: bool = Field(default=True, alias="MEDIA_DOWNLOAD_ENABLED")
    max_download_mb: int = Field(default=20, alias="MAX_DOWNLOAD_MB")

    # ─── HTTP health endpoint (local only) ───
    http_host: str = Field(default="127.0.0.1", alias="HTTP_HOST")
    http_port: int = Field(default=8000, alias="HTTP_PORT")

    # ─── Limits ───
    rate_global_rps: float = Field(default=20.0, alias="RATE_GLOBAL_RPS")
    rate_per_chat_per_sec: float = Field(default=1.0, alias="RATE_PER_CHAT_PER_SEC")
    rate_per_group_per_min: float = Field(default=20.0, alias="RATE_PER_GROUP_PER_MIN")

    # ─── Operations ───
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="json", alias="LOG_FORMAT")
    tz: str = Field(default="Asia/Tehran", alias="TZ")

    @field_validator("admin_user_ids", mode="before")
    @classmethod
    def _parse_id_list(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(part) for part in value.replace(" ", "").split(",") if part]
        if isinstance(value, int):
            return [value]
        return value

    @field_validator("archive_chat_id", mode="before")
    @classmethod
    def _empty_str_chat_id(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("database_url")
    @classmethod
    def _mysql_only(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped.lower().startswith("mysql"):
            msg = "DATABASE_URL must be a MySQL URL (mysql+aiomysql://...)"
            raise ValueError(msg)
        return stripped

    @field_validator("run_mode")
    @classmethod
    def _polling_only(cls, value: str) -> str:
        if value.strip().lower() != "polling":
            msg = "RUN_MODE must be polling"
            raise ValueError(msg)
        return "polling"

    @field_validator("bale_bot_token")
    @classmethod
    def _token_not_empty(cls, value: str) -> str:
        if not value.strip():
            msg = "BALE_BOT_TOKEN must be set"
            raise ValueError(msg)
        return value.strip()

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def offset_file(self) -> Path:
        return self.data_path / "offset"

    @property
    def admins_file(self) -> Path:
        return self.data_path / "admins.json"

    @property
    def media_root(self) -> Path:
        return self.data_path / "media"

    @property
    def max_download_bytes(self) -> int:
        return self.max_download_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide validated settings instance.

    BALEBOT_ENV_FILE points at the server's env file (/etc/balebot/balebot.env).
    """
    return Settings(_env_file=os.environ.get("BALEBOT_ENV_FILE", ".env"))  # type: ignore[call-arg]
