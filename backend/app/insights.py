"""What moves *your* recovery: tags, sleep, strain, calendar load, weekday."""
import math
import random
import statistics
from datetime import date, timedelta

from .days import build_days

MIN_N = 4
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _next_day(d: str) -> str:
    return (date.fromisoformat(d) + timedelta(days=1)).isoformat()


def _perm_p(a: list[float], b: list[float], iters: int = 3000, seed: int = 7) -> float:
    """Two-sided permutation test on difference of means."""
    rng = random.Random(seed)
    obs = abs(statistics.fmean(a) - statistics.fmean(b))
    pool = a + b
    na = len(a)
    hits = 0
    for _ in range(iters):
        rng.shuffle(pool)
        if abs(statistics.fmean(pool[:na]) - statistics.fmean(pool[na:])) >= obs - 1e-12:
            hits += 1
    return (hits + 1) / (iters + 1)


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 10:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if not sx or not sy:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def _confidence(p: float, n: int) -> str:
    if p < 0.05 and n >= 8:
        return "высокая"
    if p < 0.2:
        return "средняя"
    return "низкая"


def _corr_confidence(r: float, n: int) -> str:
    # Approximate p from t-statistic, normal approximation.
    t = abs(r) * math.sqrt((n - 2) / max(1e-9, 1 - r * r))
    p = math.erfc(t / math.sqrt(2))
    return _confidence(p, n)


