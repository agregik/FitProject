#!/usr/bin/env bash
# Открывает сервер (localhost:8000) в интернет по HTTPS через бесплатный туннель Cloudflare,
# чтобы до него доставал телефон. Сервер (./start.sh) должен быть уже запущен.
# Адрес меняется при каждом запуске — после старта зайди в Настройки → «Подключить телефон».
# --protocol http2: QUIC (UDP) часто не проходит через VPN/прокси и корпоративные сети → Error 1033.
set -e
cd "$(dirname "$0")"
command -v cloudflared >/dev/null || { echo "Нужен cloudflared: brew install cloudflared"; exit 1; }

URL_FILE=backend/.public_url
rm -f "$URL_FILE"
trap 'rm -f "$URL_FILE"' EXIT

url=""
cloudflared tunnel --no-autoupdate --protocol http2 --url http://localhost:8000 2>&1 | while IFS= read -r line; do
  if [ -z "$url" ] && [[ $line =~ (https://[a-z0-9-]+\.trycloudflare\.com) ]]; then
    url="${BASH_REMATCH[1]}"
    echo "→ Адрес выдан, подключаюсь к Cloudflare…"
  fi
  # Publish the address only once the tunnel is actually connected (otherwise phones get Error 1033).
  if [[ $line == *"Registered tunnel connection"* ]] && [ -n "$url" ] && [ ! -s "$URL_FILE" ]; then
    echo "$url" > "$URL_FILE"
    echo ""
    echo "✅ Телефон: $url"
    echo "   Открой Настройки на компьютере → «Подключить телефон» и наведи камеру на QR."
    echo ""
  fi
  case $line in *ERR*) echo "$line" ;; esac
done
