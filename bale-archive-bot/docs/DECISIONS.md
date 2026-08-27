# Architecture Decisions

Each entry records a decision made where the spec was ambiguous or collided
with a platform/technical constraint, and why.

## D-01: Pydantic models instead of plain dataclasses for API objects
The spec's file layout says "dataclass های Update/Message/…" while the security
section mandates validating every update's JSON shape with pydantic before any
processing. One pydantic model per object satisfies both intents with a single
source of truth; `extra="allow"` keeps unknown fields so `raw_update` stays
lossless and undocumented fields (e.g. `media_group_id`) can be probed.

## D-02: Single-character normalisation maps live in `classify.py`, not `fa.py`
Rule 2 bans Persian *display strings* outside `app/i18n/fa.py`. The Arabic→
Persian character tables (ي→ی, ك→ک, …) and the slug transliteration table are
linguistic *data* required by the normalisation algorithm, not user-facing
text. Seed tag titles, however, are display strings and therefore live in
`fa.py` (`SEED_TAGS`).

## D-03: `users.display_name` generated column is Postgres-only
The mandated schema uses `GENERATED ALWAYS AS (btrim(...)) STORED`, which the
Alembic migration creates verbatim on PostgreSQL. SQLite (used for fast tests)
lacks `btrim`, so the ORM computes `display_name` as a Python property and the
report SQL uses `coalesce(u.display_name, '')`. Production behaviour is
identical to the spec.

## D-04: Conversation state lives only in Postgres
Redis is not installed and is not a dependency. `STATE_BACKEND` is forced to
`postgres`. Wizard state is the `conversation_states` table; cross-process
locks are `pg_advisory_xact_lock`.

## D-05: private-first submissions with multiple groups get a group-choice step
The spec doesn't say which group a private-first submission belongs to when
the bot serves several groups. Implemented: exactly one active group → it is
used automatically; several → the wizard first shows a group-selection
keyboard; none → the item is archived without group publication.

## D-06: Album handling buffers per (chat, user, media_group_id)
`ALBUM_WINDOW_MS` buffering as mandated. When Bale does send the undocumented
`media_group_id` (probed by `api_probe.py`), it participates in the buffer key
so interleaved albums from the same user cannot merge.

## D-07: Circuit breaker triggers only on connectivity-class errors
`OperationalError`/`InterfaceError`/socket errors open the breaker and spool
updates to disk. Integrity or programming errors do NOT: they indicate a logic
bug, not an unavailable database, and spooling them would hide the bug and
delay the user for no benefit.

## D-08: Load-test latency is asserted with bounded concurrency on SQLite
The no-network test suite runs the 200-update load test against SQLite, which
allows a single writer; unbounded task fan-out measures lock queueing, not
processing latency. The test bounds concurrency at 16 (the polling loop
naturally paces work anyway) and still dispatches every update as a concurrent
duplicate pair, so the zero-duplicates guarantee is fully exercised. The p95 <
2s target for production is meant for PostgreSQL.

## D-09: Hashtag wizard is private; group stays uncluttered
Content in a research group is left in place. The bot asks the sender in a
private chat which hashtag(s) to store under. If the user has never pressed
Start, a short URL hint is posted in the group and deleted as soon as the
private conversation continues. Research vs archive is also asked privately
of the admin who added the bot, then any leftover bot prompt in the group is
deleted (`deleteMessage`).

## D-10: Confirmed items are copied into per-hashtag archive groups
Each active hashtag can be bound to its own private archive group
(`/archive` then pick the hashtag). On confirm, the original is
`copyMessage`d into every selected tag's archive chat and a compact footer
is sent as a reply. SQL is the source of truth: a missing archive group does
not block the save; admins are notified instead. The research group is never
republished into. Bale's bot HTTP API has no `setMessageReaction` (live probe
returns 404 handler-not-found); users can react in the app, but a bot cannot
put an emoji on another member's message. We do not reply in the research
group to fake a mark. Full save reports stay in the admin private chat.

## D-11: Origin edits replace the stored copy; the latest text is archived
`edited_message` is matched to the existing submission by origin chat +
message id (no second intake). SQL text/caption is overwritten, the private
subject copy is replaced, and archive copies use the stored latest text for
text/link (Bale `copyMessage` can still return the pre-edit snapshot). If the
item was already completed, archive copies are deleted and rewritten. Private
wizard leftovers of a decided item are deleted; only a short summary stays,
then that summary is deleted after `PRIVATE_SUMMARY_TTL_SECONDS` (default 30).

## D-12: `pg_trgm` creation is attempted inside the migration
`CREATE EXTENSION IF NOT EXISTS pg_trgm` runs in migration 0001. On managed
DBaaS instances where the app user lacks the privilege, run it once as the
maintenance user; the migration failure message makes this obvious. `/search`
falls back to `ILIKE` on non-Postgres engines.

## D-13: Rate-limit numbers are conservative defaults, env-tunable
Bale publishes no official limits. Defaults: 20 rps global, 1 msg/s per chat,
20 msg/min per group. All three read from `.env`. The probe script records
observed 429 behaviour to inform tuning.

## D-14: `answerCallbackQuery` is capability-gated
Listed in the spec as "exists but must be probed". `capabilities.py` probes it
at startup; every call site checks `caps.has("answerCallbackQuery")` and
degrades to silence (the keyboard still works, only toasts disappear).

## D-15: Windows-native single machine
No Docker, Redis, Caddy, or cloud object storage. Media is written under
`MEDIA_ROOT` through the `Storage` protocol (`LocalStorage` now, `S3Storage`
behind `STORAGE_BACKEND=s3`). The process is an NSSM Windows service.
`PYTHONUTF8=1` and `tzdata` keep Persian text and Jalali dates correct.

## D-16: Bale may withhold ordinary research-group messages
The Bot HTTP API does not expose `can_read_all_group_messages` or group
privacy. Live polling shows that an admin bot still receives ordinary texts
and forwards in groups that keep regular members (e.g. cyber Economy), but
only join/service events and `@bot` mentions in groups where nearly every
member is an administrator. When member/admin counts look like that, or when
Bale delivers an empty group stub, the bot DMs the sender/admin with the
concrete blocker and the private-first fallback instead of staying silent.
The dispatcher cannot invent updates Bale never sent. Join events may
arrive as ``new_chat_members`` or as ``my_chat_member``. New groups default
to research; archive groups are bound only with ``/archive``. The bot stays
in every group it is added to and waits for admin promotion instead of
leaving.

## D-17: Adding the bot to a group is enough
Owners add the bot to many research groups and should not answer a
research-versus-archive question each time. Join always registers the chat
as research. Typing ``آرشیو`` / ``/archive`` inside a group is the only way
to bind a per-hashtag archive. Anyone may add the bot; it does not leave
because the adder is not a group administrator. After it is promoted, the
next ordinary message opens the private wizard.

