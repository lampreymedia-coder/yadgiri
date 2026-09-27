"""2-1: every successful save notifies all admins; bursts are batched."""

from __future__ import annotations

from app.core.notify import AdminNotifier
from tests.bot.harness import ADMIN_ID, GROUP, USER, Harness


def _admin_texts(h: Harness) -> list[str]:
    return [t for t in h.texts_to(ADMIN_ID) if t.startswith("🆕")]


async def test_each_save_notifies_admin(h: Harness) -> None:
    h.register_group()
    await h.text(GROUP, USER, "اولی")
    await h.confirm([1])
    notes = _admin_texts(h)
    assert len(notes) == 1
    assert "علی رضایی" in notes[0] and "گروه رصد" in notes[0] and "#یادگیری" in notes[0]
    assert "متن" in notes[0]


async def test_burst_of_saves_is_batched(h: Harness) -> None:
    h.register_group()
    for index in range(7):
        await h.text(GROUP, USER, f"متن {index}")
        await h.confirm([1])
    assert h.count("Post") == 7
    assert len(_admin_texts(h)) == 5  # sixth and seventh wait for the summary
    await h.ctx.notifier.flush_due(force=True)
    notes = _admin_texts(h)
    assert len(notes) == 6
    assert "تجمیعی" in notes[-1] and notes[-1].count("\n•") == 2


async def test_batch_waits_for_the_window() -> None:
    now = [0.0]

    class FakeApi:
        sent: list[tuple[int, str]] = []

        async def send_message(self, chat_id: int, text: str) -> None:
            self.sent.append((chat_id, text))

    class Admins:
        all = {1}

    api = FakeApi()
    notifier = AdminNotifier(api, Admins(), clock=lambda: now[0])  # type: ignore[arg-type]
    for _ in range(6):
        await notifier.post_saved("full", "• short")
    assert len(api.sent) == 5
    now[0] = 100
    await notifier.flush_due()
    assert len(api.sent) == 5  # window (300 s) not over yet
    now[0] = 301
    await notifier.flush_due()
    assert len(api.sent) == 6
    # after the window the counter resets: next save is announced alone again
    now[0] = 1000
    await notifier.post_saved("full", "• short")
    assert api.sent[-1] == (1, "full")


async def test_admin_send_failure_does_not_break_the_save(h: Harness) -> None:
    h.register_group()
    h.fake.forbidden_private_chats.add(ADMIN_ID)
    await h.text(GROUP, USER, "متن")
    await h.confirm([1])
    assert h.count("Post") == 1
    delivered = [m for m in h.fake.messages.values() if m.chat_id == ADMIN_ID]
    assert delivered == []  # attempted, refused (403), logged as admin_notify_failed
