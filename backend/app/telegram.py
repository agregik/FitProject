"""Telegram bot via long polling — runs inside the backend process, no extra services."""
import asyncio
import json
import logging
import secrets
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from . import coach, config, db, insights
from .days import build_days, parse_tags, today_for, today_summary

log = logging.getLogger("telegram")
API = "https://api.telegram.org/bot{token}/{method}"

HELP = (
    "Я присылаю утреннюю сводку WHOOP и веду журнал.\n\n"
    "Просто напиши, что было: «бокал вина #алкоголь», «кофе в 18:00 #кофе_поздно». "
    "Это попадёт в журнал за сегодня.\n\n"
    "/today — сводка на сегодня\n"
    "/week — итоги недели\n"
    "/insights — что влияет на твоё восстановление\n"
    "/ask вопрос — спросить AI-коуча\n"
    "/tags — быстрые теги"
)
QUICK_TAGS = ["алкоголь", "кофе_поздно", "поздний_ужин", "стресс", "сауна", "медитация", "болею", "путешествие"]


def enabled() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN)


async def call(method: str, **params) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(API.format(token=config.TELEGRAM_BOT_TOKEN, method=method), json=params)
        return r.json()


async def send(chat_id: int, text: str, **kw) -> None:
    for chunk in [text[i:i + 3900] for i in range(0, len(text), 3900)] or [""]:
        await call("sendMessage", chat_id=chat_id, text=chunk, parse_mode="HTML",
                   disable_web_page_preview=True, **kw)


def link_code(user_id: int) -> str:
    code = secrets.token_urlsafe(9)
    db.execute("UPDATE users SET tg_link_code=? WHERE id=?", (code, user_id))
    return code


def _emoji(rec):
    if rec is None:
        return "⚪️"
    return "🟢" if rec >= 67 else ("🟡" if rec >= 34 else "🔴")


def _delta(v, base, key, nd=0, invert=False):
    if v is None or key not in base:
        return ""
    diff = v - base[key]["mean"]
    good = diff < 0 if invert else diff > 0
    arrow = "↑" if diff > 0 else "↓"
    return f" ({arrow}{abs(diff):.{nd}f} {'👍' if good else ''})".replace(" )", ")")


def morning_text(user: dict) -> str:
    s = today_summary(user)
    d = s.get("day")
    if not d:
        return "Пока нет данных."
    b = s["baseline"]
    lines = [
        f"{_emoji(d.get('recovery'))} <b>Recovery {d.get('recovery') or 0:.0f}%</b>  ·  {d['date']}",
        f"HRV {d.get('hrv') or 0:.0f} мс{_delta(d.get('hrv'), b, 'hrv')}  ·  пульс {d.get('rhr') or 0:.0f}{_delta(d.get('rhr'), b, 'rhr', invert=True)}",
    ]
    if d.get("sleep_hours"):
        lines.append(f"😴 Сон {d['sleep_hours']:.1f} ч из {d.get('sleep_need_hours') or 0:.1f} нужных · {d.get('sleep_performance') or 0:.0f}%")
    t = s["strain_target"]
    if t["min"] is not None:
        lines.append(f"🎯 {t['label']}: strain {t['min']}–{t['max']}")
    if s.get("bedtime"):
        lines.append(f"🛏 Отбой сегодня около {s['bedtime']['bedtime']}")
    for a in s["alerts"]:
        lines.append(("⚠️ " if a["level"] == "warn" else "💡 ") + a["text"])
    prev = (date.fromisoformat(d["date"]) - timedelta(days=1)).isoformat()
    prev_days = build_days(user["id"], prev, prev)
    if prev_days and prev_days[0]["tags"]:
        lines.append("Вчера в журнале: " + " ".join("#" + t for t in prev_days[0]["tags"]))
    lines.append("\nНапиши, что было вчера вечером (алкоголь, поздний ужин, стресс), чтобы я учёл это в инсайтах.")
    return "\n".join(lines)


def week_text(user: dict) -> str:
    today = today_for(user)
    start = (date.fromisoformat(today) - timedelta(days=6)).isoformat()
    prev_start = (date.fromisoformat(today) - timedelta(days=13)).isoformat()
    days = build_days(user["id"], prev_start, today)
    cur = [d for d in days if d["date"] >= start]
    prev = [d for d in days if d["date"] < start]

    def avg(ds, k):
        v = [d[k] for d in ds if d.get(k) is not None]
        return sum(v) / len(v) if v else None

    def row(label, k, nd=0, unit=""):
        a, p = avg(cur, k), avg(prev, k)
        if a is None:
            return None
        ch = f" ({'+' if a - p >= 0 else ''}{a - p:.{nd}f} к прошлой)" if p is not None else ""
        return f"{label}: {a:.{nd}f}{unit}{ch}"

    lines = ["📊 <b>Итоги недели</b>"]
    for r in (row("Recovery", "recovery", 0, "%"), row("HRV", "hrv", 0, " мс"), row("Пульс в покое", "rhr", 0),
              row("Сон", "sleep_hours", 1, " ч"), row("Strain", "strain", 1)):
        if r:
            lines.append(r)
    wk = [w for d in cur for w in d["workouts"]]
    if wk:
        lines.append(f"Тренировок: {len(wk)}")
    best = max((d for d in cur if d.get("recovery") is not None), key=lambda d: d["recovery"], default=None)
    worst = min((d for d in cur if d.get("recovery") is not None), key=lambda d: d["recovery"], default=None)
    if best and worst:
        lines.append(f"Лучший день {best['date']} ({best['recovery']:.0f}%), худший {worst['date']} ({worst['recovery']:.0f}%)")
    heads = insights.headline(insights.compute(user["id"]), 2)
    if heads:
        lines.append("\n💡 " + "\n💡 ".join(heads))
    return "\n".join(lines)


