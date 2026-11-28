#!/usr/bin/env bash
# Deletes the backups made before encryption at rest was switched on (their database and pictures are readable
# by anyone who gets the file). Keeps every encrypted backup; does nothing unless at least one exists.
#   bash /opt/fonar/deploy/purge-unencrypted-backups.sh
set -euo pipefail
cd "$(dirname "$0")"
shopt -s nullglob
plain=() enc=()
for a in backups/fonar-*.tar.gz; do
  if [ "$(tar -xOzf "$a" backup.sqlite3 2>/dev/null | head -c 15)" = "SQLite format 3" ]; then plain+=("$a"); else enc+=("$a"); fi
done
echo "Зашифрованных резервных копий: ${#enc[@]}, незашифрованных: ${#plain[@]}."
[ "${#plain[@]}" -gt 0 ] || { echo "Удалять нечего."; exit 0; }
[ "${#enc[@]}" -gt 0 ] || { echo "Сначала сделай зашифрованную копию: bash backup.sh — пока ничего не удаляю."; exit 1; }
printf '  %s\n' "${plain[@]}"
read -rp "Удалить эти незашифрованные копии? Напиши «да»: " ok
[ "$ok" = "да" ] || { echo "Ничего не удалено."; exit 0; }
rm -f -- "${plain[@]}"
echo "Удалено: ${#plain[@]}."
