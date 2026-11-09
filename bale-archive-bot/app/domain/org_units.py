"""Organisational units (OrgUnits, ~14,000 rows) kept in memory for the picker.

One SELECT loads every unit; it is read again at most every 10 minutes, on use
(no background loop). Search, paths, the tree and suggestions all run on this
copy, never with LIKE on the database.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import Counter
from dataclasses import dataclass, field

from app.db import repo
from app.db.session import Database

REFRESH_SECONDS = 10 * 60
MAX_DEPTH = 10
MIN_QUERY_CHARS = 2

_CHAR_MAP = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "‌": None,  # ZWNJ (نیم‌فاصله)
        "‍": None,
        "ـ": None,  # tatweel
        **dict(zip("۰۱۲۳۴۵۶۷۸۹", "0123456789", strict=True)),
        **dict(zip("٠١٢٣٤٥٦٧٨٩", "0123456789", strict=True)),
    }
)
_DIACRITICS_RE = re.compile(r"[ً-ٰٟ]")
_SPACES_RE = re.compile(r"\s+")
_WORD_SPLIT_RE = re.compile(r"[^\w]+")

# Words that say nothing about which unit a group belongs to (title suggestions only).
SUGGEST_STOP_WORDS = frozenset({"نهاد", "برنامه", "رسته", "گروه", "و", "-", "ی"})


def normalize(value: str) -> str:
    """ي→ی, ك→ک, no ZWNJ or diacritics, one space, Latin digits, lower case."""
    out = _DIACRITICS_RE.sub("", value.translate(_CHAR_MAP))
    return _SPACES_RE.sub(" ", out).strip().lower()


def words(value: str) -> list[str]:
    return [w for w in _WORD_SPLIT_RE.split(normalize(value)) if w]


@dataclass(frozen=True, slots=True)
class Unit:
    id: int
    level_no: int
    name: str
    parent_id: int | None
    is_active: bool
    norm_name: str
    # Ancestors (root first) + the unit itself; stops at MAX_DEPTH or a loop.
    path_ids: tuple[int, ...]
    norm_path: str


@dataclass(frozen=True, slots=True)
class Hit:
    unit: Unit
    rank: int


class OrgUnitIndex:
    """An immutable snapshot of OrgUnits with lookups for the picker."""

    def __init__(self, nodes: list[repo.OrgUnitNode]) -> None:
        by_id = {node.id: node for node in nodes}
        norm = {node.id: normalize(node.name) for node in nodes}
        units: dict[int, Unit] = {}
        for node in nodes:
            chain = _chain(node.id, by_id)
            units[node.id] = Unit(
                id=node.id,
                level_no=node.level_no,
                name=node.name,
                parent_id=node.parent_id,
                is_active=node.is_active,
                norm_name=norm[node.id],
                path_ids=chain,
                norm_path=" ".join(norm[i] for i in chain),
            )
        self.units = units
        self.active = sorted(
            (u for u in units.values() if u.is_active), key=lambda u: (u.level_no, u.name, u.id)
        )
        self._children: dict[int | None, list[Unit]] = {}
        for unit in self.active:
            parent = unit.parent_id if unit.parent_id in units else None
            self._children.setdefault(parent, []).append(unit)
        for kids in self._children.values():
            kids.sort(key=lambda u: (u.name, u.id))

    def get(self, unit_id: int) -> Unit | None:
        unit = self.units.get(unit_id)
        return unit if unit is not None and unit.is_active else None

    def path_names(self, unit: Unit) -> list[str]:
        return [self.units[i].name for i in unit.path_ids]

    def children(self, parent_id: int | None) -> list[Unit]:
        """Active children; ``None`` = the roots (ParentId IS NULL)."""
        return self._children.get(parent_id, [])

    def child_count(self, unit_id: int) -> int:
        return len(self._children.get(unit_id, []))

    def search(self, query: str) -> list[Hit]:
        """Every word must appear in the unit's full path (ancestors + own name), and
        at least one in its own name, so «نگاشت کنترل بلوغ» finds the subsystem under
        نگاشت and not everything below it.

        Rank: exact name, name starts with the query, all words in the own name,
        then the rest; lower LevelNo first in each group.
        """
        norm_query = normalize(query)
        tokens = norm_query.split(" ")
        if len(norm_query.replace(" ", "")) < MIN_QUERY_CHARS:
            return []
        hits: list[Hit] = []
        for unit in self.active:
            path = unit.norm_path
            if not all(token in path for token in tokens):
                continue
            name = unit.norm_name
            if not any(token in name for token in tokens):
                continue
            if name == norm_query:
                rank = 0
            elif name.startswith(norm_query):
                rank = 1
            elif all(token in name for token in tokens):
                rank = 2
            else:
                rank = 3
            hits.append(Hit(unit, rank))
        hits.sort(key=lambda h: (h.rank, h.unit.level_no, h.unit.name, h.unit.id))
        return hits

    def suggest(self, group_title: str, limit: int = 3) -> list[Unit]:
        """Units sharing the most words with the group title (generic words dropped)."""
        wanted = {w for w in words(group_title) if w not in SUGGEST_STOP_WORDS}
        if not wanted:
            return []
        scored: list[tuple[int, Unit]] = []
        for unit in self.active:
            shared = len(wanted & set(unit.norm_name.split(" ")))
            if shared:
                scored.append((shared, unit))
        scored.sort(key=lambda item: (-item[0], item[1].level_no, item[1].name, item[1].id))
        return [unit for _, unit in scored[:limit]]

    def recent(self, unit_ids: list[int], limit: int = 5) -> list[Unit]:
        seen: set[int] = set()
        out: list[Unit] = []
        for unit_id in unit_ids:
            unit = self.get(unit_id)
            if unit is None or unit_id in seen:
                continue
            seen.add(unit_id)
            out.append(unit)
            if len(out) == limit:
                break
        return out


def _chain(unit_id: int, by_id: dict[int, repo.OrgUnitNode]) -> tuple[int, ...]:
    """Root-first ids up to ``unit_id``; at most MAX_DEPTH, a loop stops the walk."""
    chain: list[int] = []
    current: int | None = unit_id
    while current is not None and current in by_id and current not in chain:
        chain.append(current)
        if len(chain) == MAX_DEPTH:
            break
        current = by_id[current].parent_id
    return tuple(reversed(chain))


def same_name_count(hits: list[Hit]) -> int:
    """How many hits share the most frequent name."""
    counts = Counter(hit.unit.norm_name for hit in hits)
    return max(counts.values(), default=0)


@dataclass
class OrgUnitCache:
    """The index, re-read with one SELECT when older than REFRESH_SECONDS."""

    refresh_seconds: float = REFRESH_SECONDS
    _index: OrgUnitIndex | None = None
    _loaded_at: float = 0.0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def get(self, db: Database) -> OrgUnitIndex:
        if self._index is not None and time.monotonic() - self._loaded_at < self.refresh_seconds:
            return self._index
        async with self._lock:
            if self._index is None or time.monotonic() - self._loaded_at >= self.refresh_seconds:
                async with db.tx() as conn:
                    nodes = await repo.org_unit_nodes(conn)
                self._index = OrgUnitIndex(nodes)
                self._loaded_at = time.monotonic()
        return self._index

    def invalidate(self) -> None:
        self._loaded_at = 0.0
