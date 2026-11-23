#!/usr/bin/env bash
# Update the backend to the latest code. Data, settings and the model stay.
set -euo pipefail
cd "$(dirname "$0")"
DC="docker compose"; docker compose version >/dev/null 2>&1 || DC="docker-compose"
bash backup.sh
BRANCH="$(git -C .. rev-parse --abbrev-ref HEAD)"
git -C .. fetch --depth 1 origin "$BRANCH"
git -C .. checkout -q -B "$BRANCH" FETCH_HEAD
$DC up -d --build --remove-orphans
MODEL="$(grep -E '^LLM_MODEL=' .env | cut -d= -f2- | awk '{print $1}')"
$DC exec -T ollama ollama pull "${MODEL:-qwen2.5:0.5b}"
$DC restart api
bash fetch-apk.sh || true
docker image prune -f >/dev/null
echo "updated to $(git -C .. log -1 --format='%h %s')"
