#!/usr/bin/env bash
# Consistent backup of the database + uploaded images. Keeps the last 14 archives.
# With DATA_KEY (encryption at rest) the archive holds only encrypted data: it is safe to copy elsewhere,
# but it can be restored only with the same key (bash show-data-key.sh — keep it in a password manager).
set -euo pipefail
umask 077  # archives and settings copies: readable by root only
cd "$(dirname "$0")"
DC="docker compose"; docker compose version >/dev/null 2>&1 || DC="docker-compose"
mkdir -p backups
chmod 700 backups
STAMP="$(date +%Y%m%d-%H%M%S)"
$DC exec -T api python -m app.backup /data/backup.sqlite3
tar -czf "backups/fonar-$STAMP.tar.gz" -C data/api backup.sqlite3 images
# the settings (with the keys) are kept next to the archives, for a restore on this server; copy only the
# fonar-*.tar.gz archives off the server, and the key separately
cp .env "backups/env-$STAMP" && chmod 600 "backups/env-$STAMP"
rm -f data/api/backup.sqlite3
ls -1t backups/fonar-*.tar.gz | tail -n +15 | xargs -r rm -f
ls -1t backups/env-* | tail -n +15 | xargs -r rm -f
echo "backup: $(pwd)/backups/fonar-$STAMP.tar.gz ($(du -h "backups/fonar-$STAMP.tar.gz" | cut -f1))"
