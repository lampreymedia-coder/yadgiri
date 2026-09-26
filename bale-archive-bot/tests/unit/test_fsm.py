"""Unit tests: wizard FSM back-stack semantics."""

from __future__ import annotations

from app.core.fsm import Conversation, WizardState


def test_transition_pushes_history() -> None:
    conv = Conversation(chat_id=1, user_id=2)
    conv.transition(WizardState.AWAITING_DECISION)
    conv.transition(WizardState.AWAITING_TAG_COUNT)
    conv.transition(WizardState.AWAITING_TAGS)
    assert conv.state is WizardState.AWAITING_TAGS
    assert conv.history == [
        WizardState.AWAITING_DECISION.value,
        WizardState.AWAITING_TAG_COUNT.value,
    ]


def test_back_pops_and_preserves_payload() -> None:
    conv = Conversation(chat_id=1, user_id=2)
    conv.transition(WizardState.AWAITING_DECISION)
    conv.transition(WizardState.AWAITING_TAG_COUNT)
    conv.transition(WizardState.AWAITING_TAGS)
    conv.payload["selected"] = [1, 2]
    assert conv.go_back() is WizardState.AWAITING_TAG_COUNT
    # Back never clears selections.
    assert conv.payload["selected"] == [1, 2]
    assert conv.can_go_back
    assert conv.go_back() is WizardState.AWAITING_DECISION
    assert not conv.can_go_back
    assert conv.go_back() is None


def test_idle_start_not_pushed() -> None:
    conv = Conversation(chat_id=1, user_id=2)
    conv.transition(WizardState.AWAITING_DECISION)
    assert conv.history == []
    assert not conv.can_go_back
