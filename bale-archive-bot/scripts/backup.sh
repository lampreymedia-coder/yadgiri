#!/usr/bin/env bash
# Nightly PostgreSQL backup to the Arvan backup bucket, 30-day retention.
# Requires: pg_dump, gzip, s3cmd (configured via ~/.s3cfg or env vars below).
#
# Env:
#   DATABASE_URL           postgresql://user:pass@host:5432/db
#   S3_BUCKET_BACKUP       bale-archive-backup
#   S3_ENDPOINT_URL        https://s3.ir-thr-at1.arvanstorage.ir
#   S3_ACCESS_KEY / S3_SECRET_KEY
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${S3_BUCKET_BACKUP:?S3_BUCKET_BACKUP is required}"
: "${S3_ENDPOINT_URL:?S3_ENDPOINT_URL is required}"
: "${S3_ACCESS_KEY:?S3_ACCESS_KEY is required}"
: "${S3_SECRET_KEY:?S3_SECRET_KEY is required}"

HOST_BASE="${S3_ENDPOINT_URL#https://}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
KEY="pg/backup-${STAMP}.dump.gz"

echo "[backup] dumping database..."
# Strip the SQLAlchemy driver suffix if present.
PG_URL="${DATABASE_URL/postgresql+asyncpg/postgresql}"

pg_dump --format=custom --no-owner "${PG_URL}" | gzip \
  | s3cmd --host="${HOST_BASE}" --host-bucket="${HOST_BASE}/%(bucket)s" \
          --access_key="${S3_ACCESS_KEY}" --secret_key="${S3_SECRET_KEY}" \
          put - "s3://${S3_BUCKET_BACKUP}/${KEY}"

echo "[backup] uploaded s3://${S3_BUCKET_BACKUP}/${KEY}"

echo "[backup] pruning backups older than 30 days..."
CUTOFF="$(date -u -d '30 days ago' +%Y%m%d || date -u -v-30d +%Y%m%d)"
s3cmd --host="${HOST_BASE}" --host-bucket="${HOST_BASE}/%(bucket)s" \
      --access_key="${S3_ACCESS_KEY}" --secret_key="${S3_SECRET_KEY}" \
      ls "s3://${S3_BUCKET_BACKUP}/pg/" | while read -r _date _time _size path; do
  name="$(basename "${path}")"
  stamp="${name#backup-}"; stamp="${stamp%%-*}"
  if [[ "${stamp}" =~ ^[0-9]{8}$ ]] && [[ "${stamp}" < "${CUTOFF}" ]]; then
    echo "[backup] deleting old ${path}"
    s3cmd --host="${HOST_BASE}" --host-bucket="${HOST_BASE}/%(bucket)s" \
          --access_key="${S3_ACCESS_KEY}" --secret_key="${S3_SECRET_KEY}" \
          del "${path}"
  fi
done

echo "[backup] done"
