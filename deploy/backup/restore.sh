#!/bin/sh
# Restore a dump into a database (by default a scratch one, to test backups every quarter):
#   docker compose -f docker-compose.prod.yml exec backup restore.sh /backups/smartfarm-<stamp>.dump
#   docker compose -f docker-compose.prod.yml exec backup restore.sh <file> "$DATABASE_URL"   # real restore
set -eu
FILE="$1"
TARGET="${2:-}"
if [ -z "$TARGET" ]; then
  BASE="${DATABASE_URL%/*}"
  psql --dbname="$DATABASE_URL" -c "DROP DATABASE IF EXISTS smartfarm_restore_test" -c "CREATE DATABASE smartfarm_restore_test"
  TARGET="$BASE/smartfarm_restore_test"
fi
pg_restore --clean --if-exists --no-owner --dbname="$TARGET" "$FILE"
psql --dbname="$TARGET" -tc "SELECT 'farms: ' || count(*) FROM accounts_farm"
psql --dbname="$TARGET" -tc "SELECT 'animals: ' || count(*) FROM livestock_animal"
echo "restore: done into $TARGET"
