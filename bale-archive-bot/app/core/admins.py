"""Bot admins: ADMIN_USER_IDS from .env plus a local admins.json file.

Admins added with /addadmin live only in the file. Admins from .env are
permanent (they come back on every start), so at least one admin always
remains.
"""

from __future__ import annotations

import enum
import json
import os
from pathlib import Path

from app.observability.logging import get_logger

logger = get_logger(__name__)


class RemoveResult(enum.StrEnum):
    REMOVED = "removed"
    NOT_ADMIN = "not_admin"
    FROM_ENV = "from_env"
    LAST_ADMIN = "last_admin"


class AdminStore:
    def __init__(self, path: Path, env_ids: list[int]) -> None:
        self.path = path
        self.env_ids = set(env_ids)
        self._file_ids: set[int] = set()
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            logger.warning("admins_file_unreadable", error=str(exc))
            return
        items = raw.get("admins", []) if isinstance(raw, dict) else raw
        if isinstance(items, list):
            self._file_ids = {int(item) for item in items if str(item).lstrip("-").isdigit()}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"admins": sorted(self._file_ids)}), encoding="utf-8")
        os.replace(tmp, self.path)

    @property
    def all(self) -> set[int]:
        return self.env_ids | self._file_ids

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.all

    def add(self, user_id: int) -> bool:
        """Returns False when the user already was an admin."""
        if user_id in self.all:
            return False
        self._file_ids.add(user_id)
        self._save()
        logger.info("admin_added", user_id=user_id)
        return True

    def remove(self, user_id: int) -> RemoveResult:
        if user_id not in self.all:
            return RemoveResult.NOT_ADMIN
        if user_id in self.env_ids:
            return RemoveResult.FROM_ENV
        if len(self.all) <= 1:
            return RemoveResult.LAST_ADMIN
        self._file_ids.discard(user_id)
        self._save()
        logger.info("admin_removed", user_id=user_id)
        return RemoveResult.REMOVED
