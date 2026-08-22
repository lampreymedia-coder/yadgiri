"""TTL sweeper: reminders at minute 10 and expiry handling at minute 30.

Expiry policy (EXPIRED_POLICY):
* republish — repost untagged into the group, mark expired (default);
* auto_tag  — save under the fallback tag;
* keep_draft — leave it pending and report to the admin.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.bale.errors import BaleAPIError, NetworkError
from app.config import ExpiredPolicy
from app.core.context import BotContext
from app.core.idempotency import purge_old_records
from app.db.models import Group, SubmissionStatus
from app.db.repositories.tags import TagRepository
from app.i18n import fa
from app.observability.logging import get_logger

logger = get_logger(__name__)


async def run_reminders_once(ctx: BotContext) -> int:
    """Send the minute-10 reminder for stale in-progress submissions."""
    sent = 0
    async with ctx.db.session() as session:
        service = ctx.submission_service(session)
        stale = await service.submissions.list_needing_reminder(
            timedelta(minutes=ctx.settings.reminder_after_minutes), datetime.now(UTC)
        )
        for submission in stale:
            submission.reminded_at = datetime.now(UTC)
            if submission.wizard_chat_id is None:
                continue
            try:
                await ctx.api.send_message(
                    submission.wizard_chat_id,
                    fa.reminder_message(submission.content_type.value),
                )
                sent += 1
            except (BaleAPIError, NetworkError) as exc:
                logger.info("reminder_send_failed", short_id=submission.short_id, error=str(exc))
    return sent


async def run_expiry_once(ctx: BotContext) -> int:
    """Apply EXPIRED_POLICY to submissions past their TTL."""
    handled = 0
    async with ctx.db.session() as session:
        service = ctx.submission_service(session)
        expired = await service.submissions.list_expired_in_progress(datetime.now(UTC))
        for submission in expired:
            handled += 1
            owner = await service.users.get_by_id(submission.user_id)
            group = await session.get(Group, submission.group_id) if submission.group_id else None
            sender = ""
            if owner is not None:
                sender = owner.display_name or owner.username or fa.fa_digits(owner.bale_user_id)

            policy = ctx.settings.expired_policy
            try:
                if policy is ExpiredPolicy.REPUBLISH:
                    await service.republish_without_tags(
                        submission, group, sender, SubmissionStatus.EXPIRED
                    )
                elif policy is ExpiredPolicy.AUTO_TAG:
                    tags = TagRepository(session)
                    slug, title, hashtag = fa.AUTO_TAG_FALLBACK
                    fallback = await tags.get_by_slug(slug)
                    if fallback is None:
                        fallback = await tags.create(slug, title, hashtag)
                    await service.submissions.set_tags(submission, [fallback.id])
                    if group is not None:
                        await service.complete_into_tag_archives(submission, sender)
                    else:
                        await service.submissions.set_status(submission, SubmissionStatus.COMPLETED)
                else:  # keep_draft (or republish without a known group)
                    submission.expires_at = datetime.now(UTC) + timedelta(
                        minutes=ctx.settings.submission_ttl_minutes
                    )
                    if ctx.settings.admin_chat_id is not None:
                        await service.outbox.enqueue(
                            "admin_notify",
                            ctx.settings.admin_chat_id,
                            {"text": fa.admin_intake_failure_alert(submission.short_id)},
                        )
                    continue
            except (BaleAPIError, NetworkError) as exc:
                logger.warning(
                    "expiry_handling_failed", short_id=submission.short_id, error=str(exc)
                )
                continue

            # Tell the user and close the wizard message.
            if submission.wizard_chat_id is not None and submission.wizard_message_id is not None:
                try:
                    await ctx.api.safe_edit(
                        submission.wizard_chat_id,
                        submission.wizard_message_id,
                        fa.expired_republished_message(submission.short_id),
                        None,
                    )
                except (BaleAPIError, NetworkError) as exc:
                    logger.info("expiry_notice_failed", error=str(exc))
    return handled


async def run_nightly_cleanup(ctx: BotContext) -> None:
    """Purge processed_updates older than 7 days."""
    async with ctx.db.session() as session:
        await purge_old_records(session, days=7)
