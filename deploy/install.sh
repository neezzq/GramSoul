#!/usr/bin/env bash
# Fonar backend installer for a fresh Debian 13 VPS (also works on Debian 12 / Ubuntu 22.04+).
#
#   curl -fsSL https://raw.githubusercontent.com/neezzq/GramSoul/refs/heads/<branch>/deploy/install.sh | sudo bash
#   ... | sudo bash -s -- --domain my.domain.com      # with your own domain (A record -> this VPS)
#
# Without --domain the address <ip-with-dashes>.sslip.io is used: it resolves to this
# VPS and gets a real Let's Encrypt certificate, so no domain purchase is needed.
# Safe to run again: it updates the code and keeps data and settings.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/neezzq/GramSoul.git}"
BRANCH="${BRANCH:-}"
DIR="${FONAR_DIR:-/opt/fonar}"
DOMAIN="${DOMAIN:-}"
SKIP_BENCH="${SKIP_BENCH:-0}"

while [ $# -gt 0 ]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --skip-bench) SKIP_BENCH=1; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

log() { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mОШИБКА: %s\033[0m\n' "$*"; exit 1; }

[ "$(id -u)" -eq 0 ] || die "запусти от root (sudo bash ...)"

log "Пакеты"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl git cron >/dev/null

if ! command -v docker >/dev/null 2>&1; then
  log "Устанавливаю Docker"
  if ! curl -fsSL https://get.docker.com | sh; then
    apt-get install -y -qq docker.io docker-compose >/dev/null || die "не удалось установить Docker"
  fi
fi
systemctl enable --now docker >/dev/null 2>&1 || true
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  apt-get install -y -qq docker-compose-plugin >/dev/null 2>&1 || apt-get install -y -qq docker-compose >/dev/null
  if docker compose version >/dev/null 2>&1; then DC="docker compose"; else DC="docker-compose"; fi
fi

# 2 GB RAM: a swap file keeps the model + build from being OOM-killed
if [ "$(swapon --show --noheadings | wc -l)" -eq 0 ]; then
  log "Создаю swap 2 ГБ"
  fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none
  chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  sysctl -w vm.swappiness=10 >/dev/null; echo 'vm.swappiness=10' > /etc/sysctl.d/99-fonar.conf
fi

log "Код проекта"
if [ -z "$BRANCH" ]; then
  if git ls-remote --exit-code --heads "$REPO_URL" main >/dev/null 2>&1; then BRANCH=main; else BRANCH=claude/great-keller-r937dd; fi
fi
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" fetch --depth 1 origin "$BRANCH"
  git -C "$DIR" checkout -q -B "$BRANCH" FETCH_HEAD
else
  git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$DIR"
fi
cd "$DIR/deploy"

log "Настройки"
if [ ! -f .env ]; then cp .env.example .env; chmod 600 .env; fi
if [ -z "$DOMAIN" ]; then
  DOMAIN="$(grep -E '^DOMAIN=' .env | cut -d= -f2- || true)"
fi
if [ -z "$DOMAIN" ]; then
  IP="$(curl -4 -fsS --max-time 10 https://api.ipify.org || curl -4 -fsS --max-time 10 https://ifconfig.me || true)"
  [ -n "$IP" ] || die "не удалось определить внешний IP; передай --domain"
  DOMAIN="$(echo "$IP" | tr '.' '-').sslip.io"
fi
sed -i "s|^DOMAIN=.*|DOMAIN=${DOMAIN}|" .env
MODEL="$(grep -E '^LLM_MODEL=' .env | cut -d= -f2- | awk '{print $1}')"
MODEL="${MODEL:-qwen2.5:0.5b}"
mkdir -p data/api data/ollama data/caddy data/caddy-config site backups
chown -R 10001:10001 data/api

if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
  ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
fi

log "Запускаю контейнеры (первая сборка займёт несколько минут)"
$DC up -d --build --remove-orphans

log "Загружаю модель $MODEL"
for i in $(seq 1 30); do
  $DC exec -T ollama ollama list >/dev/null 2>&1 && break
  sleep 2
done
$DC exec -T ollama ollama pull "$MODEL"
$DC restart api >/dev/null

log "APK для скачивания"
bash "$DIR/deploy/fetch-apk.sh" || echo "APK пока не опубликован — скачай его из чата и положи в $DIR/deploy/site/fonar.apk"

log "Резервные копии каждую ночь"
cat > /etc/cron.d/fonar-backup <<CRON
SHELL=/bin/bash
17 4 * * * root bash $DIR/deploy/backup.sh >> /var/log/fonar-backup.log 2>&1
CRON
chmod 644 /etc/cron.d/fonar-backup

log "Жду HTTPS-сертификат для $DOMAIN"
OK=0
for i in $(seq 1 60); do
  if curl -fsS --max-time 5 "https://$DOMAIN/v1/health" >/dev/null 2>&1; then OK=1; break; fi
  sleep 3
done
[ "$OK" = 1 ] || echo "HTTPS пока не отвечает: проверь, что порты 80 и 443 открыты у хостера, и запусти скрипт ещё раз."

if [ "$SKIP_BENCH" != 1 ]; then
  log "Замер скорости модели и памяти"
  bash "$DIR/deploy/bench.sh" || true
fi

cat <<EOF

========================================================
 Готово. Адрес сервера:  https://$DOMAIN
 Проверка:               https://$DOMAIN/v1/health
 Страница для друга:     https://$DOMAIN/   (ссылка на APK)
 Настройки модели:       $DIR/deploy/.env
 Обновление:             bash $DIR/deploy/update.sh
 Бэкап вручную:          bash $DIR/deploy/backup.sh
========================================================
EOF
