#!/usr/bin/env bash
# Restart the bot process if it exits so receive never stays down.
# Re-read .env on every restart. This wrapper used to source once; a stale
# exported RUN_MODE=webhook then beat the file and left the process on a
# dead tunnel.
set -u
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-/tmp/venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="python3"
fi
while true; do
  if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
  fi
  export RUN_MODE="${RUN_MODE:-polling}"
  echo "keep_alive: starting app.main at $(date -u +%Y-%m-%dT%H:%M:%SZ) mode=${RUN_MODE}"
  "$PYTHON" -m app.main
  code=$?
  echo "keep_alive: app.main exited ${code} at $(date -u +%Y-%m-%dT%H:%M:%SZ); restart in 2s"
  sleep 2
done
