"""WHOOP API v2: OAuth, token refresh, paginated fetch and storage."""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from . import config, db

log = logging.getLogger("whoop")

_refresh_locks: dict[int, asyncio.Lock] = {}


# ---------- helpers ----------

def parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _offset(tz: str | None) -> timedelta:
    if not tz:
        return timedelta(0)
    sign = -1 if tz.startswith("-") else 1
    hh, mm = tz.lstrip("+-").split(":")
    return sign * timedelta(hours=int(hh), minutes=int(mm))


def local_dt(ts: str | None, tz: str | None) -> datetime | None:
    dt = parse_ts(ts)
    return dt + _offset(tz) if dt else None


def cycle_day(start: str, tz: str | None) -> str:
    """A WHOOP cycle starts when you fall asleep. Shifting by 12h maps it to the day you woke up."""
    return (local_dt(start, tz) + timedelta(hours=12)).date().isoformat()


def wake_day(end: str | None, start: str, tz: str | None) -> str:
    ref = local_dt(end, tz) if end else local_dt(start, tz) + timedelta(hours=8)
    return ref.date().isoformat()


# ---------- OAuth ----------

def auth_url(state: str) -> str:
    q = {
        "response_type": "code",
        "client_id": config.WHOOP_CLIENT_ID,
        "redirect_uri": config.WHOOP_REDIRECT_URI,
        "scope": config.WHOOP_SCOPES,
        "state": state,
    }
    return f"{config.WHOOP_AUTH_URL}?{urlencode(q)}"


async def exchange_code(code: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            config.WHOOP_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config.WHOOP_REDIRECT_URI,
                "client_id": config.WHOOP_CLIENT_ID,
                "client_secret": config.WHOOP_CLIENT_SECRET,
            },
        )
        r.raise_for_status()
        return r.json()


def _save_tokens(user_id: int, tok: dict) -> None:
    db.execute(
        "UPDATE users SET access_token=?, refresh_token=COALESCE(?, refresh_token), token_expires_at=? WHERE id=?",
        (tok["access_token"], tok.get("refresh_token"), time.time() + tok.get("expires_in", 3600) - 60, user_id),
    )


async def _valid_access_token(user_id: int) -> str:
    lock = _refresh_locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        u = db.get_user(user_id)
        if u["access_token"] and (u["token_expires_at"] or 0) > time.time():
            return u["access_token"]
        if not u["refresh_token"]:
            raise RuntimeError("Нет refresh token — нужно заново войти через WHOOP")
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                config.WHOOP_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": u["refresh_token"],
                    "client_id": config.WHOOP_CLIENT_ID,
                    "client_secret": config.WHOOP_CLIENT_SECRET,
                    "scope": "offline",
                },
            )
            r.raise_for_status()
            tok = r.json()
        _save_tokens(user_id, tok)
        return tok["access_token"]


async def login_with_code(code: str) -> int:
    """Exchange OAuth code, create or update the user and return the local user id."""
    tok = await exchange_code(code)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{config.WHOOP_API}/v2/user/profile/basic",
            headers={"Authorization": f"Bearer {tok['access_token']}"},
        )
        r.raise_for_status()
        p = r.json()
    existing = db.row("SELECT id FROM users WHERE whoop_user_id=?", (p["user_id"],))
    if existing:
        uid = existing["id"]
        db.execute(
            "UPDATE users SET email=?, first_name=?, last_name=? WHERE id=?",
            (p.get("email"), p.get("first_name"), p.get("last_name"), uid),
        )
    else:
        uid = db.execute(
            "INSERT INTO users (whoop_user_id, email, first_name, last_name, api_token, created_at) VALUES (?,?,?,?,?,?)",
            (p["user_id"], p.get("email"), p.get("first_name"), p.get("last_name"),
             secrets.token_urlsafe(32), db.now_iso()),
        )
    _save_tokens(uid, tok)
    return uid


def verify_webhook(raw_body: bytes, signature: str | None, timestamp: str | None) -> bool:
    if not signature or not timestamp or not config.WHOOP_CLIENT_SECRET:
        return False
    mac = hmac.new(config.WHOOP_CLIENT_SECRET.encode(), timestamp.encode() + raw_body, hashlib.sha256)
    return hmac.compare_digest(base64.b64encode(mac.digest()).decode(), signature)


# ---------- API fetch ----------

async def _get(client: httpx.AsyncClient, user_id: int, path: str, params: dict | None = None) -> dict:
    for attempt in range(5):
        token = await _valid_access_token(user_id)
        r = await client.get(f"{config.WHOOP_API}{path}", params=params,
                             headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", "10"))
            log.warning("WHOOP rate limit, sleeping %ss", wait)
            await asyncio.sleep(wait)
            continue
        if r.status_code == 401 and attempt == 0:
            db.execute("UPDATE users SET token_expires_at=0 WHERE id=?", (user_id,))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"WHOOP API не отвечает: {path}")


async def _paged(client, user_id: int, path: str, start: str | None):
    params = {"limit": 25}
    if start:
        params["start"] = start
    while True:
        data = await _get(client, user_id, path, params)
        for rec in data.get("records", []):
            yield rec
        nxt = data.get("next_token")
        if not nxt:
            break
        params["nextToken"] = nxt


# ---------- storage ----------

def store_cycle(user_id: int, c: dict) -> None:
    s = c.get("score") or {}
    db.upsert("cycles", {
        "id": c["id"], "user_id": user_id, "day": cycle_day(c["start"], c.get("timezone_offset")),
        "start": c["start"], "end": c.get("end"), "tz": c.get("timezone_offset"),
        "score_state": c.get("score_state"), "strain": s.get("strain"), "kj": s.get("kilojoule"),
        "avg_hr": s.get("average_heart_rate"), "max_hr": s.get("max_heart_rate"), "raw": json.dumps(c),
    }, ["user_id", "id"])


