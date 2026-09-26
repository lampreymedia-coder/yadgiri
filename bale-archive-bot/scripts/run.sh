#!/usr/bin/env bash
# اجرای دستی ربات در پیش‌زمینه (برای عیب‌یابی). در حالت عادی سرویس systemd کار را می‌کند.
#   sudo systemctl stop balebot && sudo bash scripts/run.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/balebot/src/bale-archive-bot}"
VENV="${VENV:-/opt/balebot/venv}"
ENV_FILE="${ENV_FILE:-/etc/balebot/balebot.env}"

cd "$APP_DIR"
exec sudo -u balebot env \
  BALEBOT_ENV_FILE="$ENV_FILE" PYTHONUTF8=1 PYTHONUNBUFFERED=1 TZ=Asia/Tehran RUN_MODE=polling \
  LOG_FORMAT=console "$VENV/bin/python" -m app.main
