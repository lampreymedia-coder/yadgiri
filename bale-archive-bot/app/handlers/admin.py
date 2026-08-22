"""Admin panel: reports, tag management, export, settings and broadcast.

Access rule: only ``bale_user_id ∈ ADMIN_USER_IDS ∪ users.is_admin`` and
only in private chat or ADMIN_CHAT_ID. Everyone else receives the generic
"invalid command" reply (no information leak).
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Any

import jdatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.bale.errors import BaleAPIError, NetworkError
from app.bale.keyboards import button, keyboard, parse_callback
from app.bale.models import CallbackQuery, Message
from app.core.context import BotContext
from app.core.fsm import Conversation, WizardState
from app.db.models import ContentType, Group
from app.db.repositories.groups import GroupRepository
from app.db.repositories.misc import AppSettingsRepository, AuditRepository
from app.db.repositories.outbox import OutboxRepository
from app.db.repositories.submissions import SubmissionRepository
from app.db.repositories.tags import TagRepository
from app.db.repositories.users import UserRepository
from app.domain import reports
from app.domain.group_roles import (
    ROLE_ARCHIVE,
    ROLE_RESEARCH,
    archive_setting_key,
    delete_group_prompt,
    patch_settings,
    settings_of,
    tag_slug_of,
)
from app.domain.tags import make_hashtag, make_slug, unique_slug
from app.i18n import fa
from app.observability.logging import get_logger

logger = get_logger(__name__)

ADMIN_ACTIONS = {
    "ap",
    "adty",
    "adtn",
    "abcy",
    "abcn",
    "atgy",
    "atgn",
    "apg",
    "sar",
    "srg",
    "stg",
    "srb",
}

_PAGE_SIZE = 10


async def is_admin(ctx: BotContext, session: AsyncSession, bale_user_id: int) -> bool:
    if ctx.is_runtime_admin(bale_user_id):
        return True
    users = UserRepository(session)
    user = await users.get_by_bale_id(bale_user_id)
    return bool(user is not None and user.is_admin)


async def promote_first_owner(
    ctx: BotContext, session: AsyncSession, from_user: object | None
) -> bool:
    """If nobody is admin yet, make this Bale user the owner.

    Returns True when this user was just promoted.
    """
    if from_user is None:
        return False
    bale_user_id = getattr(from_user, "id", None)
    if not isinstance(bale_user_id, int):
        return False
    users = UserRepository(session)
    existing_admins = await users.list_admins()
    if existing_admins or ctx.runtime_admin_ids:
        return False
    username = getattr(from_user, "username", None)
    first_name = getattr(from_user, "first_name", None)
    last_name = getattr(from_user, "last_name", None)
    user = await users.upsert_from_bale(
        bale_user_id,
        username if isinstance(username, str) else None,
        first_name if isinstance(first_name, str) else None,
        last_name if isinstance(last_name, str) else None,
    )
    await users.set_admin(user.id, True)
    ctx.runtime_admin_ids.add(bale_user_id)
    if ctx.admin_notify_chat_id is None:
        ctx.admin_notify_chat_id = bale_user_id
    settings_repo = AppSettingsRepository(session)
    await settings_repo.set("owner_user_id", bale_user_id)
    await settings_repo.set("admin_notify_chat_id", bale_user_id)
    await session.flush()
    logger.info("first_owner_promoted", user_id=bale_user_id)
    return True


def admin_chat_allowed(ctx: BotContext, message: Message) -> bool:
    if message.chat.type == "private":
        return True
    return ctx.settings.admin_chat_id is not None and message.chat.id == ctx.settings.admin_chat_id


# ─── Date range parsing (Jalali aware) ───


def _parse_jalali(date_str: str) -> datetime | None:
    normalized = date_str.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    try:
        parts = [int(p) for p in normalized.split("/")]
        jd = jdatetime.date(parts[0], parts[1], parts[2])
        gd = jd.togregorian()
        return datetime(gd.year, gd.month, gd.day, tzinfo=UTC)
    except (ValueError, IndexError):
        return None


def parse_range(args: list[str]) -> tuple[datetime | None, datetime | None, str]:
    """Parse [today|week|month|all|from:۱۴۰۵/۰۵/۰۱ to:۱۴۰۵/۰۵/۳۰] arguments."""
    now = datetime.now(UTC)
    from_ts: datetime | None = None
    to_ts: datetime | None = None
    label = fa.range_label("all")
    for arg in args:
        lowered = arg.lower()
        if lowered == "today":
            from_ts, label = now - timedelta(days=1), fa.range_label("today")
        elif lowered == "week":
            from_ts, label = now - timedelta(days=7), fa.range_label("week")
        elif lowered == "month":
            from_ts, label = now - timedelta(days=30), fa.range_label("month")
        elif lowered == "all":
            from_ts, to_ts, label = None, None, fa.range_label("all")
        elif lowered.startswith("from:"):
            parsed = _parse_jalali(arg[5:])
            if parsed is not None:
                from_ts = parsed
                label = fa.fa_digits(arg[5:])
        elif lowered.startswith("to:"):
            parsed = _parse_jalali(arg[3:])
            if parsed is not None:
                to_ts = parsed + timedelta(days=1)
                label = fa.range_between(label, arg[3:])
    return from_ts, to_ts, label


# ─── Reports ───


async def send_stats(ctx: BotContext, session: AsyncSession, chat_id: int, args: list[str]) -> None:
    from_ts, to_ts, label = parse_range(args)
    service = reports.ReportService(session)
    overall = await service.overall(from_ts, to_ts)
    tag_stats = await service.top_tags(from_ts, to_ts)
    user_stats = await service.top_users(from_ts, to_ts, limit=5)
    matrix = await service.type_matrix()

    tag_lines = [
        fa.bar_line(
            fa.tag_title_with_state(t.title_fa, t.is_active),
            t.items,
            t.share_pct,
            reports.text_bar(t.share_pct / 100.0),
        )
        for t in tag_stats
        if t.items > 0
    ]
    type_totals: dict[str, int] = {}
    for row in matrix:
        type_totals["text"] = type_totals.get("text", 0) + row.text_count
        type_totals["image"] = type_totals.get("image", 0) + row.image_count
        type_totals["document"] = type_totals.get("document", 0) + row.document_count
        type_totals["audio"] = type_totals.get("audio", 0) + row.audio_count
        type_totals["video"] = type_totals.get("video", 0) + row.video_count
    type_line = " · ".join(
        f"{fa.content_type_name(k)} {fa.fa_digits(v)}" for k, v in type_totals.items() if v
    )
    user_lines = [
        fa.ranked_user_line(i, u.display_name or u.username or str(u.bale_user_id), u.items)
        for i, u in enumerate(user_stats, start=1)
    ]
    text = fa.stats_report(
        range_text=label,
        total=overall.total,
        contributors=overall.contributors,
        total_bytes=overall.total_bytes,
        tag_lines=tag_lines,
        type_line=type_line,
        top_user_lines=user_lines,
    )
    await ctx.api.send_message(chat_id, text)


async def send_top_users(
    ctx: BotContext, session: AsyncSession, chat_id: int, args: list[str]
) -> None:
    limit = 10
    numeric = [a for a in args if a.isdigit()]
    if numeric:
        limit = max(1, min(int(numeric[0]), 50))
    from_ts, to_ts, label = parse_range(args)
    service = reports.ReportService(session)
    stats = await service.top_users(from_ts, to_ts, limit=limit)
    lines = [f"{fa.TOP_USERS_HEADER} ({label})", fa.REPORT_DIVIDER]
    lines.extend(
        fa.ranked_user_line(i, u.display_name or u.username or str(u.bale_user_id), u.items)
        for i, u in enumerate(stats, start=1)
    )
    await ctx.api.send_message(chat_id, "\n".join(lines))


async def send_top_tags(
    ctx: BotContext, session: AsyncSession, chat_id: int, args: list[str]
) -> None:
    from_ts, to_ts, label = parse_range(args)
    service = reports.ReportService(session)
    stats = await service.top_tags(from_ts, to_ts)
    lines = [f"{fa.TOP_TAGS_HEADER} ({label})", fa.REPORT_DIVIDER]
    lines.extend(
        fa.top_tag_line(
            i,
            fa.tag_title_with_state(t.title_fa, t.is_active),
            t.hashtag,
            t.items,
            t.contributors,
            t.share_pct,
        )
        for i, t in enumerate(stats, start=1)
    )
    await ctx.api.send_message(chat_id, "\n".join(lines))


async def send_tag_browse(
    ctx: BotContext, session: AsyncSession, chat_id: int, args: list[str]
) -> None:
    if not args:
        await ctx.api.send_message(chat_id, fa.TAG_BROWSE_USAGE)
        return
    slug = args[0]
    page = int(args[1]) if len(args) > 1 and args[1].isdigit() else 1
    tags = TagRepository(session)
    tag = await tags.get_by_slug(slug)
    if tag is None:
        await ctx.api.send_message(chat_id, fa.TAG_NOT_FOUND)
        return
    submissions = SubmissionRepository(session)
    items, total = await submissions.paginate_by_tag(tag.id, page, _PAGE_SIZE)
    total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    lines = [fa.tag_line(tag.title_fa, tag.hashtag, tag.slug, tag.is_active, total)]
    lines.extend(
        fa.my_item_line(
            s.short_id, s.content_type.value, fa.status_name(s.status.value), s.created_at
        )
        for s in items
    )
    rows = []
    nav = []
    if page > 1:
        nav.append(button("◀️", "apg", "", f"{slug}:{page - 1}"))
    if page < total_pages:
        nav.append(button("▶️", "apg", "", f"{slug}:{page + 1}"))
    if nav:
        rows.append(nav)
    await ctx.api.send_message(chat_id, "\n".join(lines), keyboard(rows) if rows else None)


async def send_type_report(
    ctx: BotContext, session: AsyncSession, chat_id: int, args: list[str]
) -> None:
    if not args:
        await ctx.api.send_message(chat_id, fa.TYPE_USAGE)
        return
    reverse_names = {v: k for k, v in fa.CONTENT_TYPE_NAMES.items()}
    requested = reverse_names.get(args[0], args[0])
    valid = {ct.value for ct in ContentType}
    if requested not in valid:
        await ctx.api.send_message(chat_id, fa.TYPE_USAGE)
        return
    service = reports.ReportService(session)
    matrix = await service.type_matrix()
    lines = [fa.TYPE_MATRIX_HEADER, fa.REPORT_DIVIDER]
    for row in matrix:
        lines.append(
            f"{row.title_fa}: "
            f"{fa.content_type_name('text')} {fa.fa_digits(row.text_count)} · "
            f"{fa.content_type_name('link')} {fa.fa_digits(row.link_count)} · "
            f"{fa.content_type_name('image')} {fa.fa_digits(row.image_count)} · "
            f"{fa.content_type_name('video')} {fa.fa_digits(row.video_count)} · "
            f"{fa.content_type_name('audio')} {fa.fa_digits(row.audio_count)} · "
            f"{fa.content_type_name('document')} {fa.fa_digits(row.document_count)} — "
            + fa.matrix_row_total(row.total)
        )
    await ctx.api.send_message(chat_id, "\n".join(lines))


async def send_user_report(
    ctx: BotContext, session: AsyncSession, chat_id: int, args: list[str]
) -> None:
    if not args:
        await ctx.api.send_message(chat_id, fa.USER_USAGE)
        return
    users = UserRepository(session)
    ident = args[0]
    user = None
    if ident.startswith("@"):
        user = await users.get_by_username(ident)
    elif ident.isdigit():
        user = await users.get_by_bale_id(int(ident))
    if user is None:
        await ctx.api.send_message(chat_id, fa.USER_NOT_FOUND)
        return
    submissions = SubmissionRepository(session)
    items = await submissions.list_recent_by_user(user.id, limit=15)
    lines = [
        fa.user_report_header(user.display_name or "", user.username, user.bale_user_id),
        fa.REPORT_DIVIDER,
    ]
    lines.extend(
        fa.my_item_line(
            s.short_id, s.content_type.value, fa.status_name(s.status.value), s.created_at
        )
        for s in items
    )
    await ctx.api.send_message(chat_id, "\n".join(lines))


async def send_search(
    ctx: BotContext, session: AsyncSession, chat_id: int, args: list[str]
) -> None:
    if not args:
        await ctx.api.send_message(chat_id, fa.SEARCH_USAGE)
        return
    query = " ".join(args)
    from app.domain.classify import normalize_fa

    service = reports.ReportService(session)
    use_trigram = session.bind is not None and session.bind.dialect.name == "postgresql"
    hits = await service.search(normalize_fa(query), use_trigram=use_trigram)
    if not hits:
        await ctx.api.send_message(chat_id, fa.SEARCH_EMPTY)
        return
    lines = [fa.SEARCH_HEADER]
    lines.extend(
        fa.search_result_line(h.short_id, h.content_type, h.snippet, h.completed_at) for h in hits
    )
    await ctx.api.send_message(chat_id, "\n".join(lines))


async def send_get(ctx: BotContext, session: AsyncSession, chat_id: int, args: list[str]) -> None:
    if not args:
        await ctx.api.send_message(chat_id, fa.GET_USAGE)
        return
    submissions = SubmissionRepository(session)
    submission = await submissions.get_by_short_id(args[0].strip().lower())
    if submission is None:
        await ctx.api.send_message(chat_id, fa.GET_NOT_FOUND)
        return
    if submission.archive_chat_id is None or submission.archive_message_id is None:
        await ctx.api.send_message(chat_id, fa.GET_NO_ARCHIVE)
        return
    try:
        await ctx.api.copy_message(
            chat_id, submission.archive_chat_id, submission.archive_message_id
        )
    except (BaleAPIError, NetworkError) as exc:
        logger.warning("get_copy_failed", error=str(exc))
        await ctx.api.send_message(chat_id, fa.ERR_SERVER)


async def send_health(ctx: BotContext, session: AsyncSession, chat_id: int) -> None:
    service = reports.ReportService(session)
    health = await service.health()
    await ctx.api.send_message(
        chat_id,
        fa.health_report(
            health.in_progress,
            health.failed,
            health.outbox_pending,
            health.media_backlog,
            health.last_update_id,
            health.db_size,
        ),
    )


async def send_export(
    ctx: BotContext, session: AsyncSession, chat_id: int, args: list[str]
) -> None:
    file_format = "xlsx"
    if args and args[0].lower() in ("csv", "xlsx"):
        file_format = args[0].lower()
        args = args[1:]
    from_ts, to_ts, _label = parse_range(args)
    await ctx.api.send_message(chat_id, fa.EXPORT_PREPARING)
    service = reports.ReportService(session)
    rows = await service.submissions_for_export(from_ts, to_ts)
    if not rows:
        await ctx.api.send_message(chat_id, fa.EXPORT_EMPTY)
        return
    headers = list(rows[0].keys())
    if file_format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([_cell(row[h]) for h in headers])
        data = buffer.getvalue().encode("utf-8-sig")
        file_name = "archive-export.csv"
    else:
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        assert sheet is not None
        sheet.append(headers)
        for row in rows:
            sheet.append([_cell(row[h]) for h in headers])
        stream = io.BytesIO()
        workbook.save(stream)
        data = stream.getvalue()
        file_name = "archive-export.xlsx"
    await ctx.api.send_document(chat_id, data, file_name=file_name)


def _cell(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


# ─── Tag management ───


async def send_tags_list(ctx: BotContext, session: AsyncSession, chat_id: int) -> None:
    tags = TagRepository(session)
    all_tags = await tags.list_all()
    lines = [fa.TAGS_HEADER]
    lines.extend(fa.tag_line(t.title_fa, t.hashtag, t.slug, t.is_active) for t in all_tags)
    await ctx.api.send_message(chat_id, "\n".join(lines))


async def start_addtag_flow(ctx: BotContext, session: AsyncSession, message: Message) -> None:
    assert message.from_user is not None
    conversation = Conversation(chat_id=message.chat.id, user_id=message.from_user.id)
    conversation.state = WizardState.ADMIN_INPUT
    conversation.payload = {"flow": "addtag", "step": "title", "draft": {}}
    await ctx.state_store(session).save(conversation, 30)
    await ctx.api.send_message(message.chat.id, fa.ADDTAG_PROMPT_TITLE)


async def handle_admin_input(
    ctx: BotContext, session: AsyncSession, message: Message, conversation: Conversation
) -> None:
    """Text input steps for admin flows (/addtag wizard, /broadcast text)."""
    flow = str(conversation.payload.get("flow", ""))
    text_value = (message.text or "").strip()
    store = ctx.state_store(session)

    if flow == "addtag":
        draft: dict[str, Any] = dict(conversation.payload.get("draft", {}))
        step = str(conversation.payload.get("step", "title"))
        if step == "title":
            draft["title_fa"] = text_value
            conversation.payload.update({"step": "emoji", "draft": draft})
            await store.save(conversation, 30)
            await ctx.api.send_message(message.chat.id, fa.ADDTAG_PROMPT_EMOJI)
            return
        if step == "emoji":
            draft["emoji"] = None if text_value == "-" else text_value
            conversation.payload.update({"step": "desc", "draft": draft})
            await store.save(conversation, 30)
            await ctx.api.send_message(message.chat.id, fa.ADDTAG_PROMPT_DESC)
            return
        if step == "desc":
            draft["description"] = None if text_value == "-" else text_value
            title = str(draft.get("title_fa", ""))
            tags = TagRepository(session)
            existing_slugs = {t.slug for t in await tags.list_all()}
            slug = unique_slug(make_slug(title), existing_slugs)
            hashtag = make_hashtag(title)
            if await tags.get_by_hashtag(hashtag) is not None:
                await ctx.api.send_message(message.chat.id, fa.ADDTAG_DUPLICATE)
                conversation.state = WizardState.IDLE
                await store.clear(conversation.chat_id, conversation.user_id)
                return
            draft["slug"] = slug
            draft["hashtag"] = hashtag
            conversation.payload.update({"step": "confirm", "draft": draft})
            await store.save(conversation, 30)
            rows = [
                [button(fa.BTN_YES, "atgy"), button(fa.BTN_NO, "atgn")],
            ]
            await ctx.api.send_message(
                message.chat.id, fa.addtag_preview(title, hashtag, slug), keyboard(rows)
            )
            return

    if flow == "broadcast":
        conversation.payload.update({"text": text_value, "step": "confirm"})
        await store.save(conversation, 30)
        groups = GroupRepository(session)
        count = len(await groups.list_active())
        rows = [[button(fa.BTN_YES, "abcy"), button(fa.BTN_NO, "abcn")]]
        await ctx.api.send_message(message.chat.id, fa.broadcast_confirm(count), keyboard(rows))
        return

    conversation.state = WizardState.IDLE
    await store.clear(conversation.chat_id, conversation.user_id)


async def handle_edittag(
    ctx: BotContext, session: AsyncSession, chat_id: int, args: list[str], actor: int
) -> None:
    if len(args) < 2:
        await ctx.api.send_message(chat_id, fa.TAG_EDIT_USAGE)
        return
    tags = TagRepository(session)
    tag = await tags.get_by_slug(args[0])
    if tag is None:
        await ctx.api.send_message(chat_id, fa.TAG_NOT_FOUND)
        return
    new_title = " ".join(args[1:])
    await tags.update_fields(tag.id, title_fa=new_title)
    audit = AuditRepository(session)
    await audit.record("tag_edited", actor, "tag", str(tag.id), {"title_fa": new_title})
    await ctx.api.send_message(chat_id, fa.TAG_EDIT_DONE)


async def handle_disabletag(
    ctx: BotContext, session: AsyncSession, chat_id: int, args: list[str]
) -> None:
    if not args:
        await ctx.api.send_message(chat_id, fa.TAG_NOT_FOUND)
        return
    tags = TagRepository(session)
    tag = await tags.get_by_slug(args[0])
    if tag is None:
        await ctx.api.send_message(chat_id, fa.TAG_NOT_FOUND)
        return
    # Two-step confirmation.
    rows = [[button(fa.BTN_YES, "adty", "", tag.slug), button(fa.BTN_NO, "adtn")]]
    await ctx.api.send_message(
        chat_id,
        fa.tag_line(tag.title_fa, tag.hashtag, tag.slug, tag.is_active)
        + "\n\n"
        + fa.TAG_CONFIRM_DISABLE,
        keyboard(rows),
    )


async def handle_reordertags(
    ctx: BotContext, session: AsyncSession, chat_id: int, args: list[str], actor: int
) -> None:
    if not args:
        await ctx.api.send_message(chat_id, fa.TAG_REORDER_USAGE)
        return
    tags = TagRepository(session)
    await tags.reorder(args)
    audit = AuditRepository(session)
    await audit.record("tags_reordered", actor, "tag", None, {"order": args})
    await ctx.api.send_message(chat_id, fa.TAG_REORDER_DONE)


# ─── Groups / settings / broadcast / forget / onboard ───


async def send_groups(ctx: BotContext, session: AsyncSession, chat_id: int) -> None:
    groups = GroupRepository(session)
    all_groups = await groups.list_active()
    lines = [fa.GROUPS_HEADER]
    for group in all_groups:
        role_value = settings_of(group).get("role")
        lines.append(
            fa.group_line(
                group.title,
                group.bale_chat_id,
                group.is_active,
                group.bot_can_delete,
                role=role_value if isinstance(role_value, str) else None,
                tag=tag_slug_of(group),
            )
        )
    await ctx.api.send_message(chat_id, "\n".join(lines))


async def handle_settings(
    ctx: BotContext, session: AsyncSession, chat_id: int, args: list[str], actor: int
) -> None:
    settings_repo = AppSettingsRepository(session)
    if len(args) >= 2:
        key, value = args[0], " ".join(args[1:])
        await settings_repo.set(key, value, actor)
        audit = AuditRepository(session)
        await audit.record("setting_changed", actor, "setting", key, {"value": value})
        await ctx.api.send_message(chat_id, fa.SETTINGS_UPDATED)
        return
    current = await settings_repo.all()
    lines = [fa.SETTINGS_HEADER]
    lines.extend(f"• {key} = {value}" for key, value in current.items())
    lines.append(fa.SETTINGS_USAGE)
    await ctx.api.send_message(chat_id, "\n".join(lines))


async def start_broadcast_flow(ctx: BotContext, session: AsyncSession, message: Message) -> None:
    assert message.from_user is not None
    conversation = Conversation(chat_id=message.chat.id, user_id=message.from_user.id)
    conversation.state = WizardState.ADMIN_INPUT
    conversation.payload = {"flow": "broadcast", "step": "text"}
    await ctx.state_store(session).save(conversation, 30)
    await ctx.api.send_message(message.chat.id, fa.BROADCAST_PROMPT)


async def handle_forget(
    ctx: BotContext, session: AsyncSession, chat_id: int, args: list[str], actor: int
) -> None:
    if not args or not args[0].isdigit():
        await ctx.api.send_message(chat_id, fa.FORGET_USAGE)
        return
    users = UserRepository(session)
    user = await users.get_by_bale_id(int(args[0]))
    if user is None:
        await ctx.api.send_message(chat_id, fa.USER_NOT_FOUND)
        return
    await users.forget(user.id)
    audit = AuditRepository(session)
    await audit.record("user_forgotten", actor, "user", str(user.id), {})
    await ctx.api.send_message(chat_id, fa.FORGET_DONE)


async def persist_archive_chat(
    ctx: BotContext,
    session: AsyncSession,
    chat_id: int,
    *,
    slug: str | None = None,
    title: str | None = None,
) -> None:
    ctx.archive_chat_id = chat_id
    settings_repo = AppSettingsRepository(session)
    await settings_repo.set("archive_chat_id", chat_id)
    if slug:
        await settings_repo.set(archive_setting_key(slug), chat_id)
    groups = GroupRepository(session)
    group = await groups.upsert(chat_id, title, "group")
    await groups.set_active(group.id, True)
    changes: dict[str, Any] = {"role": ROLE_ARCHIVE, "role_asked": True}
    if slug:
        changes["tag_slug"] = slug
    patch_settings(group, **changes)
    audit = AuditRepository(session)
    await audit.record(
        "archive_chat_set", None, "group", str(chat_id), {"slug": slug} if slug else {}
    )


async def persist_research_chat(
    session: AsyncSession, chat_id: int, *, title: str | None = None
) -> Group:
    groups = GroupRepository(session)
    group = await groups.upsert(chat_id, title, "group")
    await groups.set_active(group.id, True)
    patch_settings(group, role=ROLE_RESEARCH, role_asked=True, tag_slug=None)
    return group


async def _send_archive_tag_picker(
    ctx: BotContext, session: AsyncSession, user_id: int, group_chat_id: int, group_title: str
) -> None:
    from app.handlers.group_intake import archive_tag_keyboard

    tags = await TagRepository(session).list_active()
    labels = [(tag.slug, f"{tag.hashtag}  {tag.title_fa}") for tag in tags]
    await ctx.api.send_message(
        user_id,
        fa.archive_tag_prompt(group_title),
        archive_tag_keyboard(group_chat_id, labels),
    )


async def handle_set_archive(ctx: BotContext, session: AsyncSession, message: Message) -> None:
    """Ask privately which hashtag this group archives. No bot message stays in-group."""
    assert message.from_user is not None
    groups = GroupRepository(session)
    group = await groups.upsert(message.chat.id, message.chat.title, message.chat.type)
    await groups.set_active(group.id, True)
    title = message.chat.title or group.title or fa.fa_digits(message.chat.id)
    try:
        await _send_archive_tag_picker(ctx, session, message.from_user.id, message.chat.id, title)
        return
    except (BaleAPIError, NetworkError) as exc:
        logger.warning("archive_picker_dm_failed", error=str(exc))
    try:
        sent = await ctx.api.send_message(
            message.chat.id, fa.group_role_private_hint(ctx.bot_username), is_group=True
        )
        patch_settings(group, prompt_chat_id=message.chat.id, prompt_message_id=sent.message_id)
    except (BaleAPIError, NetworkError) as exc:
        logger.warning("archive_picker_hint_failed", error=str(exc))


async def handle_onboard(ctx: BotContext, message: Message) -> None:
    """Admin command in a group: pin the getting-started message."""
    text = fa.onboard_message(ctx.bot_username)
    sent = await ctx.api.send_message(message.chat.id, text, is_group=True)
    try:
        await ctx.api.pin_chat_message(message.chat.id, sent.message_id)
        await ctx.api.send_message(message.chat.id, fa.ONBOARD_PINNED, is_group=True)
    except (BaleAPIError, NetworkError) as exc:
        logger.warning("onboard_pin_failed", error=str(exc))
        await ctx.api.send_message(message.chat.id, fa.ONBOARD_PIN_FAILED, is_group=True)


# ─── Panel ───


async def send_panel(ctx: BotContext, chat_id: int) -> None:
    rows = [
        [
            button(fa.BTN_PANEL_STATS, "ap", "", "stats"),
            button(fa.BTN_PANEL_TOP_USERS, "ap", "", "users"),
        ],
        [
            button(fa.BTN_PANEL_TOP_TAGS, "ap", "", "toptags"),
            button(fa.BTN_PANEL_TAGS, "ap", "", "tags"),
        ],
        [
            button(fa.BTN_PANEL_GROUPS, "ap", "", "groups"),
            button(fa.BTN_PANEL_HEALTH, "ap", "", "health"),
        ],
        [
            button(fa.BTN_PANEL_SETTINGS, "ap", "", "settings"),
            button(fa.BTN_PANEL_EXPORT, "ap", "", "export"),
        ],
    ]
    await ctx.api.send_message(chat_id, fa.PANEL_HEADER, keyboard(rows))


async def handle_admin_callback(ctx: BotContext, session: AsyncSession, cq: CallbackQuery) -> None:
    data = parse_callback(cq.data or "")
    if not await is_admin(ctx, session, cq.from_user.id):
        if ctx.caps.has("answerCallbackQuery"):
            try:
                await ctx.api.answer_callback_query(cq.id, fa.ERR_NOT_YOURS)
            except (BaleAPIError, NetworkError) as exc:
                logger.info("admin_denied_answer_failed", error=str(exc))
        return
    chat_id = cq.message.chat.id if cq.message is not None else cq.from_user.id

    if data.action == "ap":
        if data.arg == "stats":
            await send_stats(ctx, session, chat_id, [])
        elif data.arg == "users":
            await send_top_users(ctx, session, chat_id, [])
        elif data.arg == "toptags":
            await send_top_tags(ctx, session, chat_id, [])
        elif data.arg == "tags":
            await send_tags_list(ctx, session, chat_id)
        elif data.arg == "groups":
            await send_groups(ctx, session, chat_id)
        elif data.arg == "health":
            await send_health(ctx, session, chat_id)
        elif data.arg == "settings":
            await handle_settings(ctx, session, chat_id, [], cq.from_user.id)
        elif data.arg == "export":
            await send_export(ctx, session, chat_id, [])
    elif data.action == "apg":
        slug, _, page = data.arg.partition(":")
        await send_tag_browse(ctx, session, chat_id, [slug, page or "1"])
    elif data.action == "adty":
        tags = TagRepository(session)
        tag = await tags.get_by_slug(data.arg)
        if tag is not None:
            await tags.set_active(tag.id, False)
            audit = AuditRepository(session)
            await audit.record("tag_disabled", cq.from_user.id, "tag", str(tag.id), {})
            await ctx.api.send_message(chat_id, fa.TAG_DISABLED_DONE)
        else:
            await ctx.api.send_message(chat_id, fa.TAG_NOT_FOUND)
    elif data.action == "adtn":
        await ctx.api.send_message(chat_id, fa.BROADCAST_CANCELLED)
    elif data.action in ("atgy", "atgn", "abcy", "abcn"):
        await _handle_flow_confirm(ctx, session, cq, data.action, chat_id)
    elif data.action == "sar":
        try:
            archive_id = int(data.arg)
        except ValueError:
            await ctx.api.send_message(cq.from_user.id, fa.ERR_GENERIC)
        else:
            groups = GroupRepository(session)
            group = await groups.upsert(archive_id, None, "group")
            title = group.title or fa.fa_digits(archive_id)
            await delete_group_prompt(ctx.api, group)
            if cq.message is not None and cq.message.is_group_message:
                try:
                    await ctx.api.delete_message(cq.message.chat.id, cq.message.message_id)
                except (BaleAPIError, NetworkError) as exc:
                    logger.info("archive_prompt_delete_failed", error=str(exc))
            try:
                await _send_archive_tag_picker(ctx, session, cq.from_user.id, archive_id, title)
            except (BaleAPIError, NetworkError) as exc:
                logger.warning("archive_tag_picker_failed", error=str(exc))
                await ctx.api.send_message(cq.from_user.id, fa.ERR_GENERIC)
    elif data.action == "srb":
        try:
            group_chat_id = int(data.arg)
        except ValueError:
            await ctx.api.send_message(cq.from_user.id, fa.ERR_GENERIC)
        else:
            from app.handlers.group_intake import role_keyboard

            groups = GroupRepository(session)
            group = await groups.get_by_bale_id(group_chat_id)
            title = (group.title if group else None) or fa.fa_digits(group_chat_id)
            await ctx.api.send_message(
                cq.from_user.id, fa.bot_added_ask_role(title), role_keyboard(group_chat_id)
            )
    elif data.action == "stg":
        slug = data.arg
        try:
            archive_id = int(data.sid)
        except ValueError:
            await ctx.api.send_message(cq.from_user.id, fa.ERR_GENERIC)
        else:
            tags = TagRepository(session)
            tag = await tags.get_by_slug(slug)
            groups = GroupRepository(session)
            group = await groups.upsert(archive_id, None, "group")
            await persist_archive_chat(ctx, session, archive_id, slug=slug, title=group.title)
            await delete_group_prompt(ctx.api, group)
            hashtag = tag.hashtag if tag is not None else f"#{slug}"
            title = group.title or fa.fa_digits(archive_id)
            await ctx.api.send_message(cq.from_user.id, fa.archive_set_done(title, hashtag))
    elif data.action == "srg":
        try:
            group_chat_id = int(data.arg)
        except ValueError:
            await ctx.api.send_message(cq.from_user.id, fa.ERR_GENERIC)
        else:
            group = await persist_research_chat(session, group_chat_id)
            await delete_group_prompt(ctx.api, group)
            if cq.message is not None and cq.message.is_group_message:
                try:
                    await ctx.api.delete_message(cq.message.chat.id, cq.message.message_id)
                except (BaleAPIError, NetworkError) as exc:
                    logger.info("research_prompt_delete_failed", error=str(exc))
            title = group.title or fa.fa_digits(group_chat_id)
            await ctx.api.send_message(cq.from_user.id, fa.research_set_done(title))

    if ctx.caps.has("answerCallbackQuery"):
        try:
            await ctx.api.answer_callback_query(cq.id)
        except (BaleAPIError, NetworkError) as exc:
            logger.info("admin_answer_callback_failed", error=str(exc))


async def _handle_flow_confirm(
    ctx: BotContext, session: AsyncSession, cq: CallbackQuery, action: str, chat_id: int
) -> None:
    store = ctx.state_store(session)
    conversation = await store.load(chat_id, cq.from_user.id)
    if conversation is None:
        await ctx.api.send_message(chat_id, fa.ERR_EXPIRED)
        return

    if action == "atgy" and conversation.payload.get("flow") == "addtag":
        draft: dict[str, Any] = dict(conversation.payload.get("draft", {}))
        tags = TagRepository(session)
        users = UserRepository(session)
        actor = await users.get_by_bale_id(cq.from_user.id)
        tag = await tags.create(
            slug=str(draft["slug"]),
            title_fa=str(draft["title_fa"]),
            hashtag=str(draft["hashtag"]),
            description=draft.get("description"),
            emoji=draft.get("emoji"),
            created_by=actor.id if actor else None,
        )
        audit = AuditRepository(session)
        await audit.record("tag_created", cq.from_user.id, "tag", str(tag.id), {"slug": tag.slug})
        await ctx.api.send_message(chat_id, fa.ADDTAG_DONE)
    elif action == "abcy" and conversation.payload.get("flow") == "broadcast":
        text_value = str(conversation.payload.get("text", ""))
        groups = GroupRepository(session)
        outbox = OutboxRepository(session)
        for group in await groups.list_active():
            await outbox.enqueue("broadcast", group.bale_chat_id, {"text": text_value})
        audit = AuditRepository(session)
        await audit.record("broadcast_sent", cq.from_user.id, None, None, {"text": text_value})
        await ctx.api.send_message(chat_id, fa.BROADCAST_SENT)
    else:
        await ctx.api.send_message(chat_id, fa.BROADCAST_CANCELLED)

    await store.clear(chat_id, cq.from_user.id)
