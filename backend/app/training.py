"""Strength training log: sessions → sets × weight × reps, e1RM and volume progress.

WHOOP only sees heart rate, so it can't tell a heavy squat day from a light one.
This log fills that gap and feeds per-muscle-group effects into insights.
"""
from collections import defaultdict

from . import db

MUSCLE_GROUPS = ["ноги", "спина", "грудь", "плечи", "руки", "кор", "другое"]

DEFAULT_EXERCISES = {
    "Приседания со штангой": "ноги", "Румынская тяга": "ноги", "Становая тяга": "спина",
    "Жим ногами": "ноги", "Выпады": "ноги", "Разгибания ног": "ноги", "Сгибания ног": "ноги",
    "Подъёмы на носки": "ноги",
    "Подтягивания": "спина", "Тяга штанги в наклоне": "спина", "Тяга верхнего блока": "спина",
    "Тяга гантели в наклоне": "спина", "Горизонтальная тяга": "спина",
    "Жим лёжа": "грудь", "Жим гантелей на наклонной": "грудь", "Отжимания на брусьях": "грудь",
    "Разведения гантелей": "грудь",
    "Жим стоя": "плечи", "Жим гантелей сидя": "плечи", "Махи в стороны": "плечи", "Face pull": "плечи",
    "Подъём штанги на бицепс": "руки", "Молотки": "руки", "Французский жим": "руки",
    "Разгибания на блоке": "руки",
    "Планка": "кор", "Подъёмы ног в висе": "кор", "Скручивания": "кор",
}


def e1rm(weight: float | None, reps: int) -> float | None:
    """Epley estimated one-rep max; only meaningful for 1–12 reps with external weight."""
    if not weight or weight <= 0 or not 1 <= reps <= 12:
        return None
    return weight if reps == 1 else weight * (1 + reps / 30)


def ensure_catalog(user_id: int) -> None:
    if db.row("SELECT 1 FROM exercises WHERE user_id=? LIMIT 1", (user_id,)):
        return
    with db.conn() as c:
        c.executemany("INSERT OR IGNORE INTO exercises (user_id, name, muscle_group) VALUES (?,?,?)",
                      [(user_id, n, g) for n, g in DEFAULT_EXERCISES.items()])


def exercises(user_id: int) -> list[dict]:
    ensure_catalog(user_id)
    return db.rows(
        "SELECT e.id, e.name, e.muscle_group, COUNT(DISTINCT s.session_id) AS sessions, MAX(ls.day) AS last_day "
        "FROM exercises e LEFT JOIN lift_sets s ON s.exercise_id=e.id "
        "LEFT JOIN lift_sessions ls ON ls.id=s.session_id "
        "WHERE e.user_id=? GROUP BY e.id ORDER BY sessions DESC, e.name", (user_id,))


def _exercise_id(c, user_id: int, name: str, group: str | None) -> int:
    name = " ".join(name.split())
    # SQLite NOCASE only folds ASCII, so "жим лёжа" vs "Жим лёжа" is matched here instead.
    key = name.casefold().replace("ё", "е")
    for r in c.execute("SELECT id, name FROM exercises WHERE user_id=?", (user_id,)):
        if r["name"].casefold().replace("ё", "е") == key:
            return r["id"]
    g = group if group in MUSCLE_GROUPS else "другое"
    return c.execute("INSERT INTO exercises (user_id, name, muscle_group) VALUES (?,?,?)",
                     (user_id, name, g)).lastrowid


def save_session(user_id: int, day: str, title: str | None, notes: str | None,
                 items: list[dict], session_id: int | None = None) -> int:
    """items: [{exercise, muscle_group?, sets: [{weight_kg, reps, rir?}]}]. Replaces sets on edit."""
    ensure_catalog(user_id)
    with db.conn() as c:
        if session_id:
            if not c.execute("SELECT 1 FROM lift_sessions WHERE id=? AND user_id=?", (session_id, user_id)).fetchone():
                raise KeyError(session_id)
            c.execute("UPDATE lift_sessions SET day=?, title=?, notes=? WHERE id=?", (day, title, notes, session_id))
            c.execute("DELETE FROM lift_sets WHERE session_id=?", (session_id,))
        else:
            session_id = c.execute(
                "INSERT INTO lift_sessions (user_id, day, title, notes, created_at) VALUES (?,?,?,?,?)",
                (user_id, day, title, notes, db.now_iso())).lastrowid
        ord_ = 0
        for it in items:
            ex_id = _exercise_id(c, user_id, it["exercise"], it.get("muscle_group"))
            for s in it["sets"]:
                ord_ += 1
                c.execute("INSERT INTO lift_sets (session_id, exercise_id, ord, weight_kg, reps, rir) VALUES (?,?,?,?,?,?)",
                          (session_id, ex_id, ord_, s.get("weight_kg"), s["reps"], s.get("rir")))
    return session_id