def compute(user_id: int, days_back: int = 180) -> dict:
    end = date.today() + timedelta(days=1)
    start = end - timedelta(days=days_back + 1)
    days = build_days(user_id, start.isoformat(), end.isoformat())
    by_date = {d["date"]: d for d in days}

    # Pair each day with the next day's recovery / HRV (evening behaviour → morning outcome).
    pairs = []
    for d in days:
        nxt = by_date.get(_next_day(d["date"]))
        if nxt and nxt.get("recovery") is not None:
            pairs.append((d, nxt))

    has_notes = {d["date"] for d in days if d.get("notes")}
    tag_counts: dict[str, int] = {}
    for d in days:
        for t in d.get("tags", []):
            tag_counts[t] = tag_counts.get(t, 0) + 1

    tag_effects = []
    for tag, cnt in tag_counts.items():
        with_r = [n["recovery"] for d, n in pairs if tag in d["tags"]]
        # Compare against days where you logged something, but not this tag,
        # falling back to all other days if the journal is sparse.
        without = [(d, n) for d, n in pairs if tag not in d["tags"] and d["date"] in has_notes]
        if len(without) < MIN_N:
            without = [(d, n) for d, n in pairs if tag not in d["tags"]]
        without_r = [n["recovery"] for _, n in without]
        if len(with_r) < MIN_N or len(without_r) < MIN_N:
            continue
        with_h = [n["hrv"] for d, n in pairs if tag in d["tags"] and n.get("hrv")]
        without_h = [n["hrv"] for _, n in without if n.get("hrv")]
        diff = statistics.fmean(with_r) - statistics.fmean(without_r)
        p = _perm_p(with_r, without_r)
        hrv_diff_pct = None
        if with_h and without_h:
            hrv_diff_pct = (statistics.fmean(with_h) / statistics.fmean(without_h) - 1) * 100
        tag_effects.append({
            "tag": tag,
            "n": len(with_r),
            "recovery_with": round(statistics.fmean(with_r), 1),
            "recovery_without": round(statistics.fmean(without_r), 1),
            "recovery_diff": round(diff, 1),
            "hrv_diff_pct": round(hrv_diff_pct, 1) if hrv_diff_pct is not None else None,
            "p_value": round(p, 3),
            "confidence": _confidence(p, len(with_r)),
        })
    tag_effects.sort(key=lambda x: (x["confidence"] != "высокая", -abs(x["recovery_diff"])))

    # Continuous drivers.
    drivers = []

    def add_driver(key, label, pairs_xy, unit, explain):
        xs = [x for x, _ in pairs_xy]
        ys = [y for _, y in pairs_xy]
        r = _pearson(xs, ys)
        if r is None:
            return
        # slope: recovery points per unit
        mx, my = statistics.fmean(xs), statistics.fmean(ys)
        vx = sum((x - mx) ** 2 for x in xs)
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / vx if vx else 0
        drivers.append({
            "key": key, "label": label, "r": round(r, 2), "n": len(xs),
            "slope": round(slope, 2), "unit": unit, "explain": explain,
            "confidence": _corr_confidence(r, len(xs)),
            "points": [{"x": round(x, 2), "y": round(y, 1)} for x, y in pairs_xy],
        })

    add_driver("sleep_hours", "Длительность сна → recovery",
               [(d["sleep_hours"], d["recovery"]) for d in days if d.get("sleep_hours") and d.get("recovery") is not None],
               "час сна", "Каждый дополнительный час сна")
    add_driver("strain_prev", "Strain вчера → recovery сегодня",
               [(d["strain"], n["recovery"]) for d, n in pairs if d.get("strain") is not None],
               "ед. strain", "Каждая единица вчерашнего strain")
    add_driver("meetings", "Встречи вчера → recovery сегодня",
               [(d.get("meetings", 0), n["recovery"]) for d, n in pairs if "meetings" in d],
               "встреча", "Каждая встреча в календаре")
    add_driver("busy_hours", "Занятость вчера → recovery сегодня",
               [(d.get("busy_hours", 0), n["recovery"]) for d, n in pairs if "busy_hours" in d],
               "час встреч", "Каждый час встреч")
    add_driver("late_events", "Поздние события → recovery",
               [(d.get("late_events", 0), n["recovery"]) for d, n in pairs if "late_events" in d],
               "позднее событие", "Каждое событие после 21:00")

    def bed_hour(d):
        from .whoop import local_dt
        dt = local_dt(d["sleep_start"], d.get("sleep_tz"))
        h = dt.hour + dt.minute / 60
        return h - 24 if h > 12 else h  # 23:30 → -0.5, 00:30 → 0.5

    add_driver("bedtime", "Время отбоя → recovery",
               [(bed_hour(d), d["recovery"]) for d in days if d.get("sleep_start") and d.get("recovery") is not None],
               "час позже", "Каждый час более позднего отбоя")
    drivers.sort(key=lambda x: -abs(x["r"]))

    # Weekday pattern.
    wd = {i: [] for i in range(7)}
    for d in days:
        if d.get("recovery") is not None:
            wd[date.fromisoformat(d["date"]).weekday()].append(d["recovery"])
    weekday = [{"weekday": WEEKDAYS[i], "recovery": round(statistics.fmean(v), 1) if v else None, "n": len(v)}
               for i, v in wd.items()]

    return {
        "period_days": days_back,
        "days_with_data": sum(1 for d in days if d.get("recovery") is not None),
        "tags": tag_effects,
        "drivers": drivers,
        "weekday": weekday,
        "all_tags": sorted(tag_counts.items(), key=lambda x: -x[1]),
    }


def headline(ins: dict, limit: int = 3) -> list[str]:
    """Short human sentences for the bot / coach context."""
    out = []
    for t in ins["tags"]:
        if t["confidence"] == "низкая":
            continue
        sign = "снижает" if t["recovery_diff"] < 0 else "повышает"
        out.append(f"#{t['tag']} {sign} recovery следующего дня в среднем на {abs(t['recovery_diff']):.0f} п. "
                   f"({t['recovery_with']:.0f}% против {t['recovery_without']:.0f}%, n={t['n']}, "
                   f"уверенность {t['confidence']})")
        if len(out) >= limit:
            break
    for d in ins["drivers"]:
        if d["confidence"] == "низкая" or len(out) >= limit + 2:
            continue
        out.append(f"{d['explain']}: {d['slope']:+.1f} п. recovery (r={d['r']}, n={d['n']})")
    return out
