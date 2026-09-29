"""AI coach on top of the user's own data (Claude API), with a rule-based fallback."""
import logging
from datetime import date, timedelta

from . import config, db, insights
from .days import build_days, today_for, today_summary

log = logging.getLogger("coach")

SYSTEM = """Ты — персональный коуч по восстановлению, сну и тренировкам. У тебя есть данные пользователя с WHOOP,
его журнал (заметки с #тегами) и нагрузка по календарю. Отвечай по-русски, коротко и конкретно:
сначала вывод, потом 2–4 пункта с цифрами из данных, потом одно практическое действие на сегодня или завтра.
Опирайся только на данные ниже; если данных мало, так и скажи. Корреляция — не причинность, говори об этом, когда уместно.
Ты не врач: при тревожных симптомах советуй обратиться к специалисту. Не придумывай метрики, которых нет в данных.
Формат: обычный текст, можно короткие списки, без таблиц."""


def _fmt(v, nd=0, suffix=""):
    if v is None:
        return "—"
    return f"{v:.{nd}f}{suffix}"


def build_context(user: dict) -> str:
    today = today_for(user)
    start = (date.fromisoformat(today) - timedelta(days=45)).isoformat()
    days = build_days(user["id"], start, today)
    summ = today_summary(user)
    ins = insights.compute(user["id"])
    lines = [f"Сегодня: {today}. Имя: {user.get('first_name') or 'пользователь'}."]
    base = summ.get("baseline") or {}
    if base:
        lines.append("Личная норма за 30 дней: " + ", ".join(
            f"{k}={v['mean']}±{v['sd']}" for k, v in base.items()))
    if summ.get("bedtime"):
        b = summ["bedtime"]
        lines.append(f"Потребность во сне сегодня: {b['need_hours']} ч, рекомендуемый отбой {b['bedtime']} при подъёме {b['wake_time']}.")
    for a in summ.get("alerts") or []:
        lines.append(f"Сигнал: {a['text']}")
    lines.append("\nПоследние дни (дата | recovery % | HRV мс | RHR | сон ч / нужно ч | сон % | strain | тренировки | встречи/поздние | теги и заметки):")
    for d in days[-21:]:
        wk = ", ".join(f"{w['sport']} {_fmt(w['strain'], 1)}" for w in d["workouts"]) or "—"
        notes = "; ".join(n["text"] for n in d["notes"])[:160] or "—"
        lines.append(
            f"{d['date']} | {_fmt(d.get('recovery'))} | {_fmt(d.get('hrv'))} | {_fmt(d.get('rhr'))} | "
            f"{_fmt(d.get('sleep_hours'), 1)}/{_fmt(d.get('sleep_need_hours'), 1)} | {_fmt(d.get('sleep_performance'))} | "
            f"{_fmt(d.get('strain'), 1)} | {wk} | {d.get('meetings', '—')}/{d.get('late_events', '—')} | {notes}"
        )
    heads = insights.headline(ins, limit=5)
    if heads:
        lines.append("\nНайденные закономерности (180 дней):")
        lines += [f"- {h}" for h in heads]
    wd = [f"{w['weekday']} {_fmt(w['recovery'])}" for w in ins["weekday"] if w["recovery"] is not None]
    if wd:
        lines.append("Средний recovery по дням недели: " + ", ".join(wd))
    return "\n".join(lines)


def _fallback(user: dict, question: str) -> str:
    s = today_summary(user)
    d = s.get("day") or {}
    ins = insights.compute(user["id"])
    parts = [
        f"Recovery {_fmt(d.get('recovery'))}%, HRV {_fmt(d.get('hrv'))} мс, сон {_fmt(d.get('sleep_hours'), 1)} ч.",
        f"Рекомендация по нагрузке: {s['strain_target']['label'].lower()}"
        + (f" (strain {s['strain_target']['min']}–{s['strain_target']['max']})." if s['strain_target']['min'] is not None else "."),
    ]
    if s.get("bedtime"):
        parts.append(f"Чтобы выспаться, ложись около {s['bedtime']['bedtime']}.")
    for a in s.get("alerts") or []:
        parts.append(a["text"])
    heads = insights.headline(ins, 3)
    if heads:
        parts.append("Что влияет на тебя сильнее всего:\n" + "\n".join(f"• {h}" for h in heads))
    parts.append("\n(Упрощённый режим: добавь ANTHROPIC_API_KEY в .env, и коуч будет отвечать на любые вопросы.)")
    return "\n".join(parts)


def history(user_id: int, limit: int = 30) -> list[dict]:
    rows = db.rows(
        "SELECT role, content, created_at FROM coach_messages WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    )
    return list(reversed(rows))


def ask(user: dict, question: str, keep_history: bool = True) -> str:
    question = question.strip()
    if not config.ANTHROPIC_API_KEY:
        answer = _fallback(user, question)
    else:
        import anthropic

        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        msgs = []
        if keep_history:
            for m in history(user["id"], 10):
                msgs.append({"role": m["role"], "content": m["content"]})
        msgs.append({"role": "user", "content": question})
        try:
            resp = client.messages.create(
                model=config.COACH_MODEL,
                max_tokens=1200,
                system=[{"type": "text", "text": SYSTEM},
                        {"type": "text", "text": "ДАННЫЕ ПОЛЬЗОВАТЕЛЯ:\n" + build_context(user)}],
                messages=msgs,
            )
            answer = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        except Exception as e:  # noqa: BLE001
            log.exception("coach failed")
            answer = f"Не получилось спросить модель ({e.__class__.__name__}). Вот сводка по данным:\n\n" + _fallback(user, question)
    if keep_history:
        now = db.now_iso()
        db.execute("INSERT INTO coach_messages (user_id, role, content, created_at) VALUES (?,?,?,?)",
                   (user["id"], "user", question, now))
        db.execute("INSERT INTO coach_messages (user_id, role, content, created_at) VALUES (?,?,?,?)",
                   (user["id"], "assistant", answer, now))
    return answer
