"""2-2: daily report at 21:00 Tehran, exactly once per day (state in digest_state.json)."""

from __future__ import annotations

import json
from datetime import datetime

from app.core.digest import maybe_send_daily_digest
from app.i18n import fa
from tests.bot.harness import ADMIN_ID, GROUP, USER, Harness


def _digests(h: Harness) -> list[str]:
    return [t for t in h.texts_to(ADMIN_ID) if t.startswith("📅")]


async def test_digest_once_per_day_after_21(h: Harness) -> None:
    h.register_group()
    await h.text(GROUP, USER, "متن")
    await h.confirm([1])
    today = datetime.now().replace(microsecond=0)  # noqa: DTZ005 — only the date part matters
    assert not await maybe_send_daily_digest(h.ctx, today.replace(hour=20, minute=59))
    assert _digests(h) == []
    assert await maybe_send_daily_digest(h.ctx, today.replace(hour=21, minute=0))
    assert not await maybe_send_daily_digest(h.ctx, today.replace(hour=21, minute=30))
    digests = _digests(h)
    assert len(digests) == 1
    assert fa.jalali(today) in digests[0]
    state = json.loads((h.settings.data_path / "digest_state.json").read_text())
    assert state == {"last_sent_date": today.date().isoformat()}


async def test_digest_survives_restart(h: Harness, api, fake_bale) -> None:  # type: ignore[no-untyped-def]
    day = datetime(2026, 9, 27, 21, 5)
    assert await maybe_send_daily_digest(h.ctx, day)
    restarted = Harness(h.settings, api, fake_bale, h.root)
    try:
        assert not await maybe_send_daily_digest(restarted.ctx, day.replace(hour=23))
    finally:
        await restarted.close()
    assert len(_digests(h)) == 1


def test_text_bar() -> None:
    assert fa.text_bar(1.0, 6) == "██████"
    assert fa.text_bar(0.0, 6) == "░░░░░░"
    assert fa.text_bar(0.5, 6) == "███░░░"
    assert fa.jalali(datetime(2026, 9, 27)) == "۱۴۰۵/۰۷/۰۵"
