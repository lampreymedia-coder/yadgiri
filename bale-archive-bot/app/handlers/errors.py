"""Global error handling: nothing ever stops the main loop.

Every unhandled error is logged with the update_id and full traceback,
the user gets a calm Persian message, and the admin is alerted with a
per-error-kind throttle of one alert per five minutes.
"""

from __future__ import annotations

import time

from app.bale.errors import BaleAPIError, NetworkError
from app.bale.models import Update
from app.core.context import BotContext
from app.i18n import fa
from app.observability import metrics
from app.observability.logging import get_logger

logger = get_logger(__name__)

_ADMIN_ALERT_INTERVAL = 300.0


async def handle_update_error(ctx: BotContext, update: Update, error: Exception) -> None:
    """Log, notify user softly, alert admin (throttled). Never raises."""
    error_kind = type(error).__name__
    metrics.handler_errors.labels(where=update.kind).inc()
    logger.exception(
        "unhandled_update_error",
        update_id=update.update_id,
        update_kind=update.kind,
        error_kind=error_kind,
    )

    # Calm message to the user involved, best-effort.
    chat_id: int | None = None
    if update.message is not None:
        chat_id = update.message.chat.id
    elif update.callback_query is not None and update.callback_query.message is not None:
        chat_id = update.callback_query.message.chat.id
    if chat_id is not None:
        try:
            await ctx.api.send_message(chat_id, fa.ERR_GENERIC)
        except (BaleAPIError, NetworkError) as send_error:
            logger.warning("error_notice_send_failed", error=str(send_error))

    # Throttled admin alert: max one per error kind per 5 minutes.
    if ctx.settings.admin_chat_id is None:
        return
    now = time.monotonic()
    last = ctx.error_throttle.get(error_kind, 0.0)
    if now - last < _ADMIN_ALERT_INTERVAL:
        return
    ctx.error_throttle[error_kind] = now
    try:
        await ctx.api.send_message(ctx.settings.admin_chat_id, fa.admin_error_alert(error_kind))
    except (BaleAPIError, NetworkError) as send_error:
        logger.warning("admin_alert_send_failed", error=str(send_error))
