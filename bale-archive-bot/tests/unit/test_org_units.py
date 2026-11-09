"""OrgUnits in memory: normalisation, search, ranking, paths, suggestions, speed."""

from __future__ import annotations

import random
import time

from app.db.repo import OrgUnitNode
from app.domain.org_units import MAX_DEPTH, OrgUnitIndex, normalize, same_name_count
from app.handlers.org_units import LABEL_MAX, result_label


def node(
    uid: int, level: int, name: str, parent: int | None = None, active: bool = True
) -> OrgUnitNode:
    return OrgUnitNode(uid, level, name, parent, active)


def ids(index: OrgUnitIndex, query: str) -> list[int]:
    return [hit.unit.id for hit in index.search(query)]


NAGASHT = [
    node(100, 1, "معاونت پژوهش"),
    node(101, 2, "اندیشکده توسعه صنعتی نگاشت", 100),
    node(102, 2, "اندیشکده راهبردی افق", 100),
    node(103, 3, "سیستم کنترل بلوغ و انتقال فاز", 101),
    node(104, 3, "سیستم کنترل بلوغ و انتقال فاز", 102),
    node(105, 4, "بخش پایش", 103),
    node(106, 2, "مركز نگاشت‌هاي ملي", 100),  # Arabic ي/ك and a ZWNJ
    node(107, 2, "واحد خاموش نگاشت", 100, active=False),
]


def test_normalize_letters_zwnj_diacritics_digits_case() -> None:
    assert normalize("مركز  نگاشت‌هاي ملي") == "مرکز نگاشتهای ملی"
    assert normalize("عِلمی ۱۲٣ ABC") == "علمی 123 abc"


def test_search_ignores_letter_and_zwnj_differences() -> None:
    index = OrgUnitIndex(NAGASHT)
    assert ids(index, "مرکز نگاشت‌های ملی") == [106]
    assert ids(index, "نگاشتهاي") == [106]
    assert 101 in ids(index, "نگاشت")


def test_all_words_must_match_and_inactive_units_are_hidden() -> None:
    index = OrgUnitIndex(NAGASHT)
    assert ids(index, "اندیشکده نگاشت") == [101]
    assert ids(index, "اندیشکده") == [101, 102]
    assert 107 not in ids(index, "خاموش")
    assert ids(index, "ن") == []  # at least two letters


def test_parent_plus_name_finds_only_the_unit_under_that_parent() -> None:
    index = OrgUnitIndex(NAGASHT)
    assert ids(index, "سیستم کنترل بلوغ") == [103, 104]
    assert ids(index, "نگاشت کنترل بلوغ") == [103]
    assert ids(index, "افق سیستم کنترل بلوغ") == [104]


def test_ranking_exact_then_prefix_then_rest_lower_level_first() -> None:
    index = OrgUnitIndex(
        [
            node(1, 1, "ریشه"),
            node(2, 4, "سامانه رصد نو", 1),  # contains, deep
            node(3, 2, "سامانه رصد قدیم", 1),  # contains, shallow
            node(4, 5, "رصد", 1),  # exact
            node(5, 3, "رصد میدانی", 1),  # starts with
            node(6, 2, "رصدخانه", 1),  # starts with, shallower
        ]
    )
    assert ids(index, "رصد") == [4, 6, 5, 3, 2]


def test_path_follows_parents_with_depth_and_loop_guard() -> None:
    index = OrgUnitIndex(NAGASHT)
    assert index.path_names(index.units[105]) == [
        "معاونت پژوهش",
        "اندیشکده توسعه صنعتی نگاشت",
        "سیستم کنترل بلوغ و انتقال فاز",
        "بخش پایش",
    ]
    loop = OrgUnitIndex([node(1, 1, "الف", 2), node(2, 2, "ب", 1)])
    assert list(loop.units[1].path_ids) == [2, 1]
    deep = OrgUnitIndex([node(i, i, f"سطح {i}", i - 1 if i > 1 else None) for i in range(1, 16)])
    assert len(deep.units[15].path_ids) == MAX_DEPTH and deep.units[15].path_ids[-1] == 15


def test_button_label_two_ancestors_level_and_cut_from_the_start() -> None:
    index = OrgUnitIndex(NAGASHT)
    label = result_label(index, index.units[105])
    assert len(label) <= LABEL_MAX
    assert label.startswith("…") and label.endswith("› بخش پایش (س۴)")
    short = OrgUnitIndex(
        [node(1, 1, "ستاد"), node(2, 2, "واحد", 1), node(3, 3, "دفتر", 2), node(4, 4, "میز", 3)]
    )
    assert result_label(short, short.units[4]) == "واحد › دفتر › میز (س۴)"


def test_suggestions_from_the_group_title() -> None:
    index = OrgUnitIndex(NAGASHT)
    top = [u.id for u in index.suggest("نهاد اندیشکده ای - نگاشت")]
    assert 101 in top and len(top) <= 3
    assert index.suggest("گروه برنامه رسته و") == []
    assert index.suggest("گروه دوستان قدیمی") == []


def test_recent_skips_repeats_and_inactive() -> None:
    index = OrgUnitIndex(NAGASHT)
    assert [u.id for u in index.recent([103, 103, 107, 101, 999, 102, 104, 105, 106])] == [
        103,
        101,
        102,
        104,
        105,
    ]


def test_same_name_count() -> None:
    index = OrgUnitIndex(NAGASHT)
    assert same_name_count(index.search("سیستم کنترل بلوغ")) == 2


def synthetic_units(total: int = 14_000) -> list[OrgUnitNode]:
    """~14,000 units in 7 levels; many names repeat under different parents."""
    rng = random.Random(7)
    words = ["نگاشت", "بلوغ", "کنترل", "سیستم", "پایش", "راهبرد", "توسعه", "صنعتی", "افق", "داده"]
    repeated = ["سیستم کنترل بلوغ و انتقال فاز", "دفتر هماهنگی", "واحد پشتیبانی"]
    nodes: list[OrgUnitNode] = []
    levels: list[list[int]] = [[] for _ in range(8)]
    for uid in range(1, total + 1):
        level = 1 if uid <= 20 else min(7, 2 + (uid % 6))
        parents = levels[level - 1]
        parent = rng.choice(parents) if parents else None
        if parent is None:
            level = 1
        name = rng.choice(repeated) if uid % 7 == 0 else " ".join(rng.sample(words, 3)) + f" {uid}"
        nodes.append(node(uid, level, name, parent))
        levels[level].append(uid)
    return nodes


def test_search_on_14000_units_is_fast() -> None:
    index = OrgUnitIndex(synthetic_units())
    assert len(index.active) == 14_000
    for query in [
        "نگاشت",
        "کنترل بلوغ",
        "نگاشت کنترل بلوغ",
        "سیستم کنترل بلوغ و انتقال فاز",
        "1234",
        "ناموجود",
    ]:
        started = time.perf_counter()
        index.search(query)
        assert time.perf_counter() - started < 0.2, query