async def _handle(msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    if not text:
        return
    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            u = db.row("SELECT id FROM users WHERE tg_link_code=?", (parts[1],))
            if u:
                db.execute("UPDATE users SET tg_chat_id=?, tg_link_code=NULL WHERE id=?", (chat_id, u["id"]))
                await send(chat_id, "✅ Аккаунт подключён!\n\n" + HELP)
                return
        await send(chat_id, "Чтобы подключить бота, нажми «Подключить Telegram» в настройках на сайте.")
        return
    u = db.row("SELECT id FROM users WHERE tg_chat_id=?", (chat_id,))
    if not u:
        await send(chat_id, "Сначала подключи аккаунт: сайт → Настройки → «Подключить Telegram».")
        return
    user = db.get_user(u["id"])
    cmd = text.split()[0].split("@")[0].lower()
    arg = text[len(text.split()[0]):].strip()
    if cmd in ("/help",):
        await send(chat_id, HELP)
    elif cmd == "/today":
        await send(chat_id, morning_text(user))
    elif cmd == "/week":
        await send(chat_id, week_text(user))
    elif cmd == "/insights":
        heads = insights.headline(insights.compute(user["id"]), 5)
        await send(chat_id, "\n\n".join("💡 " + h for h in heads) if heads else
                   "Пока мало данных. Веди журнал пару недель, и появятся закономерности.")
    elif cmd == "/ask":
        if not arg:
            await send(chat_id, "Напиши вопрос после /ask, например: /ask почему у меня падает HRV?")
            return
        await call("sendChatAction", chat_id=chat_id, action="typing")
        answer = await asyncio.to_thread(coach.ask, user, arg)
        await send(chat_id, answer)
    elif cmd == "/tags":
        kb = [[{"text": "#" + t, "callback_data": "tag:" + t} for t in QUICK_TAGS[i:i + 2]]
              for i in range(0, len(QUICK_TAGS), 2)]
        await call("sendMessage", chat_id=chat_id, text="Отметь, что было сегодня:",
                   reply_markup={"inline_keyboard": kb})
    elif cmd.startswith("/"):
        await send(chat_id, HELP)
    else:
        add_note(user, text, source="telegram")
        tags = parse_tags(text)
        await send(chat_id, "📝 Записал в журнал" + (": " + " ".join("#" + t for t in tags) if tags else "."))


def add_note(user: dict, text: str, day: str | None = None, source: str = "web") -> int:
    day = day or today_for(user)
    return db.execute(
        "INSERT INTO notes (user_id, day, text, tags, source, created_at) VALUES (?,?,?,?,?,?)",
        (user["id"], day, text, json.dumps(parse_tags(text), ensure_ascii=False), source, db.now_iso()),
    )


async def _handle_callback(cb: dict) -> None:
    chat_id = cb["message"]["chat"]["id"]
    u = db.row("SELECT id FROM users WHERE tg_chat_id=?", (chat_id,))
    data = cb.get("data", "")
    if u and data.startswith("tag:"):
        add_note(db.get_user(u["id"]), "#" + data[4:], source="telegram")
        await call("answerCallbackQuery", callback_query_id=cb["id"], text=f"#{data[4:]} записан")
    else:
        await call("answerCallbackQuery", callback_query_id=cb["id"])


async def poll_forever() -> None:
    if not enabled():
        return
    await call("setMyCommands", commands=[
        {"command": "today", "description": "Сводка на сегодня"},
        {"command": "week", "description": "Итоги недели"},
        {"command": "insights", "description": "Что влияет на восстановление"},
        {"command": "ask", "description": "Вопрос AI-коучу"},
        {"command": "tags", "description": "Быстрые теги"},
    ])
    offset = 0
    log.info("telegram bot polling started")
    while True:
        try:
            res = await call("getUpdates", offset=offset, timeout=50, allowed_updates=["message", "callback_query"])
            for upd in res.get("result", []):
                offset = upd["update_id"] + 1
                try:
                    if "message" in upd:
                        await _handle(upd["message"])
                    elif "callback_query" in upd:
                        await _handle_callback(upd["callback_query"])
                except Exception:  # noqa: BLE001
                    log.exception("telegram handler failed")
        except Exception:  # noqa: BLE001
            log.exception("telegram polling error")
            await asyncio.sleep(5)


async def push_scheduled(user_id: int) -> None:
    """Morning summary once today's recovery is scored; weekly report Sunday after 20:00."""
    if not enabled():
        return
    user = db.get_user(user_id)
    if not user or not user["tg_chat_id"]:
        return
    s = today_summary(user)
    d = s.get("day")
    if d and s.get("is_today") and d.get("recovery") is not None and db.mark_notified(user_id, "morning", d["date"]):
        await send(user["tg_chat_id"], morning_text(user))
    now = datetime.now(ZoneInfo(db.user_settings(user)["tz"]))
    if now.weekday() == 6 and now.hour >= 20:
        key = f"{now.isocalendar().year}-W{now.isocalendar().week}"
        if db.mark_notified(user_id, "weekly", key):
            await send(user["tg_chat_id"], week_text(user))
