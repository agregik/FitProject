#!/usr/bin/env bash
# Первый запуск: создаёт окружение, ставит зависимости, собирает сайт и поднимает всё на http://localhost:8000
#   ./start.sh --lan   — ещё и для телефона в той же Wi‑Fi сети (вход по QR в Настройках)
set -e
cd "$(dirname "$0")"

HOST=127.0.0.1
if [ "$1" = "--lan" ]; then
  LAN_IP=$(ipconfig getifaddr en0 || ipconfig getifaddr en1 || true)
  [ -n "$LAN_IP" ] || { echo "Не нашёл адрес в Wi‑Fi сети. Ноут подключён к Wi‑Fi?"; exit 1; }
  HOST=0.0.0.0
  export PUBLIC_URL="http://$LAN_IP:8000"   # куда ведёт QR-код для телефона
fi

if [ ! -f backend/.env ]; then
  cp backend/.env.example backend/.env
  echo "→ Создан backend/.env (демо-режим). Потом впишешь туда ключи WHOOP."
fi

if [ ! -d backend/.venv ]; then
  echo "→ Python-окружение…"
  python3 -m venv backend/.venv
fi
backend/.venv/bin/pip install -q -r backend/requirements.txt

echo "→ Сборка сайта…"
(cd web && npm install --silent && npm run build --silent)

echo ""
echo "✅ Открой http://localhost:8000"
if [ -n "$LAN_IP" ]; then
  echo "📱 Телефон в той же Wi‑Fi сети: $PUBLIC_URL"
  echo "   Настройки → «Подключить телефон» → «Показать QR-код». Сервер виден всем устройствам этой сети,"
  echo "   данные закрыты токеном. В кафе и чужих сетях запускай без --lan."
fi
echo ""
cd backend && exec .venv/bin/uvicorn app.main:app --host "$HOST" --port 8000
