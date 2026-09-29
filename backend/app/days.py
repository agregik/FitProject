"""Merge cycles, recovery, sleep, workouts, notes and calendar into one row per day."""
import json
import re
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import db

TAG_RE = re.compile(r"#([\w\-]+)", re.UNICODE)


def parse_tags(text: str) -> list[str]:
    return sorted({t.lower() for t in TAG_RE.findall(text)})


def today_for(user: dict) -> str:
    tz = db.user_settings(user)["tz"]
    return datetime.now(ZoneInfo(tz)).date().isoformat()


def _hours(ms):
    return round(ms / 3_600_000, 2) if ms is not None else None


def build_days(user_id: int, start: str | None = None, end: str | None = None) -> list[dict]:
    start = start or "0000-01-01"
    end = end or "9999-12-31"
    p = (user_id, start, end)
    days: dict[str, dict] = defaultdict(lambda: {"tags": [], "notes": [], "workouts": []})

    for r in db.rows("SELECT * FROM cycles WHERE user_id=? AND day BETWEEN ? AND ?", p):
        d = days[r["day"]]
        d.update(strain=r["strain"], kj=r["kj"], avg_hr=r["avg_hr"], max_hr=r["max_hr"])

    for r in db.rows("SELECT * FROM recovery WHERE user_id=? AND day BETWEEN ? AND ?", p):
        d = days[r["day"]]
        d.update(recovery=r["score"], hrv=r["hrv"], rhr=r["rhr"], spo2=r["spo2"],
                 skin_temp=r["skin_temp"], calibrating=bool(r["calibrating"]))

    for r in db.rows("SELECT * FROM sleeps WHERE user_id=? AND day BETWEEN ? AND ? ORDER BY start", p):
        d = days[r["day"]]
        if r["nap"]:
            d["nap_hours"] = round((d.get("nap_hours") or 0) + (_hours((r["in_bed_ms"] or 0) - (r["awake_ms"] or 0)) or 0), 2)
            continue
        asleep = (r["in_bed_ms"] or 0) - (r["awake_ms"] or 0)
        d.update(
            sleep_hours=_hours(asleep), sleep_need_hours=_hours(r["need_ms"]),
            sleep_performance=r["performance"], sleep_consistency=r["consistency"],
            sleep_efficiency=r["efficiency"], resp_rate=r["resp_rate"],
            deep_hours=_hours(r["sws_ms"]), rem_hours=_hours(r["rem_ms"]), light_hours=_hours(r["light_ms"]),
            awake_hours=_hours(r["awake_ms"]), disturbances=r["disturbances"],
            sleep_start=r["start"], sleep_end=r["end"], sleep_tz=r["tz"],
        )

    for r in db.rows("SELECT * FROM workouts WHERE user_id=? AND day BETWEEN ? AND ? ORDER BY start", p):
        days[r["day"]]["workouts"].append({
            "id": r["id"], "sport": r["sport"], "strain": r["strain"], "start": r["start"], "end": r["end"],
            "avg_hr": r["avg_hr"], "max_hr": r["max_hr"], "kj": r["kj"], "distance_m": r["distance_m"],
            "zones": json.loads(r["zones"] or "{}"),
        })

    for r in db.rows("SELECT * FROM notes WHERE user_id=? AND day BETWEEN ? AND ? ORDER BY created_at", p):
        d = days[r["day"]]
        tags = json.loads(r["tags"] or "[]")
        d["notes"].append({"id": r["id"], "text": r["text"], "tags": tags, "source": r["source"]})
        d["tags"] = sorted(set(d["tags"]) | set(tags))

    ev_by_day = defaultdict(list)
    for r in db.rows("SELECT * FROM events WHERE user_id=? AND day BETWEEN ? AND ?", p):
        ev_by_day[r["day"]].append(r)
    for day, evs in ev_by_day.items():
        days[day].update(calendar_metrics(evs))

    out = []
    for day in sorted(days):
        d = days[day]
        d["date"] = day
        out.append(d)
    return out


