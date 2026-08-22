#!/usr/bin/env bash
# Restart the bot process if it exits so receive never stays down.
set -u
cd "$(dirname "$0")/.."
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi
PYTHON="${PYTHON:-/tmp/venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="${PYTHON:-python3}"
fi
while true; do
  echo "keep_alive: starting app.main at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  "$PYTHON" -m app.main
  code=$?
  echo "keep_alive: app.main exited ${code} at $(date -u +%Y-%m-%dT%H:%M:%SZ); restart in 2s"
  sleep 2
done
