#!/bin/bash
# Виконується на сервері під час кожного запуску: встановлює/оновлює бота й запускає його.
set -euo pipefail

APP=/opt/ukrmovych_bot
DATA=/var/lib/ukrmovych_bot
REPO=https://github.com/ukrmovych/ukrmovych_bot.git
MD=http://metadata.google.internal/computeMetadata/v1/instance/attributes

# e2-micro має лише 1 ГБ пам'яті — додаємо swap
if [ ! -f /swapfile ]; then
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
swapon -a || true

if ! dpkg -s git python3-venv >/dev/null 2>&1; then
  apt-get update -q
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q git python3-venv
fi

id bot >/dev/null 2>&1 || useradd --system --home "$DATA" --shell /usr/sbin/nologin bot
mkdir -p "$DATA"
chown bot:bot "$DATA"

if [ -d "$APP/.git" ]; then
  git -C "$APP" fetch -q origin master
  git -C "$APP" reset -q --hard origin/master
else
  git clone -q "$REPO" "$APP"
fi
[ -x "$APP/.venv/bin/python" ] || python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q --upgrade -r "$APP/requirements.txt"

TOKEN=$(curl -fs -H 'Metadata-Flavor: Google' "$MD/bot-token" || true)
( umask 077
  printf 'BOT_TOKEN=%s\nDB_PATH=%s/bot.db\n' "$TOKEN" "$DATA" > "$DATA/.env" )
chown bot:bot "$DATA/.env"

install -m 644 "$APP"/deploy/systemd/* /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now ukrmovych-bot-update.timer
systemctl enable ukrmovych-bot.service
systemctl restart ukrmovych-bot.service
