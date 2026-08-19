#!/usr/bin/env bash
# Restore a backup produced by backup.sh.
#
# Usage:
#   ./scripts/restore.sh s3://bale-archive-backup/pg/backup-YYYYMMDD-HHMMSS.dump.gz
#   ./scripts/restore.sh /path/to/backup.dump.gz
#
# Env: DATABASE_URL (target database; must already exist), and for s3 paths
#      S3_ENDPOINT_URL / S3_ACCESS_KEY / S3_SECRET_KEY.
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"
SOURCE="${1:?usage: restore.sh <s3://...|/path/to/backup.dump.gz>}"

PG_URL="${DATABASE_URL/postgresql+asyncpg/postgresql}"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

if [[ "${SOURCE}" == s3://* ]]; then
  : "${S3_ENDPOINT_URL:?S3_ENDPOINT_URL is required for s3 restore}"
  : "${S3_ACCESS_KEY:?S3_ACCESS_KEY is required}"
  : "${S3_SECRET_KEY:?S3_SECRET_KEY is required}"
  HOST_BASE="${S3_ENDPOINT_URL#https://}"
  echo "[restore] downloading ${SOURCE}..."
  s3cmd --host="${HOST_BASE}" --host-bucket="${HOST_BASE}/%(bucket)s" \
        --access_key="${S3_ACCESS_KEY}" --secret_key="${S3_SECRET_KEY}" \
        get "${SOURCE}" "${WORK}/backup.dump.gz"
  FILE="${WORK}/backup.dump.gz"
else
  FILE="${SOURCE}"
fi

echo "[restore] WARNING: this will overwrite objects in the target database."
read -r -p "Type RESTORE to continue: " CONFIRM
if [[ "${CONFIRM}" != "RESTORE" ]]; then
  echo "[restore] aborted"
  exit 1
fi

echo "[restore] restoring..."
gunzip -c "${FILE}" | pg_restore --clean --if-exists --no-owner --dbname="${PG_URL}"

echo "[restore] verifying..."
psql "${PG_URL}" -c "SELECT count(*) AS submissions FROM submissions;" || true
echo "[restore] done — record the result of this test in docs/RUNBOOK.md"
