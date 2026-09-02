# Bale Archive Bot

Archive bot for [Bale messenger](https://docs.bale.ai) groups, built to run on
**one Windows machine**: local PostgreSQL, local disk for media, NSSM as the
Windows service. No Docker, Redis, or cloud object storage required.

Every piece of content posted in a monitored group is archived first. The
sender is then asked — **in the same group, as a reply** — whether it should
be stored under hashtags. Forwarded posts are accepted like any other
content; there is no extra size or dimension filter.

## Install on Windows

```
copy .env.example .env
# fill BALE_BOT_TOKEN and DATABASE_URL
.\scripts\install.ps1
.\scripts\run.ps1
```

`DATABASE_URL` example (Postgres on this PC):

```
postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/bale_archive
```

Keep it running after logoff with NSSM: `.\scripts\install-service.ps1`

See `docs/RUNBOOK.md` and `docs/DEPLOY_WINDOWS.md`.

## Architecture

```
Update (polling)
   │ idempotency (processed_updates) → per-(chat,user) lock
   ▼
Dispatcher ──► group intake ──► [1] copyMessage → archive group
   │                            [2] INSERT submissions (draft)
   │                            [3] deleteMessage (ONLY after 1+2)
   │                            [4] wizard in the same group (reply)
   ├──► wizard callbacks (FSM, state in conversation_states)
   ├──► admin commands
   ▼
Workers: outbox · media → local MEDIA_ROOT · TTL sweeper · weekly digest
```

Golden rule: **the original message is never deleted before both the archive
copy and the database row exist.**

Conversation state lives only in Postgres (`conversation_states`). Locks use
`pg_advisory_xact_lock`. File storage goes through a `Storage` interface
(`LocalStorage` now; `STORAGE_BACKEND=s3` later).

## Commands

| Command | Who | What |
|---------|-----|------|
| `/start`, `/help`, `/my`, `/undo`, `/resume` | everyone | onboarding, history, undo, resume |
| `آرشیو` / `/archive` in a group | admin/owner | mark that group as the private archive |
| `/panel`, `/stats`, reports, tags, export | admin | admin panel |

## Development

```
python -m pip install -e ".[dev]"
python -m ruff check app tests scripts
python -m black --check app tests scripts
python -m mypy app scripts
python -m pytest -q
```

Or on Windows: `.\scripts\check.ps1`

Tests never touch the network (`tests/fakes/fake_bale.py`).

## Documentation

- `docs/DEPLOY_WINDOWS.md` — first-time setup
- `docs/ADMIN_GUIDE.md` — Persian admin guide
- `docs/RUNBOOK.md` — NSSM, backup, Defender, Windows Update
- `docs/BALE_API_NOTES.md` — probed API behaviour
- `docs/DECISIONS.md` — architecture decisions