def store_recovery(user_id: int, r: dict) -> None:
    s = r.get("score") or {}
    cyc = db.row("SELECT day FROM cycles WHERE user_id=? AND id=?", (user_id, r["cycle_id"]))
    day = cyc["day"] if cyc else None
    if day is None:
        sl = db.row("SELECT day FROM sleeps WHERE user_id=? AND id=?", (user_id, str(r.get("sleep_id"))))
        day = sl["day"] if sl else (parse_ts(r["created_at"]).date().isoformat())
    db.upsert("recovery", {
        "cycle_id": r["cycle_id"], "user_id": user_id, "sleep_id": str(r.get("sleep_id")), "day": day,
        "score_state": r.get("score_state"), "score": s.get("recovery_score"), "hrv": s.get("hrv_rmssd_milli"),
        "rhr": s.get("resting_heart_rate"), "spo2": s.get("spo2_percentage"),
        "skin_temp": s.get("skin_temp_celsius"), "calibrating": int(bool(s.get("user_calibrating"))),
        "raw": json.dumps(r),
    }, ["user_id", "cycle_id"])


def store_sleep(user_id: int, sl: dict) -> None:
    s = sl.get("score") or {}
    st = s.get("stage_summary") or {}
    need = s.get("sleep_needed") or {}
    need_ms = sum(need.get(k) or 0 for k in (
        "baseline_milli", "need_from_sleep_debt_milli", "need_from_recent_strain_milli",
        "need_from_recent_nap_milli")) or None
    db.upsert("sleeps", {
        "id": str(sl["id"]), "user_id": user_id, "cycle_id": sl.get("cycle_id"),
        "day": wake_day(sl.get("end"), sl["start"], sl.get("timezone_offset")),
        "start": sl["start"], "end": sl.get("end"), "tz": sl.get("timezone_offset"),
        "nap": int(bool(sl.get("nap"))), "score_state": sl.get("score_state"),
        "performance": s.get("sleep_performance_percentage"),
        "consistency": s.get("sleep_consistency_percentage"),
        "efficiency": s.get("sleep_efficiency_percentage"), "resp_rate": s.get("respiratory_rate"),
        "in_bed_ms": st.get("total_in_bed_time_milli"), "awake_ms": st.get("total_awake_time_milli"),
        "light_ms": st.get("total_light_sleep_time_milli"), "sws_ms": st.get("total_slow_wave_sleep_time_milli"),
        "rem_ms": st.get("total_rem_sleep_time_milli"), "disturbances": st.get("disturbance_count"),
        "need_ms": need_ms, "raw": json.dumps(sl),
    }, ["user_id", "id"])


def store_workout(user_id: int, w: dict) -> None:
    s = w.get("score") or {}
    db.upsert("workouts", {
        "id": str(w["id"]), "user_id": user_id,
        "day": local_dt(w["start"], w.get("timezone_offset")).date().isoformat(),
        "start": w["start"], "end": w.get("end"), "tz": w.get("timezone_offset"),
        "sport": w.get("sport_name") or str(w.get("sport_id")), "score_state": w.get("score_state"),
        "strain": s.get("strain"), "avg_hr": s.get("average_heart_rate"), "max_hr": s.get("max_heart_rate"),
        "kj": s.get("kilojoule"), "distance_m": s.get("distance_meter"),
        "zones": json.dumps(s.get("zone_durations") or {}), "raw": json.dumps(w),
    }, ["user_id", "id"])


# ---------- sync ----------

async def sync_user(user_id: int, full: bool = False) -> dict:
    """Fetch data since last sync (minus a 4-day overlap so late scores get updated)."""
    u = db.get_user(user_id)
    if u["is_demo"]:
        return {"skipped": "demo"}
    start = None
    if u["last_sync_at"] and not full:
        start = (parse_ts(u["last_sync_at"]) - timedelta(days=4)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    counts = {}
    async with httpx.AsyncClient(timeout=60) as client:
        # Order matters: cycles and sleeps first so recovery can resolve its day.
        for name, path, store in (
            ("cycles", "/v2/cycle", store_cycle),
            ("sleeps", "/v2/activity/sleep", store_sleep),
            ("recovery", "/v2/recovery", store_recovery),
            ("workouts", "/v2/activity/workout", store_workout),
        ):
            n = 0
            async for rec in _paged(client, user_id, path, start):
                store(user_id, rec)
                n += 1
            counts[name] = n
    db.execute("UPDATE users SET last_sync_at=? WHERE id=?", (db.now_iso(), user_id))
    log.info("synced user %s: %s", user_id, counts)
    return counts


async def handle_webhook(payload: dict) -> int | None:
    """WHOOP webhooks only carry ids, so we re-sync the recent window for that user."""
    u = db.row("SELECT id FROM users WHERE whoop_user_id=?", (payload.get("user_id"),))
    if not u:
        return None
    typ = payload.get("type", "")
    if typ.endswith(".deleted"):
        table = {"sleep": "sleeps", "workout": "workouts"}.get(typ.split(".")[0])
        if table:
            db.execute(f"DELETE FROM {table} WHERE user_id=? AND id=?", (u["id"], str(payload.get("id"))))
        elif typ.startswith("recovery"):
            db.execute("DELETE FROM recovery WHERE user_id=? AND sleep_id=?", (u["id"], str(payload.get("id"))))
        return u["id"]
    await sync_user(u["id"])
    return u["id"]
