"""Paged picker of active organisational units (OrgUnits), 8 per page."""

from __future__ import annotations

from collections.abc import Callable

from app.bale.models import InlineKeyboardButton
from app.db.repo import OrgUnitRow
from app.i18n import fa

PAGE_SIZE = 8


def page_count(units: list[OrgUnitRow]) -> int:
    return max(1, (len(units) + PAGE_SIZE - 1) // PAGE_SIZE)


def unit_rows(
    units: list[OrgUnitRow],
    page: int,
    pick: Callable[[OrgUnitRow], InlineKeyboardButton],
    turn: Callable[[int, str], InlineKeyboardButton],
    current: int | None = None,
) -> list[list[InlineKeyboardButton]]:
    """One unit per row (names can be long), then ◀️ n/m ▶️ when there are several pages."""
    pages = page_count(units)
    page = max(1, min(page, pages))
    chunk = units[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
    rows = [[pick(unit)] for unit in chunk]
    if pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 1:
            nav.append(turn(page - 1, "◀️"))
        nav.append(turn(page, f"{fa.fa_digits(page)}/{fa.fa_digits(pages)}"))
        if page < pages:
            nav.append(turn(page + 1, "▶️"))
        rows.append(nav)
    return rows


def unit_label(unit: OrgUnitRow, current: int | None = None) -> str:
    mark = "✅ " if current == unit.id else ""
    return f"{mark}{unit.name} (سطح {fa.fa_digits(unit.level_no)})"
