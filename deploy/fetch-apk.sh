#!/usr/bin/env bash
# Puts the latest published APK next to the landing page: https://<domain>/fonar.apk
set -euo pipefail
cd "$(dirname "$0")"
URL="${APK_URL:-https://github.com/neezzq/GramSoul/releases/latest/download/fonar.apk}"
mkdir -p site
if curl -fsSL --max-time 120 -o site/fonar.apk.tmp "$URL"; then
  mv site/fonar.apk.tmp site/fonar.apk
  echo "APK: $(du -h site/fonar.apk | cut -f1)"
else
  rm -f site/fonar.apk.tmp
  exit 1
fi
