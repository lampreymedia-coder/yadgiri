"""Default new groups to research; archive groups stay archive."""

from __future__ import annotations

from types import SimpleNamespace

from app.domain.group_roles import ensure_research_role, group_role


def test_ensure_research_role_fills_missing_role() -> None:
    group = SimpleNamespace(settings={})
    assert ensure_research_role(group) is True  # type: ignore[arg-type]
    assert group_role(group) == "research"  # type: ignore[arg-type]
    assert group.settings["role_asked"] is True


def test_ensure_research_role_does_not_overwrite_archive() -> None:
    group = SimpleNamespace(settings={"role": "archive", "tag_slug": "learning"})
    assert ensure_research_role(group) is False  # type: ignore[arg-type]
    assert group_role(group) == "archive"  # type: ignore[arg-type]
    assert group.settings["tag_slug"] == "learning"
