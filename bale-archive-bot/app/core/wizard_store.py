"""Wizard state in program memory only (no table), with a 30-minute expiry.

A restart forgets unfinished wizards. That is accepted: nothing was written
to the database for them and the user's original message was never touched.
"""

from __future__ import annotations

import secrets
import string
import time
from dataclasses import dataclass, field
from datetime import datetime

from app.bale.models import Message
from app.db.repo import GroupRow

STEP_DECISION = "decision"
STEP_TAGS = "tags"
STEP_PREVIEW = "preview"
STEP_SAVING = "saving"

_SID_ALPHABET = string.ascii_lowercase + string.digits


@dataclass(slots=True)
class WizardSession:
    sid: str
    user_id: int
    person_id: int
    group: GroupRow
    origin_chat_id: int
    origin_message_ids: list[int]
    messages: list[Message]
    content_type: int
    content_text: str
    posted_at: datetime
    sender_name: str
    step: str = STEP_DECISION
    selected: list[int] = field(default_factory=list)
    wizard_message_id: int | None = None
    # Private-chat messages to delete when the wizard ends (subject copy, reminder …).
    private_extra_ids: list[int] = field(default_factory=list)
    # Group hint shown when the private chat could not be opened.
    hint_message_id: int | None = None
    created_at: float = field(default_factory=time.monotonic)
    reminded: bool = False

    @property
    def primary_message_id(self) -> int:
        return self.origin_message_ids[0]

    def age_seconds(self, now: float | None = None) -> float:
        return (now if now is not None else time.monotonic()) - self.created_at


class WizardStore:
    def __init__(self) -> None:
        self._by_sid: dict[str, WizardSession] = {}

    def new_sid(self) -> str:
        while True:
            sid = "".join(secrets.choice(_SID_ALPHABET) for _ in range(8))
            if sid not in self._by_sid:
                return sid

    def add(self, session: WizardSession) -> None:
        self._by_sid[session.sid] = session

    def get(self, sid: str) -> WizardSession | None:
        return self._by_sid.get(sid)

    def pop(self, sid: str) -> WizardSession | None:
        return self._by_sid.pop(sid, None)

    def __len__(self) -> int:
        return len(self._by_sid)

    def all(self) -> list[WizardSession]:
        return list(self._by_sid.values())

    def for_user(self, user_id: int) -> list[WizardSession]:
        return [s for s in self._by_sid.values() if s.user_id == user_id]

    def find_by_origin(self, chat_id: int, message_id: int) -> WizardSession | None:
        for session in self._by_sid.values():
            if session.origin_chat_id == chat_id and message_id in session.origin_message_ids:
                return session
        return None

    def expired(self, ttl_seconds: float, now: float | None = None) -> list[WizardSession]:
        return [
            s
            for s in self._by_sid.values()
            if s.step != STEP_SAVING and s.age_seconds(now) >= ttl_seconds
        ]
