#!/usr/bin/env bash
# Створює безкоштовний сервер Google Cloud (e2-micro) і запускає на ньому бота.
# Запуск у Google Cloud Shell:
#   bash <(curl -fsSL https://raw.githubusercontent.com/ukrmovych/ukrmovych_bot/master/deploy/gcloud-create.sh)
set -euo pipefail

NAME=ukrmovych-bot
ZONE=us-central1-a   # лише us-west1 / us-central1 / us-east1 входять у безкоштовний тариф
RAW=https://raw.githubusercontent.com/ukrmovych/ukrmovych_bot/master

say() { printf '\n\033[1;32m%s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31m❌ %s\033[0m\n' "$*"; exit 1; }

PROJECT=$(gcloud config get-value project 2>/dev/null || true)
if [ -z "$PROJECT" ]; then
  PROJECT=$(gcloud projects list --format='value(projectId)' --limit=1)
  [ -n "$PROJECT" ] || fail "Не знайдено жодного проєкту. Створи проєкт у консолі Google Cloud і запусти скрипт ще раз."
  gcloud config set project "$PROJECT" >/dev/null
fi
say "Проєкт: $PROJECT"

read -rsp "Встав токен бота від @BotFather і натисни Enter (символи не відображатимуться): " TOKEN </dev/tty
echo
TOKEN=$(printf '%s' "$TOKEN" | tr -d '[:space:]')
curl -fsS "https://api.telegram.org/bot${TOKEN}/getMe" | grep -q '"ok":true' \
  || fail "Telegram не прийняв цей токен. Перевір його в @BotFather і спробуй ще раз."
say "Токен підходить ✅"

say "Вмикаю Compute Engine (може зайняти хвилину)..."
gcloud services enable compute.googleapis.com \
  || fail "Не вдалося ввімкнути Compute Engine. Перевір, що до проєкту прив'язано платіжний акаунт (Billing)."

BOOT=$(mktemp)
TOKFILE=$(mktemp)
trap 'rm -f "$BOOT" "$TOKFILE"' EXIT
# Під час кожного запуску сервер бере найсвіжіший startup.sh з GitHub
printf '#!/bin/bash\ncurl -fsSL %s/deploy/startup.sh | bash\n' "$RAW" > "$BOOT"
printf '%s' "$TOKEN" > "$TOKFILE"

if gcloud compute instances describe "$NAME" --zone "$ZONE" >/dev/null 2>&1; then
  say "Сервер уже є — оновлюю токен і перезапускаю..."
  gcloud compute instances add-metadata "$NAME" --zone "$ZONE" \
    --metadata-from-file=bot-token="$TOKFILE",startup-script="$BOOT"
  gcloud compute instances reset "$NAME" --zone "$ZONE"
else
  say "Створюю безкоштовний сервер..."
  gcloud compute instances create "$NAME" \
    --zone="$ZONE" \
    --machine-type=e2-micro \
    --image-family=debian-12 --image-project=debian-cloud \
    --boot-disk-size=30GB --boot-disk-type=pd-standard \
    --metadata-from-file=bot-token="$TOKFILE",startup-script="$BOOT"
fi

say "Налаштовую сповіщення на пошту, якщо з'являться бодай якісь витрати..."
BILLING=$(gcloud billing projects describe "$PROJECT" --format='value(billingAccountName)' 2>/dev/null | sed 's#billingAccounts/##' || true)
if [ -n "$BILLING" ] \
  && gcloud services enable billingbudgets.googleapis.com >/dev/null 2>&1 \
  && ! gcloud billing budgets list --billing-account="$BILLING" --format='value(displayName)' 2>/dev/null | grep -qx ukrmovych-bot; then
  gcloud billing budgets create --billing-account="$BILLING" --display-name=ukrmovych-bot \
    --budget-amount=1USD --threshold-rule=percent=0.01 >/dev/null 2>&1 \
    && echo "Готово: лист прийде, щойно витрати перевищать 0,01 \$." \
    || echo "Не вийшло — це не критично, бот працюватиме."
fi

say "🎉 Готово! За 3–5 хвилин бот запрацює — напиши йому /start у Telegram."
