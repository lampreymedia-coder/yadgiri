"""Admin roster helpers: who counts as admin and last-admin safety."""

from __future__ import annotations

from collections.abc import Iterable


def effective_admin_ids(
    *,
    db_admin_bale_ids: Iterable[int],
    runtime_admin_ids: Iterable[int],
    env_admin_ids: Iterable[int],
) -> set[int]:
    """Union of DB flags, in-memory runtime set, and ADMIN_USER_IDS from env."""
    ids = set(db_admin_bale_ids)
    ids.update(runtime_admin_ids)
    ids.update(env_admin_ids)
    return ids


def can_remove_admin(effective_ids: set[int], target_bale_id: int) -> bool:
    """False when removing ``target_bale_id`` would leave zero admins."""
    return len(effective_ids - {target_bale_id}) >= 1
