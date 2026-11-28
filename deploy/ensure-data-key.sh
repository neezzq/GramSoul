#!/usr/bin/env bash
# Makes sure deploy/.env has DATA_KEY — the key that encrypts the database, the pictures and the voice-over audio
# on this server (app/crypto.py). Generated once; never replaced (data encrypted with it would become unreadable).
# Called by install.sh and update.sh. The key is printed only by show-data-key.sh, never here.
set -euo pipefail
umask 077
cd "$(dirname "$0")"
touch .env
chmod 600 .env
if grep -qE '^DATA_KEY=.{40,}' .env; then
  exit 0
fi
KEY="$(head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '=\n')"
grep -v '^DATA_KEY=' .env > .env.tmp || true
echo "DATA_KEY=$KEY" >> .env.tmp
mv .env.tmp .env
chmod 600 .env
cat <<MSG

================================================================================
  Включено шифрование данных на сервере (база, картинки, озвучка).
  Создан ключ шифрования DATA_KEY в $(pwd)/.env

  ОБЯЗАТЕЛЬНО сохрани его отдельно от сервера (менеджер паролей, заметка
  в надёжном месте): без ключа ни данные, ни резервные копии не прочитать.
  Показать ключ:   bash $(pwd)/show-data-key.sh
================================================================================

MSG
