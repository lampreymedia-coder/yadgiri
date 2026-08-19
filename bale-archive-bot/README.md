# Bale Archive Bot

A production-grade archive bot for [Bale messenger](https://docs.bale.ai) groups.
Every piece of content posted in a monitored group is archived first, then the
sender is asked — in a private-chat wizard — whether it should be stored under
one or more hashtags. Admins get precise, aggregated and per-entity reports.

## Install in 5 minutes

```bash
git clone <repo> && cd bale-archive-bot
cp .env.example .env      # fill: BALE_BOT_TOKEN, ARCHIVE_CHAT_ID, ADMIN_USER_IDS, DATABASE_URL
docker compose up --build -d
docker compose run --rm app python scripts/seed_tags.py
```

That's it. The `migrate` service applies Alembic migrations automatically,
`app` starts in polling mode by default (`RUN_MODE=polling`), and `/healthz`
answers on port 8000.

For local development with a bundled PostgreSQL:

```bash
docker compose --profile dev up -d postgres
DATABASE_URL=postgresql+asyncpg://bot:bot@localhost:5432/bale_archive
```

## Architecture at a glance

```
Update (polling / webhook)
   │ idempotency (processed_updates) → per-(chat,user) lock
   ▼
Dispatcher ──► group intake ──► [1] copyMessage → archive channel
   │                            [2] INSERT submissions (draft)
   │                            [3] deleteMessage (ONLY after 1+2)
   │                            [4] wizard in private chat (fallback: in-group)
   ├──► wizard callbacks (FSM + back-stack, state in Redis→Postgres)
   ├──► admin commands (reports, tags, export, broadcast)
   ▼
Workers: outbox retry · media download→S3 · TTL sweeper · weekly digest
```

Golden rule: **the original message is never deleted before both the archive
copy and the database row exist.** If either fails, the message stays in the
group, the user gets a short notice and the admin is alerted.

Every stored item has three retention layers: the database row, the archived
message in Bale (works even for 20–50MB files bots cannot download), and the
file in Arvan object storage (when ≤ 20MB).

## Commands

| Command | Who | What |
|---------|-----|------|
| `/start`, `/help`, `/my`, `/undo <code>`, `/resume` | everyone | onboarding, own history, undo, resume wizard |
| `/panel`, `/stats`, `/top_users`, `/top_tags`, `/tag`, `/type`, `/user`, `/search`, `/get`, `/export` | admin | reports & retrieval |
| `/tags`, `/addtag`, `/edittag`, `/disabletag`, `/reordertags` | admin | dynamic hashtag management (no code changes) |
| `/groups`, `/health`, `/settings`, `/broadcast`, `/forget`, `/onboard` | admin | operations |

Admin commands answer only for `ADMIN_USER_IDS` ∪ `users.is_admin`, and only
in private chat or `ADMIN_CHAT_ID`. Everyone else sees a generic
"invalid command" reply.

## Development

```bash
pip install -e ".[dev]"
make check        # ruff + black --check + mypy --strict + pytest
make probe        # scripts/api_probe.py against a test group (writes docs/BALE_API_NOTES.md)
```

Tests never touch the network (`tests/fakes/fake_bale.py`). Postgres-specific
tests use testcontainers and skip automatically when Docker is unavailable.

## Documentation

- `docs/DEPLOY_ARVAN.md` — zero-to-running on Arvan Cloud
- `docs/ADMIN_GUIDE.md` — راهنمای فارسی ادمین
- `docs/RUNBOOK.md` — troubleshooting: 15 likely failures and fixes
- `docs/BALE_API_NOTES.md` — probed API behaviour
- `docs/DECISIONS.md` — architecture decisions and rationale
