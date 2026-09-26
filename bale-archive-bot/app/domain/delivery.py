"""Detect when Bale withholds ordinary group messages from an admin bot.

Live groups show a consistent pattern: ordinary text and forwards arrive in
groups that still have regular (non-admin) members. Groups where nearly every
member is an administrator deliver join/service events and @mentions, but not
plain content. The HTTP API has no `can_read_all_group_messages` flag, so we
infer the risk from member/admin counts and tell the user instead of staying
silent.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.bale.errors import BaleAPIError, NetworkError
from app.bale.methods import BaleAPI
from app.observability.logging import get_logger

logger = get_logger(__name__)

# Small groups (bot + owner + one member) are allowed to have two admins.
# Larger groups that were created as "everyone is admin" need more than one
# ordinary member before Bale starts delivering unmentioned texts.
_ALMOST_ALL_MIN_MEMBERS = 5


@dataclass(frozen=True)
class ResearchDeliveryReport:
    chat_id: int
    member_count: int
    admin_count: int
    bot_is_admin: bool
    almost_all_admins: bool

    @property
    def at_risk(self) -> bool:
        return (not self.bot_is_admin) or self.almost_all_admins


def almost_all_administrators(member_count: int, admin_count: int) -> bool:
    """True when Bale is likely to hide ordinary group messages from the bot."""
    if member_count <= 0 or admin_count <= 0:
        return False
    if admin_count >= member_count:
        return True
    return member_count >= _ALMOST_ALL_MIN_MEMBERS and admin_count >= member_count - 1


async def inspect_research_delivery(
    api: BaleAPI, chat_id: int, bot_user_id: int
) -> ResearchDeliveryReport:
    """Read live member/admin counts. Never raises."""
    member_count = 0
    try:
        member_count = await api.get_chat_members_count(chat_id)
    except (BaleAPIError, NetworkError) as exc:
        logger.warning("delivery_member_count_failed", chat_id=chat_id, error=str(exc))

    admins: list[dict[str, object]] = []
    try:
        admins = await api.get_chat_administrators(chat_id)
    except (BaleAPIError, NetworkError) as exc:
        logger.warning("delivery_admin_list_failed", chat_id=chat_id, error=str(exc))
    admin_count = len(admins)

    bot_is_admin = any(
        _admin_user_id(item) == bot_user_id
        and str(item.get("status") or "").lower() in {"administrator", "creator"}
        for item in admins
    )
    if not bot_is_admin and bot_user_id:
        try:
            member = await api.get_chat_member(chat_id, bot_user_id)
        except (BaleAPIError, NetworkError) as exc:
            logger.warning("delivery_bot_status_failed", chat_id=chat_id, error=str(exc))
        else:
            bot_is_admin = str(member.get("status") or "").lower() in {
                "administrator",
                "creator",
            }

    report = ResearchDeliveryReport(
        chat_id=chat_id,
        member_count=member_count,
        admin_count=admin_count,
        bot_is_admin=bot_is_admin,
        almost_all_admins=almost_all_administrators(member_count, admin_count),
    )
    logger.info(
        "research_delivery_inspected",
        chat_id=chat_id,
        member_count=member_count,
        admin_count=admin_count,
        bot_is_admin=bot_is_admin,
        almost_all_admins=report.almost_all_admins,
    )
    return report


def _admin_user_id(item: dict[str, object]) -> int | None:
    user = item.get("user")
    if not isinstance(user, dict):
        return None
    raw = user.get("id")
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.lstrip("-").isdigit():
        return int(raw)
    return None
