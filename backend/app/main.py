import asyncio
import csv
import io
import json
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import calendar_ics, coach, config, db, demo, insights, telegram, training, whoop
from .days import build_days, today_for, today_summary

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("app")
COOKIE = "fp_token"


async def _sync_all_loop():
    ticks = 0
    while True:
        try:
            if ticks % max(1, config.SYNC_INTERVAL_SEC // 60) == 0:
                for u in db.rows("SELECT id FROM users WHERE is_demo=0 AND refresh_token IS NOT NULL"):
                    try:
                        await whoop.sync_user(u["id"])
                        await calendar_ics.sync_calendar(u["id"])
                    except Exception:  # noqa: BLE001
                        log.exception("sync failed for user %s", u["id"])
            for u in db.rows("SELECT id FROM users WHERE tg_chat_id IS NOT NULL"):
                await telegram.push_scheduled(u["id"])
        except Exception:  # noqa: BLE001
            log.exception("background loop error")
        ticks += 1
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    if config.DEMO_MODE and not db.row("SELECT id FROM users WHERE is_demo=1"):
        log.info("seeding demo data…")
        demo.seed()
    tasks = [asyncio.create_task(_sync_all_loop())]
    if telegram.enabled():
        tasks.append(asyncio.create_task(telegram.poll_forever()))
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="FitProject", lifespan=lifespan)


# ---------- auth ----------

def current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE)
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    u = db.row("SELECT id FROM users WHERE api_token=?", (token,)) if token else None
    if not u and config.DEMO_MODE:
        u = db.row("SELECT id FROM users WHERE is_demo=1")
    if not u:
        raise HTTPException(401, "not_logged_in")
    return db.get_user(u["id"])


@app.get("/auth/login")
def login():
    if not config.WHOOP_CLIENT_ID:
        raise HTTPException(400, "WHOOP_CLIENT_ID не задан в backend/.env")
    state = secrets.token_urlsafe(16)
    resp = RedirectResponse(whoop.auth_url(state))
    resp.set_cookie("oauth_state", state, max_age=600, httponly=True, samesite="lax")
    return resp


@app.get("/auth/callback")
async def callback(request: Request, bg: BackgroundTasks, code: str | None = None, state: str | None = None,
                   error: str | None = None):
    if error:
        return RedirectResponse(f"{config.WEB_URL}/?error={error}")
    if not code or state != request.cookies.get("oauth_state"):
        raise HTTPException(400, "Неверный state OAuth, попробуй войти ещё раз")
    uid = await whoop.login_with_code(code)
    u = db.get_user(uid)
    bg.add_task(whoop.sync_user, uid, u["last_sync_at"] is None)
    resp = RedirectResponse(f"{config.WEB_URL}/?connected=1")
    resp.set_cookie(COOKIE, u["api_token"], max_age=3600 * 24 * 365, httponly=True, samesite="lax")
    resp.delete_cookie("oauth_state")
    return resp


@app.post("/auth/logout")
def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE)
    return resp


@app.get("/api/me")
def me(user=Depends(current_user)):
    return {
        "id": user["id"], "first_name": user["first_name"], "last_name": user["last_name"], "email": user["email"],
        "is_demo": bool(user["is_demo"]), "last_sync_at": user["last_sync_at"],
        "telegram_linked": bool(user["tg_chat_id"]), "telegram_enabled": telegram.enabled(),
        "whoop_configured": bool(config.WHOOP_CLIENT_ID), "coach_ai": bool(config.ANTHROPIC_API_KEY),
        "ics_urls": user["ics_urls"], "settings": db.user_settings(user),
        "api_token": user["api_token"],  # for the iOS app / widget setup
    }


class SettingsIn(BaseModel):
    tz: str | None = None
    wake_time: str | None = None


@app.patch("/api/settings")
def update_settings(body: SettingsIn, user=Depends(current_user)):
    s = user["settings"]
    s.update({k: v for k, v in body.model_dump().items() if v})
    db.execute("UPDATE users SET settings=? WHERE id=?", (json.dumps(s), user["id"]))
    return db.user_settings(db.get_user(user["id"]))


# ---------- data ----------

@app.post("/api/sync")
async def sync(user=Depends(current_user)):
    if user["is_demo"]:
        return {"demo": True}
    counts = await whoop.sync_user(user["id"])
    counts["events"] = await calendar_ics.sync_calendar(user["id"])
    await telegram.push_scheduled(user["id"])
    return counts


