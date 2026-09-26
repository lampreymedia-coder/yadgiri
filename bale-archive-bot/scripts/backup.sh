#!/usr/bin/env bash
# پشتیبان کامل دیتابیس Bale_Archive با mysqldump (فقط خواندن).
# اجرا با root:  sudo bash scripts/backup.sh
# خروجی: /var/backups/balebot/Bale_Archive-<تاریخ>.sql.gz
set -euo pipefail

DB_NAME="${DB_NAME:-Bale_Archive}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/balebot}"
KEEP_DAYS="${KEEP_DAYS:-30}"

if [[ $EUID -ne 0 ]]; then
  echo "این اسکریپت را با root اجرا کنید: sudo bash $0" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
stamp="$(TZ=Asia/Tehran date +%Y%m%d-%H%M%S)"
target="$BACKUP_DIR/${DB_NAME}-${stamp}.sql.gz"

# root روی اوبونتو با auth_socket وارد MySQL می‌شود؛ رمز لازم نیست.
if ! mysqldump --single-transaction --routines --triggers --default-character-set=utf8mb4 \
    --databases "$DB_NAME" | gzip > "$target.part"; then
  rm -f "$target.part"
  echo "❌ پشتیبان‌گیری ناموفق بود." >&2
  exit 1
fi
mv "$target.part" "$target"
chmod 600 "$target"
find "$BACKUP_DIR" -name "${DB_NAME}-*.sql.gz" -mtime "+$KEEP_DAYS" -delete
echo "✅ پشتیبان ساخته شد: $target ($(du -h "$target" | cut -f1))"
