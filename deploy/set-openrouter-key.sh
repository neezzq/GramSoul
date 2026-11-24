#!/usr/bin/env bash
# Stores the OpenRouter API key on this server (deploy/.env, readable by root only)
# and restarts the API. The key is never put into the app.
#   bash /opt/fonar/deploy/set-openrouter-key.sh
set -euo pipefail
cd "$(dirname "$0")"
DC="docker compose"; docker compose version >/dev/null 2>&1 || DC="docker-compose"
printf 'Вставь ключ OpenRouter (начинается с sk-or-) и нажми Enter.\nСимволы при вставке не отображаются — так и должно быть: '
read -rs KEY
echo
KEY="$(echo "$KEY" | tr -d '[:space:]')"
[ -n "$KEY" ] || { echo "Пусто — ничего не изменено."; exit 1; }
case "$KEY" in sk-or-*) ;; *) echo "Это не похоже на ключ OpenRouter (он начинается с sk-or-). Ничего не изменено."; exit 1 ;; esac

echo "Проверяю ключ в OpenRouter…"
CODE="$(curl -s -o /tmp/or-key.json -w '%{http_code}' -H "Authorization: Bearer $KEY" https://openrouter.ai/api/v1/key || true)"
if [ "$CODE" != "200" ]; then
  echo "OpenRouter не принял ключ (HTTP $CODE). Проверь, что скопировал его целиком."; rm -f /tmp/or-key.json; exit 1
fi
python3 - <<'PY' 2>/dev/null || true
import json
d = json.load(open("/tmp/or-key.json")).get("data", {})
print(f"Ключ рабочий. Лимит: {d.get('limit')}, потрачено: {d.get('usage')}")
PY
rm -f /tmp/or-key.json

touch .env
grep -v '^OPENROUTER_API_KEY=' .env > .env.tmp || true
echo "OPENROUTER_API_KEY=$KEY" >> .env.tmp
mv .env.tmp .env
chmod 600 .env
$DC up -d --force-recreate api >/dev/null
DOMAIN="$(grep -E '^DOMAIN=' .env | cut -d= -f2-)"
for i in $(seq 1 20); do
  if curl -fsS "https://$DOMAIN/v1/health" 2>/dev/null | grep -q '"cloud":true'; then
    echo "Готово: облачный ИИ включён. Новые сцены по умолчанию облачные; в старых переключи «ИИ» в меню сцены."
    exit 0
  fi
  sleep 2
done
echo "API перезапущен, но /v1/health пока не отвечает — проверь: $DC logs --tail=50 api"
