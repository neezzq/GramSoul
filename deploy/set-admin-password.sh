#!/usr/bin/env bash
# Sets the password of the admin page https://<domain>/admin/ (users, spent tokens, players' photos).
# Only a scrypt hash is stored in deploy/.env (root-only); the password itself is never written anywhere.
set -euo pipefail
cd "$(dirname "$0")"
DC="docker compose"; docker compose version >/dev/null 2>&1 || DC="docker-compose"
read -rsp "Пароль для админки (не короче 10 символов): " P1; echo
read -rsp "Ещё раз: " P2; echo
[ "$P1" = "$P2" ] || { echo "Пароли не совпали."; exit 1; }
[ "${#P1}" -ge 10 ] || { echo "Слишком короткий пароль: нужно не меньше 10 символов."; exit 1; }
HASH="$(printf '%s' "$P1" | $DC exec -T api python -c 'import sys; from app.common import hash_password; print(hash_password(sys.stdin.read()))')"
case "$HASH" in scrypt:*) ;; *) echo "Не удалось посчитать хэш (API запущен?)."; exit 1 ;; esac
touch .env
chmod 600 .env
grep -v '^ADMIN_PASSWORD_HASH=' .env > .env.tmp || true
echo "ADMIN_PASSWORD_HASH=$HASH" >> .env.tmp
mv .env.tmp .env
chmod 600 .env
$DC up -d --force-recreate api >/dev/null
DOMAIN="$(grep -E '^DOMAIN=' .env | cut -d= -f2-)"
echo "Готово. Админка: https://${DOMAIN:-<домен>}/admin/"
