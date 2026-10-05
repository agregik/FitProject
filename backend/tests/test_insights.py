import json
import random
from datetime import date, timedelta

from app import db, insights, training


def _recovery(user_id, days=60, seed=1):
    rnd = random.Random(seed)
    start = date.today() - timedelta(days=days)
    for i in range(days + 1):
        d = (start + timedelta(days=i)).isoformat()
        db.execute("INSERT INTO recovery (cycle_id, user_id, day, score, hrv) VALUES (?,?,?,?,?)",
                   (i, user_id, d, rnd.uniform(30, 90), rnd.uniform(40, 80)))
    return start


def _note(user_id, day, tags, text="x"):
    db.execute("INSERT INTO notes (user_id, day, text, tags, created_at) VALUES (?,?,?,?,?)",
               (user_id, day.isoformat(), text, json.dumps(tags, ensure_ascii=False), db.now_iso()))


def test_unlogged_days_are_not_treated_as_habit_free(user_id):
    start = _recovery(user_id)
    for i in range(0, 40, 5):  # 8 tagged days, nothing else logged
        _note(user_id, start + timedelta(days=i), ["алкоголь"])
    res = insights.compute(user_id, 90)
    assert res["tags"] == []
    pending = {p["tag"]: p for p in res["pending_tags"]}
    assert pending["алкоголь"]["n"] == 8 and pending["алкоголь"]["n_without"] == 0


def test_tag_is_compared_against_logged_days_only(user_id):
    start = _recovery(user_id)
    for i in range(0, 40, 5):
        _note(user_id, start + timedelta(days=i), ["алкоголь"])
    for i in range(1, 40, 5):  # 8 "plain" logged days without the tag
        _note(user_id, start + timedelta(days=i), [], "обычный день")
    res = insights.compute(user_id, 90)
    eff = {t["tag"]: t for t in res["tags"]}
    assert eff["алкоголь"]["n"] == 8
    assert eff["алкоголь"]["n_without"] == 8  # not the ~50 unlogged days


def test_few_tagged_days_stay_pending(user_id):
    start = _recovery(user_id)
    for i in range(0, 20, 5):  # the reviewer's case: 4 tagged + 4 untagged logged days
        _note(user_id, start + timedelta(days=i), ["стресс"])
        _note(user_id, start + timedelta(days=i + 1), [], "обычный день")
    res = insights.compute(user_id, 90)
    assert res["tags"] == []


def test_strength_tags_use_days_since_first_logged_session(user_id):
    start = _recovery(user_id)
    for i in range(30, 58, 3):  # lifts only in the second half of the period
        training.save_session(user_id, (start + timedelta(days=i)).isoformat(), "Ноги", None,
                              [{"exercise": "Приседания со штангой", "sets": [{"weight_kg": 100, "reps": 5}]}])
    res = insights.compute(user_id, 90)
    eff = {t["tag"]: t for t in res["tags"]}
    legs = eff["силовая_ноги"]
    assert legs["n"] + legs["n_without"] <= 30  # days before the first session are excluded


def test_e1rm():
    assert training.e1rm(100, 1) == 100
    assert round(training.e1rm(100, 5), 1) == 116.7
    assert training.e1rm(100, 15) is None
    assert training.e1rm(None, 5) is None


def test_high_confidence_requires_interval_excluding_zero(user_id):
    start = _recovery(user_id, days=120, seed=3)
    for i in range(0, 118):
        _note(user_id, start + timedelta(days=i), ["тег"] if i % 3 == 0 else [], "день")
    for t in insights.compute(user_id, 150)["tags"]:
        if t["confidence"] == "высокая":
            assert t["ci_low"] > 0 or t["ci_high"] < 0