def calendar_metrics(evs: list[dict]) -> dict:
    timed = [e for e in evs if not e["all_day"]]
    intervals = sorted(
        (datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"])) for e in timed if e["end"]
    )
    busy = 0.0
    cur_s = cur_e = None
    for s, e in intervals:
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                busy += (cur_e - cur_s).total_seconds()
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        busy += (cur_e - cur_s).total_seconds()
    late = sum(1 for s, e in intervals if e.hour >= 21 or e.date() > s.date())
    early = sum(1 for s, _ in intervals if s.hour < 8)
    return {
        "meetings": len(timed),
        "busy_hours": round(busy / 3600, 2),
        "late_events": late,
        "early_events": early,
        "events": [{"title": e["title"], "start": e["start"], "end": e["end"], "all_day": bool(e["all_day"])}
                   for e in sorted(evs, key=lambda x: x["start"] or "")],
    }


METRICS = ["recovery", "hrv", "rhr", "skin_temp", "spo2", "resp_rate", "sleep_hours",
           "sleep_performance", "strain"]


def baselines(days: list[dict], until: str, window: int = 30) -> dict:
    """Mean and stdev of each metric over the `window` days before `until` (exclusive)."""
    lo = (date.fromisoformat(until) - timedelta(days=window)).isoformat()
    sample = [d for d in days if lo <= d["date"] < until]
    out = {}
    for m in METRICS:
        vals = [d[m] for d in sample if d.get(m) is not None]
        if len(vals) >= 5:
            out[m] = {"mean": round(statistics.fmean(vals), 2), "sd": round(statistics.stdev(vals), 2), "n": len(vals)}
    return out


def strain_target(recovery: float | None) -> dict:
    if recovery is None:
        return {"min": None, "max": None, "label": "Нет данных"}
    if recovery >= 67:
        return {"min": 14, "max": 18, "label": "Можно нагружаться"}
    if recovery >= 34:
        return {"min": 10, "max": 14, "label": "Умеренная нагрузка"}
    return {"min": 0, "max": 10, "label": "День восстановления"}


def bedtime(user: dict, days: list[dict]) -> dict | None:
    """Bedtime = wake time − sleep need / typical efficiency."""
    s = db.user_settings(user)
    last = next((d for d in reversed(days) if d.get("sleep_need_hours")), None)
    if not last:
        return None
    effs = [d["sleep_efficiency"] for d in days[-14:] if d.get("sleep_efficiency")]
    eff = (statistics.fmean(effs) / 100) if effs else 0.9
    need_h = last["sleep_need_hours"]
    in_bed_h = need_h / max(eff, 0.6)
    hh, mm = map(int, s["wake_time"].split(":"))
    wake = datetime(2000, 1, 2, hh, mm)
    bed = wake - timedelta(hours=in_bed_h)
    return {"bedtime": bed.strftime("%H:%M"), "wake_time": s["wake_time"],
            "need_hours": round(need_h, 1), "in_bed_hours": round(in_bed_h, 1)}


def alerts(days: list[dict], base: dict) -> list[dict]:
    out = []
    if not days:
        return out
    t = days[-1]

    def z(metric):
        if t.get(metric) is None or metric not in base or not base[metric]["sd"]:
            return None
        return (t[metric] - base[metric]["mean"]) / base[metric]["sd"]

    zh, zr, zt = z("hrv"), z("rhr"), None
    if t.get("skin_temp") is not None and "skin_temp" in base:
        zt = t["skin_temp"] - base["skin_temp"]["mean"]
    if zh is not None and zh < -1.5 and zr is not None and zr > 1.0:
        out.append({"level": "warn", "text": "HRV заметно ниже нормы и пульс в покое выше: организм под нагрузкой. Сегодня лучше полегче."})
    if zt is not None and zt > 0.6:
        out.append({"level": "warn", "text": f"Температура кожи выше нормы на {zt:.1f}°C. Бывает перед простудой: следи за самочувствием."})
    if t.get("resp_rate") is not None and "resp_rate" in base and t["resp_rate"] - base["resp_rate"]["mean"] > 1.0:
        out.append({"level": "warn", "text": "Частота дыхания во сне выше обычной."})
    short = 0
    for d in reversed(days[-5:]):
        if d.get("sleep_hours") and d.get("sleep_need_hours") and d["sleep_hours"] < d["sleep_need_hours"] - 0.75:
            short += 1
        else:
            break
    if short >= 3:
        out.append({"level": "info", "text": f"{short} ночи подряд сон короче потребности. Копится недосып: ложись раньше."})
    if zh is not None and zh > 1.0:
        out.append({"level": "good", "text": "HRV выше твоей нормы: хороший день для тяжёлой тренировки."})
    return out


def today_summary(user: dict) -> dict:
    today = today_for(user)
    start = (date.fromisoformat(today) - timedelta(days=60)).isoformat()
    days = build_days(user["id"], start, today)
    scored = [d for d in days if d.get("recovery") is not None]
    cur = scored[-1] if scored else (days[-1] if days else None)
    if not cur:
        return {"date": today, "day": None}
    base = baselines(days, cur["date"])
    upto = [d for d in days if d["date"] <= cur["date"]]
    return {
        "date": today,
        "day": cur,
        "is_today": cur["date"] == today,
        "baseline": base,
        "strain_target": strain_target(cur.get("recovery")),
        "bedtime": bedtime(user, upto),
        "alerts": alerts(upto, base),
        "last7": [
            {k: d.get(k) for k in ("date", "recovery", "hrv", "sleep_hours", "strain")} for d in days[-7:]
        ],
    }
