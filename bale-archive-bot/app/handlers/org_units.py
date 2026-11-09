"""Organisational unit picker shared by /register and the panel's group screen.

OrgUnits has ~14,000 rows, so instead of pages of every unit the picker offers:
🔎 search (typed as a Reply), 🌳 tree browsing, 💡 suggestions from the group
title and 🕘 recently chosen units. Any choice first shows a confirm page with
the full path.

Picker arguments (ASCII, inside each host's callback_data)::

    m            menu                    f            ask for a search
    q:<page>     search results          n:<id>:<page> tree under unit id (0 = roots)
    s:<id>       confirm page            k:<id>       confirmed → the host saves it
    p            suggestions             r            recent
    b            back from the confirm page

The search words live in memory (PickerState), never in callback_data.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from app.bale.errors import BaleAPIError, NetworkError
from app.bale.keyboards import button, keyboard
from app.bale.models import InlineKeyboardButton, Message
from app.core.context import BotContext
from app.db import repo
from app.domain.org_units import MIN_QUERY_CHARS, OrgUnitIndex, Unit, normalize, same_name_count
from app.i18n import fa
from app.observability.logging import get_logger

logger = get_logger(__name__)

RESULTS_PER_PAGE = 10
TREE_PER_PAGE = 8
LABEL_MAX = 60
STATE_TTL_SECONDS = 30 * 60

HOST_REGISTER = "reg"  # callback 1|ou|<group chat id>|<picker arg>
HOST_PANEL = "pan"  # callback 1|pa|gro|<BaleGroups.Id>:<picker arg>
ACT_REGISTER_UNIT = "ou"

Rows = list[list[InlineKeyboardButton]]
Make = Callable[[str, str], InlineKeyboardButton]


@dataclass
class PickerState:
    host: str
    sid: str
    chat_id: int
    user_id: int  # only this admin's Reply counts as a search
    title: str  # group title, for suggestions
    heading: str
    current: int | None = None  # unit shown with ✅
    message_id: int | None = None  # the picker message
    prompt_id: int | None = None  # «write part of the name» message
    query: str = ""
    back_to: str = "m"
    exit_row: list[InlineKeyboardButton] = field(default_factory=list)
    touched: float = field(default_factory=time.monotonic)


def host_button(host: str, sid: str, label: str, parg: str) -> InlineKeyboardButton:
    if host == HOST_REGISTER:
        return button(label, ACT_REGISTER_UNIT, sid, parg)
    return button(label, "pa", "gro", f"{sid}:{parg}")


# ─── State (program memory, 30 minutes) ───


def _prune(ctx: BotContext) -> None:
    now = time.monotonic()
    for key in [k for k, st in ctx.unit_pickers.items() if now - st.touched > STATE_TTL_SECONDS]:
        del ctx.unit_pickers[key]


def get_state(ctx: BotContext, host: str, sid: str, chat_id: int) -> PickerState | None:
    _prune(ctx)
    st = ctx.unit_pickers.get((host, sid, chat_id))
    if st is not None:
        st.touched = time.monotonic()
    return st


def open_state(ctx: BotContext, st: PickerState) -> PickerState:
    _prune(ctx)
    ctx.unit_pickers[(st.host, st.sid, st.chat_id)] = st
    return st


# ─── Labels ───


def result_label(index: OrgUnitIndex, unit: Unit, current: int | None = None) -> str:
    """«grandparent › parent › name (س۴)», ≤ 60 chars; the name stays whole, the path is cut."""
    mark = "✅ " if current == unit.id else ""
    suffix = f" (س{fa.fa_digits(unit.level_no)})"
    names = index.path_names(unit)[-3:]
    name = names[-1]
    prefix = "".join(f"{n} › " for n in names[:-1])
    room = LABEL_MAX - len(mark) - len(suffix) - len(name)
    if len(prefix) > room:
        prefix = "…" + prefix[len(prefix) - room + 1 :] if room > 1 else ""
    return f"{mark}{prefix}{name}{suffix}"


def full_path(index: OrgUnitIndex, unit: Unit) -> str:
    return " › ".join(index.path_names(unit))


def _tree_label(index: OrgUnitIndex, unit: Unit, current: int | None) -> str:
    mark = "✅ " if current == unit.id else ""
    count = index.child_count(unit.id)
    return f"{mark}{unit.name} ({fa.fa_digits(count)})" if count else f"{mark}{unit.name}"


# ─── Views ───


async def view(ctx: BotContext, st: PickerState, parg: str) -> tuple[str, Rows]:
    """Text and buttons for one picker screen (everything except ``f`` and ``k``)."""
    index = await ctx.org_units.get(ctx.db)
    kind, _, rest = parg.partition(":")

    def b(label: str, target: str) -> InlineKeyboardButton:
        return host_button(st.host, st.sid, label, target)

    if kind == "b":
        return await view(ctx, st, st.back_to if st.back_to != "b" else "m")
    if kind == "s" and rest.isdigit():
        unit = index.get(int(rest))
        if unit is not None:
            body = fa.unit_confirm(full_path(index, unit), unit.level_no)
            return body, [[b(fa.BTN_UNIT_CONFIRM, f"k:{unit.id}")], [b(fa.BTN_UNIT_BACK, "b")]]
        kind = "m"
    if kind == "q" and st.query:
        st.back_to = parg
        return _search_view(index, st, _page(rest), b)
    if kind == "n":
        st.back_to = parg
        parent_part, _, page_part = rest.partition(":")
        parent = index.get(int(parent_part)) if parent_part.isdigit() else None
        return _tree_view(index, st, parent, _page(page_part), b)
    if kind == "p":
        units = index.suggest(st.title)
        if units:
            st.back_to = parg
            rows = [[b(result_label(index, u, st.current), f"s:{u.id}")] for u in units]
            return fa.UNIT_SUGGEST_TITLE, [*rows, [b(fa.BTN_UNIT_BACK, "m")]]
    if kind == "r":
        units = await _recent(ctx, index)
        if units:
            st.back_to = parg
            rows = [[b(result_label(index, u, st.current), f"s:{u.id}")] for u in units]
            return fa.UNIT_RECENT_TITLE, [*rows, [b(fa.BTN_UNIT_BACK, "m")]]
    st.back_to = "m"
    first = [b(fa.BTN_UNIT_SEARCH, "f"), b(fa.BTN_UNIT_TREE, "n:0:1")]
    extra = []
    if index.suggest(st.title):
        extra.append(b(fa.BTN_UNIT_SUGGEST, "p"))
    if await _recent(ctx, index):
        extra.append(b(fa.BTN_UNIT_RECENT, "r"))
    rows = [first] + ([extra] if extra else [])
    if st.exit_row:
        rows.append(st.exit_row)
    heading = st.heading
    if st.current is not None and (unit := index.get(st.current)) is not None:
        heading += f"\n(فعلی: {full_path(index, unit)})"
    return heading, rows


def _page(raw: str) -> int:
    return max(1, int(raw)) if raw.isdigit() else 1


def _nav(page: int, pages: int, target: str, b: Make) -> list[InlineKeyboardButton]:
    make = b
    row: list[InlineKeyboardButton] = []
    if page < pages:
        row.append(make(fa.BTN_UNIT_NEXT, target.format(page + 1)))
    if page > 1:
        row.append(make(fa.BTN_UNIT_PREV, target.format(page - 1)))
    return row


def _search_view(index: OrgUnitIndex, st: PickerState, page: int, b: Make) -> tuple[str, Rows]:
    make = b
    hits = index.search(st.query)
    if not hits:
        body = f"🔎 «{st.query}»: {fa.UNIT_NOTHING_FOUND}"
        return body, [[make(fa.BTN_UNIT_SEARCH_AGAIN, "f")], [make(fa.BTN_UNIT_BACK, "m")]]
    pages = (len(hits) + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
    page = min(page, pages)
    chunk = hits[(page - 1) * RESULTS_PER_PAGE : page * RESULTS_PER_PAGE]
    crowded = len(hits) > RESULTS_PER_PAGE and same_name_count(hits) > 1
    body = fa.unit_search_results(st.query, len(hits), page, pages, crowded)
    rows: Rows = [
        [make(result_label(index, hit.unit, st.current), f"s:{hit.unit.id}")] for hit in chunk
    ]
    nav = _nav(page, pages, "q:{}", b)
    if nav:
        rows.append(nav)
    rows.append([make(fa.BTN_UNIT_SEARCH_AGAIN, "f"), make(fa.BTN_UNIT_BACK, "m")])
    return body, rows


def _tree_view(
    index: OrgUnitIndex, st: PickerState, parent: Unit | None, page: int, b: Make
) -> tuple[str, Rows]:
    make = b
    kids = index.children(parent.id if parent else None)
    pages = max(1, (len(kids) + TREE_PER_PAGE - 1) // TREE_PER_PAGE)
    page = min(page, pages)
    chunk = kids[(page - 1) * TREE_PER_PAGE : page * TREE_PER_PAGE]
    rows: Rows = []
    for kid in chunk:
        target = f"n:{kid.id}:1" if index.child_count(kid.id) else f"s:{kid.id}"
        rows.append([make(_tree_label(index, kid, st.current), target)])
    nav = _nav(page, pages, f"n:{parent.id if parent else 0}:{{}}", b)
    if nav:
        rows.append(nav)
    if parent is None:
        rows.append([make(fa.BTN_UNIT_BACK, "m")])
        return fa.UNIT_TREE_ROOTS, rows
    up = parent.parent_id if parent.parent_id is not None and index.get(parent.parent_id) else 0
    rows.append([make(fa.BTN_UNIT_PICK_THIS, f"s:{parent.id}")])
    rows.append([make(fa.BTN_UNIT_UP, f"n:{up}:1")])
    return fa.unit_tree_here(full_path(index, parent)), rows


async def _recent(ctx: BotContext, index: OrgUnitIndex) -> list[Unit]:
    async with ctx.db.tx() as conn:
        ids = await repo.recent_org_unit_ids(conn)
    return index.recent(ids)


# ─── Showing a screen ───


async def show(ctx: BotContext, st: PickerState, parg: str, message_id: int | None) -> None:
    """Edit the picker message in place (or send it when there is none)."""
    body, rows = await view(ctx, st, parg)
    markup = keyboard(rows)
    is_group = st.chat_id < 0
    try:
        if message_id is not None:
            st.message_id = await ctx.api.safe_edit(
                st.chat_id, message_id, body, markup, is_group=is_group
            )
        else:
            sent = await ctx.api.send_message(st.chat_id, body, markup, is_group=is_group)
            st.message_id = sent.message_id
    except (BaleAPIError, NetworkError) as exc:
        logger.info("unit_picker_show_failed", chat_id=st.chat_id, error=str(exc))


async def ask_search(ctx: BotContext, st: PickerState, message_id: int | None) -> None:
    """«Write part of the name» as a reply to the picker message."""
    if message_id is not None:
        st.message_id = message_id
    await _drop_prompt(ctx, st)
    try:
        sent = await ctx.api.send_message(
            st.chat_id,
            fa.UNIT_SEARCH_PROMPT,
            reply_to_message_id=st.message_id,
            is_group=st.chat_id < 0,
        )
        st.prompt_id = sent.message_id
    except (BaleAPIError, NetworkError) as exc:
        logger.info("unit_search_prompt_failed", chat_id=st.chat_id, error=str(exc))


async def handle_search_reply(ctx: BotContext, message: Message) -> bool:
    """A Reply to the search prompt. True = consumed (never archived, no wizard).

    Only the admin the picker belongs to counts; anyone else's reply is handled as usual.
    """
    target = message.reply_to_message
    if target is None or message.from_user is None:
        return False
    _prune(ctx)
    st = next(
        (
            s
            for s in ctx.unit_pickers.values()
            if s.chat_id == message.chat.id and s.prompt_id == target.message_id
        ),
        None,
    )
    if st is None:
        return False
    if message.from_user.id != st.user_id:
        logger.info("unit_search_reply_ignored", reason="other_user", chat_id=st.chat_id)
        return False
    st.touched = time.monotonic()
    query = " ".join((message.text or message.caption or "").split())
    if len(normalize(query).replace(" ", "")) < MIN_QUERY_CHARS:
        try:
            await ctx.api.send_message(
                st.chat_id,
                fa.UNIT_SEARCH_TOO_SHORT,
                reply_to_message_id=st.prompt_id,
                is_group=st.chat_id < 0,
            )
        except (BaleAPIError, NetworkError) as exc:
            logger.info("unit_search_notice_failed", error=str(exc))
        return True
    st.query = query[:100]
    logger.info("unit_search", chat_id=st.chat_id, length=len(st.query))
    if not message.is_private_message:
        await _try_delete(ctx, message.chat.id, message.message_id)
    await _drop_prompt(ctx, st)
    await show(ctx, st, "q:1", st.message_id)
    return True


async def _drop_prompt(ctx: BotContext, st: PickerState) -> None:
    if st.prompt_id is not None:
        await _try_delete(ctx, st.chat_id, st.prompt_id)
        st.prompt_id = None


async def _try_delete(ctx: BotContext, chat_id: int, message_id: int) -> None:
    try:
        await ctx.api.delete_message(chat_id, message_id)
    except (BaleAPIError, NetworkError) as exc:
        logger.info("delete_failed", chat_id=chat_id, message_id=message_id, error=str(exc))
