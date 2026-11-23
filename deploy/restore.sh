#!/usr/bin/env bash
# Restore from an archive made by backup.sh:  bash restore.sh backups/fonar-YYYYmmdd-HHMMSS.tar.gz
set -euo pipefail
cd "$(dirname "$0")"
[ -f "${1:-}" ] || { echo "usage: bash restore.sh backups/fonar-....tar.gz"; exit 1; }
DC="docker compose"; docker compose version >/dev/null 2>&1 || DC="docker-compose"
TMP="$(mktemp -d)"; tar -xzf "$1" -C "$TMP"
$DC stop api
mkdir -p data/api/images
cp "$TMP/backup.sqlite3" data/api/fonar.sqlite3
rm -f data/api/fonar.sqlite3-wal data/api/fonar.sqlite3-shm
cp -a "$TMP/images/." data/api/images/ 2>/dev/null || true
chown -R 10001:10001 data/api
rm -rf "$TMP"
$DC start api
echo "restored from $1"
