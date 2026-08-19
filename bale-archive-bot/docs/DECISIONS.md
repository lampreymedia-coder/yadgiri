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

## D-04: Conversation state is written to Postgres even when Redis is up
`STATE_BACKEND=auto` uses Redis for speed but always mirrors to
`conversation_states`. Redis may evict or restart without persistence; the
spec's hard requirement is that a container restart mid-wizard loses nothing.
Double-write costs one small UPSERT per step and removes a whole failure mode.

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

## D-09: `sendMessage` failure inside the wizard falls back to the group
Opening the wizard tries the private chat first. `403` means "user never
pressed /start" → `users.has_private_chat=false` and the in-group single-message
wizard is used, including a URL button to the bot (`https://ble.ir/<bot>`).

## D-10: Republish uses copyMessage from the archive, not forward
The spec's open question ("bot-authored repost vs forward") is resolved toward
`copyMessage` with a `📌/📎 {sender}` header line: forwards would show the
*bot* as forwarder anyway (the original message is already deleted), and the
header preserves attribution in plain text.

## D-11: Edited messages are logged and ignored
`edited_message` arrives after the gateway has already archived/deleted the
original. Re-running intake would duplicate content; the raw update is still
recorded in logs for audit. Revisit if editing becomes a real workflow.

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
