#!/usr/bin/env bash
# Connects YooKassa payments (coins and Elite). The keys are stored in deploy/.env (root only), never in the app.
# Until they are set, the app shows «Оплата скоро» and nothing is charged.
#   bash /opt/fonar/deploy/set-yookassa.sh          — set or replace shopId and the secret key
#   bash /opt/fonar/deploy/set-yookassa.sh --remove — switch payments off again
set -euo pipefail
umask 077  # .env and its temporary copy are readable by root only from the first byte
cd "$(dirname "$0")"
DC="docker compose"; docker compose version >/dev/null 2>&1 || DC="docker-compose"
touch .env
strip() { grep -vE '^(YOOKASSA_SHOP_ID|YOOKASSA_SECRET_KEY|PAYMENTS_TEST_MODE)=' .env > .env.tmp || true; }
if [ "${1:-}" = "--remove" ]; then
  strip; mv .env.tmp .env; chmod 600 .env
  $DC up -d --force-recreate api >/dev/null
  echo "Готово: оплата выключена, в приложении снова «Оплата скоро»."
  exit 0
fi
printf 'shopId магазина ЮKassa (цифры, из личного кабинета → Интеграция → Ключи API): '
read -r SHOP
SHOP="$(echo "$SHOP" | tr -d '[:space:]')"
case "$SHOP" in ''|*[!0-9]*) echo "shopId — это только цифры. Ничего не изменено."; exit 1 ;; esac
printf 'Секретный ключ (live_… или test_…) и Enter.\nСимволы при вставке не отображаются — так и должно быть: '
read -rs KEY
echo
KEY="$(echo "$KEY" | tr -d '[:space:]')"
case "$KEY" in live_*|test_*) ;; *) echo "Это не похоже на секретный ключ ЮKassa (live_… или test_…). Ничего не изменено."; exit 1 ;; esac
# the credentials go to curl through stdin, not the command line (the process list shows arguments to every user)
AUTH="$(printf '%s:%s' "$SHOP" "$KEY" | base64 -w0)"
CODE="$(printf 'Authorization: Basic %s\n' "$AUTH" | curl -s -o /dev/null -w '%{http_code}' -H @- https://api.yookassa.ru/v3/me || true)"
[ "$CODE" = "200" ] || { echo "ЮKassa не приняла shopId и ключ (HTTP $CODE). Ничего не изменено."; exit 1; }
strip
{ echo "YOOKASSA_SHOP_ID=$SHOP"; echo "YOOKASSA_SECRET_KEY=$KEY"; } >> .env.tmp
mv .env.tmp .env
chmod 600 .env
$DC up -d --force-recreate api >/dev/null
DOMAIN="$(grep -E '^DOMAIN=' .env | cut -d= -f2- || true)"
echo "Готово: оплата через ЮKassa включена."
echo "В личном кабинете ЮKassa → Интеграция → HTTP-уведомления укажи адрес:"
echo "  https://${DOMAIN:-твой-домен}/v1/payments/yookassa/webhook"
echo "и отметь событие payment.succeeded (и payment.canceled)."
case "$KEY" in test_*) echo "Это тестовый ключ: деньги не списываются. Для настоящих платежей запусти скрипт ещё раз с ключом live_…";; esac
