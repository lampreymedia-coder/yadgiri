#!/usr/bin/env bash
# خروجی اکسل کامل آرشیو در /root/bale-archive.xlsx (مجوز 600).
# پرس‌وجو با کاربر balebot و همان env ربات اجرا می‌شود؛ فایل را root می‌نویسد.
#   sudo bash /opt/balebot/src/bale-archive-bot/scripts/export_excel.sh
set -euo pipefail
APP_DIR="${APP_DIR:-/opt/balebot/src/bale-archive-bot}"
VENV="${VENV:-/opt/balebot/venv}"
ENV_FILE="${ENV_FILE:-/etc/balebot/balebot.env}"
OUT="${OUT:-/root/bale-archive.xlsx}"
[[ $EUID -eq 0 ]] || { echo "با root اجرا کنید: sudo bash $0" >&2; exit 1; }
umask 077
tmp="$(mktemp "${OUT}.XXXXXX")"
if (cd "$APP_DIR" && sudo -u balebot env BALEBOT_ENV_FILE="$ENV_FILE" PYTHONUTF8=1 TZ=Asia/Tehran \
      "$VENV/bin/python" scripts/export_excel.py --output -) > "$tmp"; then
  mv "$tmp" "$OUT"
  chmod 600 "$OUT"
  echo "✅ ساخته شد: $OUT"
else
  rm -f "$tmp"
  echo "❌ ساخت اکسل ناموفق بود." >&2
  exit 1
fi
