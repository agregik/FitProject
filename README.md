# FitProject

Надстройка над WHOOP: тренды, свой журнал привычек, инсайты «что влияет на моё восстановление»,
AI-коуч, календарь и Telegram-бот. Зачем это нужно и что входит в MVP, описано в [SPEC.md](SPEC.md).

## Быстрый старт (демо, 2 минуты)

Нужны Python 3.11+ и Node 18+ (`brew install python node`).

```bash
cd ~/Desktop/FitProject
chmod +x start.sh
./start.sh
```

Открой http://localhost:8000. Там будет 180 дней синтетических данных, чтобы потрогать всё до подключения WHOOP.

### Режим разработки (горячая перезагрузка)

```bash
# терминал 1: backend
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000
# терминал 2: сайт
cd web && npm run dev          # http://localhost:5173, API проксируется на :8000
```

В режиме разработки поставь в `backend/.env` `WEB_URL=http://localhost:5173`. Если запускаешь через `start.sh` (один порт), нужен `WEB_URL=http://localhost:8000`.

## Подключение настоящего WHOOP

1. Зайди на https://developer-dashboard.whoop.com под своим аккаунтом WHOOP и создай Team, затем App.
2. **Redirect URL:** `http://localhost:8000/auth/callback`.
3. **Scopes:** отметь все `read:*` и `offline`.
4. Скопируй Client ID и Client Secret в `backend/.env`. Там же поставь `DEMO_MODE=0` (или оставь 1, демо не мешает).
5. Перезапусти backend, открой сайт → Настройки → «Подключить WHOOP». После входа подтянется вся история, это займёт минуту-две.

Данные обновляются раз в час и по кнопке «Синхронизировать сейчас».

**Вебхуки** (мгновенное обновление, когда посчитан recovery): им нужен публичный HTTPS-адрес. Локально можно так:
`brew install cloudflared && cloudflared tunnel --url http://localhost:8000`. Полученный адрес + `/webhooks/whoop`
впиши в дашборд WHOOP как Webhook URL (версия v2).

## AI-коуч

Получи ключ на https://console.anthropic.com и впиши `ANTHROPIC_API_KEY=` в `backend/.env`.
Без ключа коуч работает в упрощённом режиме, на правилах.

## Telegram-бот

1. Напиши @BotFather → `/newbot` и получи токен.
2. Впиши в `backend/.env` `TELEGRAM_BOT_TOKEN=` и `TELEGRAM_BOT_USERNAME=` (имя без @).
3. Перезапусти backend. Сайт → Настройки → «Подключить Telegram».

Что умеет бот:
- утренняя сводка, как только посчитан recovery: зона, HRV и пульс относительно нормы, целевой strain, время отбоя, предупреждения;
- любое сообщение становится записью в журнал, `#теги` распознаются; `/tags` — быстрые теги кнопками;
- `/today`, `/week`, `/insights`, `/ask вопрос`;
- итоги недели в воскресенье вечером.

Бот работает через long polling, то есть и локально, без публичного адреса.

## Календарь

Сайт → Настройки → Календарь → вставь секретную ICS-ссылку (Google: настройки календаря → «Секретный адрес в формате iCal»).

## Структура

```
backend/app/
  main.py          FastAPI: API, OAuth, вебхуки, фоновая синхронизация
  whoop.py         WHOOP API v2: OAuth, refresh, пагинация, сохранение
  days.py          сборка «дня» из всех источников, нормы, рекомендации, сигналы
  insights.py      влияние тегов/сна/нагрузки/календаря на recovery (перестановочный тест, корреляции)
  coach.py         AI-коуч на Claude + контекст из данных
  telegram.py      бот
  calendar_ics.py  импорт ICS
  demo.py          генератор демо-данных
  db.py            SQLite (схема сразу мультипользовательская)
web/src/
  pages/           Сегодня, Тренды, Журнал, Инсайты, Коуч, Настройки
```

## API для iOS (этап 2)

Все эндпоинты `/api/*` принимают `Authorization: Bearer <api_token>` (токен в Настройках).
Для виджета есть компактный `GET /api/widget`.

## Git

```bash
git init && git add . && git commit -m "FitProject MVP"
gh repo create fitproject --private --source=. --push   # если стоит GitHub CLI
```
