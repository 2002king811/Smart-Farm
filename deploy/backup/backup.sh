#!/bin/sh
# Nightly: dump the database, keep 30 days of dumps, copy each one off-site to S3 if
# BACKUP_S3_BUCKET is set (give that bucket a 30-day lifecycle rule).
set -eu
STAMP=$(date -u +%Y%m%d-%H%M%S)
FILE="/backups/smartfarm-$STAMP.dump"
pg_dump --format=custom --no-owner --dbname="$DATABASE_URL" --file="$FILE"
echo "backup: wrote $FILE ($(du -h "$FILE" | cut -f1))"
find /backups -name 'smartfarm-*.dump' -mtime +30 -delete
if [ -n "${BACKUP_S3_BUCKET:-}" ]; then
  AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY_ID:-}" AWS_SECRET_ACCESS_KEY="${S3_SECRET_ACCESS_KEY:-}" \
    aws s3 cp "$FILE" "s3://$BACKUP_S3_BUCKET/db/" ${S3_ENDPOINT_URL:+--endpoint-url "$S3_ENDPOINT_URL"}
  echo "backup: copied to s3://$BACKUP_S3_BUCKET/db/"
fi
