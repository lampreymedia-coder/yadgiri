"""Research vs archive group roles, and per-hashtag archive destinations.

Content intake only runs in research groups. Each active hashtag can be bound
to its own private archive group; SQL remains the source of truth even when a
tag has no archive chat yet.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.bale.errors import BaleAPIError, Forbidden, NetworkError
from app.bale.methods import BaleAPI
from app.db.models import Group
from app.db.repositories.groups import GroupRepository
from app.db.repositories.misc import AppSettingsRepository
from app.observability.logging import get_logger

logger = get_logger(__name__)

ROLE_ARCHIVE = "archive"
ROLE_RESEARCH = "research"
ARCHIVE_SETTING_PREFIX = "archive_chat:"


def settings_of(group: Group) -> dict[str, Any]:
    raw = group.settings
    return dict(raw) if isinstance(raw, dict) else {}


def group_role(group: Group) -> str | None:
    raw = settings_of(group).get("role")
    return raw if isinstance(raw, str) else None


def is_archive(group: Group) -> bool:
    return group_role(group) == ROLE_ARCHIVE


def is_research(group: Group) -> bool:
    return group_role(group) == ROLE_RESEARCH


def needs_role(group: Group) -> bool:
    return group_role(group) not in {ROLE_RESEARCH, ROLE_ARCHIVE}


def role_already_asked(group: Group) -> bool:
    return bool(settings_of(group).get("role_asked"))


def tag_slug_of(group: Group) -> str | None:
    raw = settings_of(group).get("tag_slug")
    return raw if isinstance(raw, str) else None


def archive_setting_key(slug: str) -> str:
    return f"{ARCHIVE_SETTING_PREFIX}{slug}"


def patch_settings(group: Group, **changes: Any) -> None:
    group.settings = {**settings_of(group), **changes}


def is_archive_destination(group: Group, default_archive_chat_id: int | None) -> bool:
    if is_archive(group):
        return True
    return default_archive_chat_id is not None and group.bale_chat_id == default_archive_chat_id


async def try_delete_message(api: BaleAPI, chat_id: int | None, message_id: int | None) -> bool:
    """Best-effort delete. Never raises. Used to keep research groups uncluttered."""
    if chat_id is None or message_id is None:
        return False
    try:
        await api.delete_message(chat_id, message_id)
        return True
    except Forbidden:
        logger.info("delete_forbidden", chat_id=chat_id, message_id=message_id)
        return False
    except (BaleAPIError, NetworkError) as exc:
        logger.info("delete_failed", chat_id=chat_id, message_id=message_id, error=str(exc))
        return False


async def delete_group_prompt(api: BaleAPI, group: Group) -> None:
    settings = settings_of(group)
    chat_id = settings.get("prompt_chat_id")
    message_id = settings.get("prompt_message_id")
    if isinstance(chat_id, int) and isinstance(message_id, int):
        await try_delete_message(api, chat_id, message_id)
    patch_settings(group, prompt_chat_id=None, prompt_message_id=None)


async def resolve_archive_chat_id(session: AsyncSession, slug: str) -> int | None:
    """Return the private archive chat bound to ``slug``, if any."""
    groups = GroupRepository(session)
    from_group = await groups.archive_chat_id_for_slug(slug)
    if from_group is not None:
        return from_group
    stored = await AppSettingsRepository(session).get(archive_setting_key(slug))
    if stored is None:
        return None
    try:
        return int(stored)
    except (TypeError, ValueError):
        return None
