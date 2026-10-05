#!/usr/bin/env bash
# Открывает сервер (localhost:8000) в интернет по HTTPS через бесплатный туннель Cloudflare,
# чтобы до него доставал телефон. Сервер (./start.sh) должен быть уже запущен.
# Адрес меняется при каждом запуске — после старта зайди в Настройки → «Подключить телефон».
set -e
cd "$(dirname "$0")"
command -v cloudflared >/dev/null || { echo "Нужен cloudflared: brew install cloudflared"; exit 1; }

URL_FILE=backend/.public_url
rm -f "$URL_FILE"
trap 'rm -f "$URL_FILE"' EXIT

cloudflared tunnel --no-autoupdate --url http://localhost:8000 2>&1 | while IFS= read -r line; do
  if [ ! -s "$URL_FILE" ] && [[ $line =~ (https://[a-z0-9-]+\.trycloudflare\.com) ]]; then
    echo "${BASH_REMATCH[1]}" > "$URL_FILE"
    echo ""
    echo "✅ Телефон: ${BASH_REMATCH[1]}"
    echo "   Открой Настройки на компьютере → «Подключить телефон» и наведи камеру на QR."
    echo ""
  fi
  case $line in *ERR*|*error*) echo "$line" ;; esac
done
