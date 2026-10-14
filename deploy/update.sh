#!/bin/bash
# Кожні 5 хвилин: якщо на GitHub з'явився новий код — оновлює й перезапускає бота.
set -euo pipefail
APP=/opt/ukrmovych_bot
cd "$APP"
git fetch -q origin master
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/master)" ] && exit 0
git reset -q --hard origin/master
.venv/bin/pip install -q --upgrade -r requirements.txt
install -m 644 deploy/systemd/* /etc/systemd/system/
systemctl daemon-reload
systemctl restart ukrmovych-bot.service
echo "Оновлено до $(git rev-parse --short HEAD)"