def delete_session(user_id: int, session_id: int) -> None:
    db.execute("DELETE FROM lift_sessions WHERE id=? AND user_id=?", (session_id, user_id))


def sessions(user_id: int, start: str, end: str) -> list[dict]:
    heads = db.rows("SELECT id, day, title, notes FROM lift_sessions WHERE user_id=? AND day BETWEEN ? AND ? "
                    "ORDER BY day DESC, id DESC", (user_id, start, end))
    if not heads:
        return []
    ids = [h["id"] for h in heads]
    sets = db.rows(
        f"SELECT s.session_id, s.weight_kg, s.reps, s.rir, e.id AS exercise_id, e.name, e.muscle_group "
        f"FROM lift_sets s JOIN exercises e ON e.id=s.exercise_id "
        f"WHERE s.session_id IN ({','.join('?' * len(ids))}) ORDER BY s.session_id, s.ord", ids)
    by_session: dict[int, list] = defaultdict(list)
    for s in sets:
        by_session[s["session_id"]].append(s)
    out = []
    for h in heads:
        items: list[dict] = []
        volume = 0.0
        for s in by_session[h["id"]]:
            if not items or items[-1]["exercise_id"] != s["exercise_id"]:
                items.append({"exercise_id": s["exercise_id"], "exercise": s["name"],
                              "muscle_group": s["muscle_group"], "sets": [], "best_e1rm": None})
            it = items[-1]
            it["sets"].append({"weight_kg": s["weight_kg"], "reps": s["reps"], "rir": s["rir"]})
            est = e1rm(s["weight_kg"], s["reps"])
            if est and (it["best_e1rm"] is None or est > it["best_e1rm"]):
                it["best_e1rm"] = round(est, 1)
            volume += (s["weight_kg"] or 0) * s["reps"]
        out.append({**h, "items": items, "volume_kg": round(volume),
                    "sets": sum(len(i["sets"]) for i in items),
                    "groups": sorted({i["muscle_group"] for i in items})})
    return out


def progress(user_id: int, exercise_id: int) -> dict:
    ex = db.row("SELECT id, name, muscle_group FROM exercises WHERE id=? AND user_id=?", (exercise_id, user_id))
    if not ex:
        raise KeyError(exercise_id)
    rows = db.rows("SELECT ls.day, s.weight_kg, s.reps FROM lift_sets s JOIN lift_sessions ls ON ls.id=s.session_id "
                   "WHERE s.exercise_id=? AND ls.user_id=? ORDER BY ls.day, s.ord", (exercise_id, user_id))
    by_day: dict[str, dict] = {}
    for r in rows:
        d = by_day.setdefault(r["day"], {"day": r["day"], "e1rm": None, "top_kg": None, "volume_kg": 0.0, "sets": 0})
        est = e1rm(r["weight_kg"], r["reps"])
        if est and (d["e1rm"] is None or est > d["e1rm"]):
            d["e1rm"] = est
        if r["weight_kg"] and (d["top_kg"] is None or r["weight_kg"] > d["top_kg"]):
            d["top_kg"] = r["weight_kg"]
        d["volume_kg"] += (r["weight_kg"] or 0) * r["reps"]
        d["sets"] += 1
    points = [{**d, "e1rm": round(d["e1rm"], 1) if d["e1rm"] else None, "volume_kg": round(d["volume_kg"])}
              for d in by_day.values()]
    best = max((p["e1rm"] for p in points if p["e1rm"]), default=None)
    return {**ex, "points": points, "best_e1rm": best}


def daily_load(user_id: int, start: str, end: str) -> dict[str, dict]:
    """Per day: total lifted volume (kg) and muscle groups trained — consumed by build_days."""
    out: dict[str, dict] = {}
    for r in db.rows(
        "SELECT ls.day, e.muscle_group, SUM(COALESCE(s.weight_kg,0) * s.reps) AS vol, COUNT(*) AS n "
        "FROM lift_sets s JOIN lift_sessions ls ON ls.id=s.session_id JOIN exercises e ON e.id=s.exercise_id "
        "WHERE ls.user_id=? AND ls.day BETWEEN ? AND ? GROUP BY ls.day, e.muscle_group", (user_id, start, end)):
        d = out.setdefault(r["day"], {"lift_volume_kg": 0.0, "lift_sets": 0, "lift_groups": []})
        d["lift_volume_kg"] += r["vol"] or 0
        d["lift_sets"] += r["n"]
        d["lift_groups"].append(r["muscle_group"])
    for d in out.values():
        d["lift_volume_kg"] = round(d["lift_volume_kg"])
        d["lift_groups"].sort()
    return out