@app.get("/api/today")
def today(user=Depends(current_user)):
    return today_summary(user)


@app.get("/api/days")
def days(start: str | None = None, end: str | None = None, user=Depends(current_user)):
    end = end or today_for(user)
    start = start or (date.fromisoformat(end) - timedelta(days=90)).isoformat()
    return build_days(user["id"], start, end)


@app.get("/api/insights")
def get_insights(days: int = 180, user=Depends(current_user)):
    return insights.compute(user["id"], days)


@app.get("/api/widget")
def widget(user=Depends(current_user)):
    """Compact payload for iOS widgets."""
    s = today_summary(user)
    d = s.get("day") or {}
    return {
        "date": d.get("date"), "recovery": d.get("recovery"), "hrv": d.get("hrv"), "rhr": d.get("rhr"),
        "sleep_hours": d.get("sleep_hours"), "sleep_performance": d.get("sleep_performance"),
        "strain": d.get("strain"), "strain_target": s.get("strain_target"),
        "bedtime": (s.get("bedtime") or {}).get("bedtime"),
        "last7": s.get("last7"),
    }


# ---------- journal ----------

class NoteIn(BaseModel):
    text: str
    day: str | None = None


@app.get("/api/notes")
def list_notes(start: str | None = None, end: str | None = None, user=Depends(current_user)):
    end = end or today_for(user)
    start = start or (date.fromisoformat(end) - timedelta(days=30)).isoformat()
    rows = db.rows("SELECT id, day, text, tags, source, created_at FROM notes WHERE user_id=? AND day BETWEEN ? AND ? "
                   "ORDER BY day DESC, id DESC", (user["id"], start, end))
    for r in rows:
        r["tags"] = json.loads(r["tags"])
    return rows


@app.post("/api/notes")
def create_note(body: NoteIn, user=Depends(current_user)):
    if not body.text.strip():
        raise HTTPException(400, "Пустая заметка")
    nid = telegram.add_note(user, body.text.strip(), body.day)
    return {"id": nid}


@app.delete("/api/notes/{note_id}")
def delete_note(note_id: int, user=Depends(current_user)):
    db.execute("DELETE FROM notes WHERE id=? AND user_id=?", (note_id, user["id"]))
    return {"ok": True}


@app.get("/api/tags")
def tags(user=Depends(current_user)):
    counts = {}
    for r in db.rows("SELECT tags FROM notes WHERE user_id=?", (user["id"],)):
        for t in json.loads(r["tags"]):
            counts[t] = counts.get(t, 0) + 1
    quick = [t for t in telegram.QUICK_TAGS if t not in counts]
    return [{"tag": t, "count": n} for t, n in sorted(counts.items(), key=lambda x: -x[1])] + \
           [{"tag": t, "count": 0} for t in quick]


# ---------- strength training ----------

class SetIn(BaseModel):
    weight_kg: float | None = Field(None, ge=0, le=1000)
    reps: int = Field(..., ge=1, le=200)
    rir: int | None = Field(None, ge=0, le=10)


class LiftItemIn(BaseModel):
    exercise: str = Field(..., min_length=1, max_length=80)
    muscle_group: str | None = None
    sets: list[SetIn] = Field(..., min_length=1, max_length=30)


class LiftSessionIn(BaseModel):
    day: str | None = None
    title: str | None = Field(None, max_length=80)
    notes: str | None = Field(None, max_length=1000)
    items: list[LiftItemIn] = Field(..., min_length=1, max_length=30)


def _save_lift(body: LiftSessionIn, user: dict, session_id: int | None = None) -> dict:
    day = body.day or today_for(user)
    try:
        date.fromisoformat(day)
    except ValueError:
        raise HTTPException(400, "Неверная дата")
    try:
        sid = training.save_session(user["id"], day, body.title, body.notes,
                                    [i.model_dump() for i in body.items], session_id)
    except KeyError:
        raise HTTPException(404, "Тренировка не найдена")
    return {"id": sid}


@app.get("/api/training/exercises")
def lift_exercises(user=Depends(current_user)):
    return {"exercises": training.exercises(user["id"]), "groups": training.MUSCLE_GROUPS}


