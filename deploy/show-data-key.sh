#!/usr/bin/env bash
# Prints the encryption key of this server's data (DATA_KEY), to save it in a password manager.
# Keep it secret: with the key and a copy of the data anyone can read everything.
set -euo pipefail
cd "$(dirname "$0")"
KEY="$(grep -E '^DATA_KEY=' .env 2>/dev/null | cut -d= -f2- || true)"
[ -n "$KEY" ] || { echo "Ключа нет: шифрование ещё не включено (запусти update.sh)."; exit 1; }
echo "Ключ шифрования данных (сохрани в менеджере паролей, никому не показывай):"
echo
echo "DATA_KEY=$KEY"
echo
echo "Восстановить на новом сервере: вписать эту строку в deploy/.env до запуска restore.sh."
