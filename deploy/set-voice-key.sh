#!/usr/bin/env bash
# Optional: a separate OpenRouter key only for the voice-over of characters (its own spending limit).
# Without it the voice-over uses OPENROUTER_API_KEY. The key is stored in deploy/.env (root only), never in the app.
#   bash /opt/fonar/deploy/set-voice-key.sh          — set or replace the key
#   bash /opt/fonar/deploy/set-voice-key.sh --remove — go back to the main OpenRouter key
set -euo pipefail
umask 077  # .env and its temporary copy are readable by root only from the first byte
cd "$(dirname "$0")"
DC="docker compose"; docker compose version >/dev/null 2>&1 || DC="docker-compose"
touch .env
if [ "${1:-}" = "--remove" ]; then
  grep -v '^TTS_API_KEY=' .env > .env.tmp || true
  mv .env.tmp .env; chmod 600 .env
  $DC up -d --force-recreate api >/dev/null
  echo "Готово: озвучка снова идёт через основной ключ OpenRouter."
  exit 0
fi
printf 'Вставь ключ OpenRouter для озвучки (sk-or-…) и нажми Enter.\nСимволы при вставке не отображаются — так и должно быть: '
read -rs KEY
echo
KEY="$(echo "$KEY" | tr -d '[:space:]')"
[ -n "$KEY" ] || { echo "Пусто — ничего не изменено."; exit 1; }
case "$KEY" in sk-or-*) ;; *) echo "Это не похоже на ключ OpenRouter (он начинается с sk-or-). Ничего не изменено."; exit 1 ;; esac
# the key goes to curl through stdin, not the command line (the process list shows arguments to every user)
CODE="$(printf 'Authorization: Bearer %s\n' "$KEY" | curl -s -o /dev/null -w '%{http_code}' -H @- https://openrouter.ai/api/v1/key || true)"
[ "$CODE" = "200" ] || { echo "OpenRouter не принял ключ (HTTP $CODE). Ничего не изменено."; exit 1; }
grep -v '^TTS_API_KEY=' .env > .env.tmp || true
echo "TTS_API_KEY=$KEY" >> .env.tmp
mv .env.tmp .env
chmod 600 .env
$DC up -d --force-recreate api >/dev/null
echo "Готово: озвучка идёт через отдельный ключ. Лимит трат на него можно поставить на openrouter.ai/settings/keys."
