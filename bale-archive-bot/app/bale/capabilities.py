"""Runtime capability probing (spec section 2-14).

Never assume an API method exists — measure once at startup and let the
rest of the code branch with ``caps.has("answerCallbackQuery")``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.bale.errors import BadRequest, BaleAPIError, NetworkError, NotFound
from app.bale.methods import BaleAPI
from app.observability.logging import get_logger

logger = get_logger(__name__)

# Methods that can be probed harmlessly (bad params are fine — we only care
# whether the method itself is recognised, i.e. not a 404).
_PROBEABLE_METHODS: tuple[str, ...] = (
    "getMe",
    "getUpdates",
    "getWebhookInfo",
    "sendMessage",
    "editMessageText",
    "deleteMessage",
    "copyMessage",
    "forwardMessage",
    "getFile",
    "getChat",
    "getChatMembersCount",
    "answerCallbackQuery",
)


@dataclass
class Capabilities:
    """Result of startup probing; consulted instead of assumptions."""

    supported: dict[str, bool] = field(default_factory=dict)
    media_group_id_seen: bool = False
    probed: bool = False

    def has(self, method: str) -> bool:
        """True unless the probe positively determined the method is missing."""
        return self.supported.get(method, True)

    def mark(self, method: str, supported: bool) -> None:
        self.supported[method] = supported


async def probe_capabilities(api: BaleAPI) -> Capabilities:
    """Probe each method with harmless parameters and record support.

    A ``404`` (unknown method) marks the method unsupported; any other
    response — including parameter validation errors — proves the method
    exists. Network failures leave the method optimistically enabled.
    """
    caps = Capabilities()
    for method in _PROBEABLE_METHODS:
        try:
            if method == "getMe":
                await api.get_me()
            elif method == "getUpdates":
                await api.get_updates(offset=-1, limit=1)
            elif method == "getWebhookInfo":
                await api.get_webhook_info()
            else:
                # Intentionally invalid params: we expect 400, which proves
                # the method is routable. chat_id=0 never exists.
                await api.client.request(method, {"chat_id": 0}, max_attempts=1)
            caps.mark(method, True)
        except NotFound:
            caps.mark(method, False)
            logger.warning("capability_missing", method=method)
        except BadRequest:
            caps.mark(method, True)
        except (BaleAPIError, NetworkError) as exc:
            # Inconclusive: keep optimistic default but log it.
            logger.info("capability_probe_inconclusive", method=method, error=str(exc))
    caps.probed = True
    logger.info(
        "capabilities_probed",
        missing=[m for m, ok in caps.supported.items() if not ok],
    )
    return caps
