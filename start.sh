#!/usr/bin/env bash
# Первый запуск: создаёт окружение, ставит зависимости, собирает сайт и поднимает всё на http://localhost:8000
set -e
cd "$(dirname "$0")"

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
echo ""
cd backend && exec .venv/bin/uvicorn app.main:app --port 8000
