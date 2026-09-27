"""Bot admins and owner: ADMIN_USER_IDS from .env plus a local admins.json file.

* The owner is the first id of ADMIN_USER_IDS until ownership is transferred;
  the new owner is then kept in admins.json.
* Only the owner adds/removes admins or transfers ownership.
* Admins from .env are permanent (they come back on every start), and the
  owner can never be removed, so at least one admin always remains.
Nothing here touches the database.
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
    IS_OWNER = "is_owner"
    LAST_ADMIN = "last_admin"


class AdminStore:
    def __init__(self, path: Path, env_ids: list[int]) -> None:
        self.path = path
        self.env_order = list(env_ids)
        self.env_ids = set(env_ids)
        self._file_ids: set[int] = set()
        self._owner_override: int | None = None
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
        owner = raw.get("owner") if isinstance(raw, dict) else None
        if isinstance(owner, int):
            self._owner_override = owner

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        payload = {"admins": sorted(self._file_ids), "owner": self._owner_override}
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, self.path)

    @property
    def all(self) -> set[int]:
        admins = self.env_ids | self._file_ids
        if self._owner_override is not None:
            admins.add(self._owner_override)
        return admins

    @property
    def owner(self) -> int | None:
        if self._owner_override is not None:
            return self._owner_override
        if self.env_order:
            return self.env_order[0]
        return min(self._file_ids) if self._file_ids else None

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.all

    def is_owner(self, user_id: int) -> bool:
        return self.owner == user_id

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
        if user_id == self.owner:
            return RemoveResult.IS_OWNER
        if user_id in self.env_ids:
            return RemoveResult.FROM_ENV
        if len(self.all) <= 1:
            return RemoveResult.LAST_ADMIN
        self._file_ids.discard(user_id)
        self._save()
        logger.info("admin_removed", user_id=user_id)
        return RemoveResult.REMOVED

    def transfer_owner(self, new_owner: int) -> None:
        """Make ``new_owner`` the owner; the old owner stays an admin."""
        old = self.owner
        if old is not None and old not in self.env_ids:
            self._file_ids.add(old)
        self._file_ids.add(new_owner)
        self._owner_override = new_owner
        self._save()
        logger.info("owner_transferred", old_owner=old, new_owner=new_owner)
