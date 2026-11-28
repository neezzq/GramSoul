#!/usr/bin/env bash
# Update the backend to the latest code. Data and settings stay.
set -euo pipefail
cd "$(dirname "$0")"
DC="docker compose"; docker compose version >/dev/null 2>&1 || DC="docker-compose"
if [ "${FONAR_UPDATED:-}" != 1 ]; then
  bash backup.sh
  BRANCH="$(git -C .. rev-parse --abbrev-ref HEAD)"
  git -C .. fetch --depth 1 origin "$BRANCH"
  git -C .. checkout -q -B "$BRANCH" FETCH_HEAD
  # continue with the freshly pulled version of this very script
  FONAR_UPDATED=1 exec bash "$0" "$@"
fi
bash ensure-data-key.sh  # encryption at rest: created once; the API encrypts the existing data on its next start
mkdir -p backups && chmod 700 data/api backups && chmod 600 backups/* 2>/dev/null || true  # older copies too
$DC up -d --build --remove-orphans
# Caddyfile is a bind mount: apply its changes without dropping connections
$DC exec -T caddy caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1 || $DC restart caddy
if grep -qiE '^LOCAL_AI=(on|1|true|yes)' .env 2>/dev/null; then
  $DC --profile local up -d ollama
  MODEL="$(grep -E '^LLM_MODEL=' .env | cut -d= -f2- | awk '{print $1}')"
  $DC exec -T ollama ollama pull "${MODEL:-qwen2.5:0.5b}"
else
  # the small local model is off: stop it and give its ~700 MB of memory back
  $DC rm -sf ollama >/dev/null 2>&1 || true
fi
$DC restart api
bash fetch-apk.sh || true
docker image prune -f >/dev/null
echo "updated to $(git -C .. log -1 --format='%h %s')"
