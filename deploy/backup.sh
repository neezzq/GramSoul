#!/usr/bin/env bash
# Consistent backup of the database + uploaded images. Keeps the last 14 archives.
set -euo pipefail
cd "$(dirname "$0")"
DC="docker compose"; docker compose version >/dev/null 2>&1 || DC="docker-compose"
mkdir -p backups
STAMP="$(date +%Y%m%d-%H%M%S)"
$DC exec -T api python -c "
import sqlite3
src = sqlite3.connect('/data/fonar.sqlite3'); dst = sqlite3.connect('/data/backup.sqlite3')
src.backup(dst); dst.close(); src.close()"
tar -czf "backups/fonar-$STAMP.tar.gz" -C data/api backup.sqlite3 images
cp .env "backups/env-$STAMP" && chmod 600 "backups/env-$STAMP"
rm -f data/api/backup.sqlite3
ls -1t backups/fonar-*.tar.gz | tail -n +15 | xargs -r rm -f
ls -1t backups/env-* | tail -n +15 | xargs -r rm -f
echo "backup: $(pwd)/backups/fonar-$STAMP.tar.gz ($(du -h "backups/fonar-$STAMP.tar.gz" | cut -f1))"