@app.get("/api/training/sessions")
def lift_sessions(start: str | None = None, end: str | None = None, user=Depends(current_user)):
    end = end or today_for(user)
    start = start or (date.fromisoformat(end) - timedelta(days=90)).isoformat()
    return training.sessions(user["id"], start, end)


@app.post("/api/training/sessions")
def lift_create(body: LiftSessionIn, user=Depends(current_user)):
    return _save_lift(body, user)


@app.put("/api/training/sessions/{session_id}")
def lift_update(session_id: int, body: LiftSessionIn, user=Depends(current_user)):
    return _save_lift(body, user, session_id)


@app.delete("/api/training/sessions/{session_id}")
def lift_delete(session_id: int, user=Depends(current_user)):
    training.delete_session(user["id"], session_id)
    return {"ok": True}


@app.get("/api/training/progress/{exercise_id}")
def lift_progress(exercise_id: int, user=Depends(current_user)):
    try:
        return training.progress(user["id"], exercise_id)
    except KeyError:
        raise HTTPException(404, "Упражнение не найдено")


# ---------- coach ----------

class AskIn(BaseModel):
    question: str


@app.get("/api/coach/history")
def coach_history(user=Depends(current_user)):
    return coach.history(user["id"], 50)


@app.post("/api/coach")
async def coach_ask(body: AskIn, user=Depends(current_user)):
    answer = await asyncio.to_thread(coach.ask, user, body.question)
    return {"answer": answer, "ai": bool(config.ANTHROPIC_API_KEY)}


@app.delete("/api/coach/history")
def coach_clear(user=Depends(current_user)):
    db.execute("DELETE FROM coach_messages WHERE user_id=?", (user["id"],))
    return {"ok": True}


# ---------- integrations ----------

class CalendarIn(BaseModel):
    urls: list[str]


@app.post("/api/calendar")
async def set_calendar(body: CalendarIn, user=Depends(current_user)):
    urls = [u.strip() for u in body.urls if u.strip()]
    db.execute("UPDATE users SET ics_urls=? WHERE id=?", (json.dumps(urls), user["id"]))
    n = await calendar_ics.sync_calendar(user["id"]) if urls else 0
    return {"events": n}


@app.post("/api/telegram/link")
def telegram_link(user=Depends(current_user)):
    if not telegram.enabled():
        raise HTTPException(400, "TELEGRAM_BOT_TOKEN не задан в backend/.env")
    code = telegram.link_code(user["id"])
    return {"url": f"https://t.me/{config.TELEGRAM_BOT_USERNAME}?start={code}", "code": code}


@app.get("/api/export.csv")
def export_csv(user=Depends(current_user)):
    rows = build_days(user["id"])
    cols = ["date", "recovery", "hrv", "rhr", "spo2", "skin_temp", "resp_rate", "sleep_hours", "sleep_need_hours",
            "sleep_performance", "sleep_efficiency", "deep_hours", "rem_hours", "strain", "kj", "meetings",
            "busy_hours", "late_events"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols + ["workouts", "tags", "notes"])
    for d in rows:
        w.writerow([d.get(c) for c in cols] + [
            "; ".join(f"{x['sport']} {x['strain']}" for x in d["workouts"]),
            " ".join("#" + t for t in d["tags"]),
            " | ".join(n["text"] for n in d["notes"]),
        ])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=fitproject.csv"})


@app.post("/webhooks/whoop")
async def whoop_webhook(request: Request, bg: BackgroundTasks):
    raw = await request.body()
    if not whoop.verify_webhook(raw, request.headers.get("X-WHOOP-Signature"),
                                request.headers.get("X-WHOOP-Signature-Timestamp")):
        raise HTTPException(401, "bad signature")
    payload = json.loads(raw)

    async def work():
        uid = await whoop.handle_webhook(payload)
        if uid:
            await telegram.push_scheduled(uid)

    bg.add_task(work)
    return Response(status_code=204)


@app.post("/api/demo/reset")
def demo_reset():
    if not config.DEMO_MODE:
        raise HTTPException(403, "DEMO_MODE выключен")
    demo.seed()
    return {"ok": True}


# ---------- serve built web app (production) ----------

WEB_DIST = Path(__file__).resolve().parent.parent.parent / "web" / "dist"
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = WEB_DIST / path
        return FileResponse(f if path and f.is_file() else WEB_DIST / "index.html")
