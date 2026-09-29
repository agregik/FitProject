"""Synthetic 180-day dataset with realistic, discoverable effects.

Hidden truths the insights engine should find:
  #алкоголь      → next-day HRV −20%, recovery ≈ −20
  #поздний_ужин  → HRV −7%
  #сауна         → HRV +5%
  late meetings  → later bedtime, less sleep
  high strain    → lower next-day recovery
Plus a short illness episode (skin temp and respiratory rate up).
"""
import json
import math
import random
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

from . import db

TZ = "+03:00"
OFF = timedelta(hours=3)


def _utc(local: datetime) -> str:
    return (local - OFF).replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


NOTE_TEXT = {
    "алкоголь": ["Два бокала вина на ужине #алкоголь", "Пиво с друзьями #алкоголь", "День рождения, коктейли #алкоголь"],
    "кофе_поздно": ["Кофе после 17:00 #кофе_поздно"],
    "поздний_ужин": ["Плотно поел в 22:30 #поздний_ужин", "Поздний ужин #поздний_ужин"],
    "сауна": ["Баня вечером #сауна", "Сауна после тренировки #сауна"],
    "медитация": ["10 минут медитации перед сном #медитация"],
    "стресс": ["Тяжёлый день, дедлайн #стресс", "Нервный созвон с заказчиком #стресс"],
    "болею": ["Першит горло, слабость #болею"],
}


def seed(days: int = 180, rnd_seed: int = 42) -> int:
    rnd = random.Random(rnd_seed)
    existing = db.row("SELECT id FROM users WHERE is_demo=1")
    if existing:
        uid = existing["id"]
        with db.conn() as c:
            for t in ("cycles", "recovery", "sleeps", "workouts", "notes", "events", "coach_messages", "notified"):
                c.execute(f"DELETE FROM {t} WHERE user_id=?", (uid,))
    else:
        uid = db.execute(
            "INSERT INTO users (first_name, api_token, is_demo, created_at, settings) VALUES (?,?,1,?,?)",
            ("Демо", "demo-" + secrets.token_urlsafe(16), db.now_iso(),
             json.dumps({"tz": "Europe/Moscow", "wake_time": "07:30"})),
        )

    today = datetime.now(timezone.utc).astimezone(timezone(OFF)).date()
    start = today - timedelta(days=days - 1)
    sick_start = start + timedelta(days=int(days * 0.55))
    hrv_base = 62.0
    prev_strain = 10.0
    cycle_id = 900000
    sleep_debt = 0.0

    with db.conn() as c:
        for i in range(days):
            day = start + timedelta(days=i)
            prev = day - timedelta(days=1)
            wd_prev = prev.weekday()
            weekend_night = wd_prev in (4, 5)
            sick = sick_start <= day < sick_start + timedelta(days=4)

            # --- yesterday's calendar ---
            meetings, late = 0, 0
            if wd_prev < 5:
                meetings = rnd.randint(2, 8)
                slots = sorted(rnd.sample(range(9, 19), min(meetings, 10)))
                for h in slots:
                    s = datetime(prev.year, prev.month, prev.day, h, rnd.choice([0, 30]))
                    e = s + timedelta(minutes=rnd.choice([30, 30, 60, 60, 90]))
                    c.execute('INSERT INTO events (user_id, day, start, "end", title, all_day) VALUES (?,?,?,?,?,0)',
                              (uid, prev.isoformat(), s.isoformat() + "+03:00", e.isoformat() + "+03:00",
                               rnd.choice(["Синк команды", "1:1", "Ревью", "Созвон с клиентом", "Планирование", "Интервью"])))
                if rnd.random() < 0.15:
                    late = 1
                    s = datetime(prev.year, prev.month, prev.day, 21, 30)
                    c.execute('INSERT INTO events (user_id, day, start, "end", title, all_day) VALUES (?,?,?,?,?,0)',
                              (uid, prev.isoformat(), s.isoformat() + "+03:00",
                               (s + timedelta(hours=1)).isoformat() + "+03:00", "Созвон с США"))

            # --- yesterday evening behaviours (logged on prev day) ---
            tags = set()
            if rnd.random() < (0.45 if weekend_night else 0.12):
                tags.add("алкоголь")
            if rnd.random() < 0.15:
                tags.add("кофе_поздно")
            if rnd.random() < 0.2:
                tags.add("поздний_ужин")
            if rnd.random() < 0.1:
                tags.add("сауна")
            if rnd.random() < 0.3:
                tags.add("медитация")
            if meetings >= 7 or late:
                if rnd.random() < 0.6:
                    tags.add("стресс")
            if sick_start - timedelta(days=1) <= prev < sick_start + timedelta(days=3):
                tags.add("болею")
            if i > 0:  # don't log for the day before the dataset starts
                for t in tags:
                    c.execute("INSERT INTO notes (user_id, day, text, tags, source, created_at) VALUES (?,?,?,?,?,?)",
                              (uid, prev.isoformat(), rnd.choice(NOTE_TEXT[t]), json.dumps([t], ensure_ascii=False),
                               rnd.choice(["web", "telegram"]), db.now_iso()))

            # --- night prev → day ---
            bed_h = 23.4 + rnd.gauss(0, 0.45) + (0.6 if weekend_night else 0) + (1.0 if late else 0)
            bed_h += 0.4 if "алкоголь" in tags else 0
            bed_h -= 0.3 if "медитация" in tags else 0
            wake_h = (9.0 if weekend_night else 7.5) + rnd.gauss(0, 0.25)
            in_bed = wake_h + 24 - bed_h
            eff = min(97, max(78, 91 + rnd.gauss(0, 2.5) - (5 if "алкоголь" in tags else 0)
                             - (3 if "кофе_поздно" in tags else 0) - (4 if sick else 0)))
            asleep = in_bed * eff / 100
            need = 7.5 + max(0, prev_strain - 12) * 0.1 + sleep_debt * 0.25
            sleep_debt = max(0, min(2, 0.6 * sleep_debt + need - asleep - 0.3))
            perf = min(100, asleep / need * 100)
            deep = asleep * (0.22 - (0.05 if "алкоголь" in tags else 0) + rnd.gauss(0, 0.02))
            rem = asleep * (0.24 - (0.06 if "алкоголь" in tags else 0) + rnd.gauss(0, 0.02))
            light = asleep - deep - rem

            # --- physiology ---
            trend = 4 * math.sin(i / 28)
            mult = 1.0
            mult *= 0.80 if "алкоголь" in tags else 1
            mult *= 0.93 if "поздний_ужин" in tags else 1
            mult *= 0.93 if "стресс" in tags else 1
            mult *= 1.05 if "сауна" in tags else 1
            mult *= 1.03 if "медитация" in tags else 1
            mult *= 0.92 if prev_strain > 15 else 1
            mult *= 1 - max(0, need - asleep) * 0.04
            mult *= 0.7 if sick else 1
            hrv = max(20, (hrv_base + trend) * mult + rnd.gauss(0, 4.5))
            rhr = 52 - (hrv - hrv_base) * 0.12 + (4 if "алкоголь" in tags else 0) + (6 if sick else 0) + rnd.gauss(0, 1.2)
            rec = 64 + 110 * (hrv / (hrv_base + trend) - 1) + 0.35 * (perf - 85) - 1.5 * (rhr - 52) + rnd.gauss(0, 5)
            rec = max(4, min(99, rec))
            skin = 33.8 + rnd.gauss(0, 0.15) + (0.8 if sick else 0)
            resp = 14.6 + rnd.gauss(0, 0.3) + (1.6 if sick else 0)
            spo2 = min(99.5, 96.5 + rnd.gauss(0, 0.8))

            bed_local = datetime(prev.year, prev.month, prev.day) + timedelta(hours=bed_h)
            wake_local = datetime(prev.year, prev.month, prev.day) + timedelta(hours=wake_h + 24)
            cycle_id += 1
            sleep_id = str(uuid.UUID(int=rnd.getrandbits(128)))
            is_today = day == today

            # --- today's workouts and strain ---
            wd = day.weekday()
            workouts = []
            if not sick:
                if wd in (0, 3) and rnd.random() < 0.85:
                    workouts.append(("Running", rnd.uniform(9, 13), 18, rnd.uniform(6000, 11000)))
                if wd in (1, 4) and rnd.random() < 0.8:
                    workouts.append(("Weightlifting", rnd.uniform(7, 10), 19, None))
                if wd == 5 and rnd.random() < 0.7:
                    workouts.append(("Cycling", rnd.uniform(13, 17), 10, rnd.uniform(40000, 80000)))
                if wd == 6 and rnd.random() < 0.3:
                    workouts.append(("Yoga", rnd.uniform(3, 5), 11, None))
            day_strain = min(21, 6 + rnd.uniform(0, 3) + sum(w[1] for w in workouts) * 0.55)
            if is_today:
                day_strain = min(day_strain, 7.5)  # the day isn't over yet
                workouts = []

            c.execute(
                'INSERT INTO cycles (id, user_id, day, start, "end", tz, score_state, strain, kj, avg_hr, max_hr, raw) '
                "VALUES (?,?,?,?,?,?,?,?,?,?,?, '{}')",
                (cycle_id, uid, day.isoformat(), _utc(bed_local), None if is_today else _utc(bed_local + timedelta(hours=24)),
                 TZ, "SCORED", round(day_strain, 1), round(8000 + day_strain * 400), round(64 + day_strain), round(120 + day_strain * 4)),
            )
            c.execute(
                'INSERT INTO sleeps (id, user_id, cycle_id, day, start, "end", tz, nap, score_state, performance, consistency, '
                "efficiency, resp_rate, in_bed_ms, awake_ms, light_ms, sws_ms, rem_ms, disturbances, need_ms, raw) "
                "VALUES (?,?,?,?,?,?,?,0,'SCORED',?,?,?,?,?,?,?,?,?,?,?, '{}')",
                (sleep_id, uid, cycle_id, day.isoformat(), _utc(bed_local), _utc(wake_local), TZ, round(perf),
                 round(max(50, 85 - abs(bed_h - 23.4) * 15 + rnd.gauss(0, 4))), round(eff, 1), round(resp, 1),
                 int(in_bed * 3.6e6), int((in_bed - asleep) * 3.6e6), int(light * 3.6e6), int(deep * 3.6e6),
                 int(rem * 3.6e6), rnd.randint(5, 18), int(need * 3.6e6)),
            )
            c.execute(
                "INSERT INTO recovery (cycle_id, user_id, sleep_id, day, score_state, score, hrv, rhr, spo2, skin_temp, calibrating, raw) "
                "VALUES (?,?,?,?,'SCORED',?,?,?,?,?,0,'{}')",
                (cycle_id, uid, sleep_id, day.isoformat(), round(rec), round(hrv, 1), round(rhr), round(spo2, 1), round(skin, 2)),
            )
            for sport, strain, hour, dist in workouts:
                s = datetime(day.year, day.month, day.day, hour, rnd.choice([0, 15, 30]))
                dur = timedelta(minutes=int(35 + strain * 5))
                zones = {"zone_zero_milli": 0, "zone_one_milli": int(dur.total_seconds() * 150),
                         "zone_two_milli": int(dur.total_seconds() * 350), "zone_three_milli": int(dur.total_seconds() * 300),
                         "zone_four_milli": int(dur.total_seconds() * 150), "zone_five_milli": int(dur.total_seconds() * 50)}
                c.execute(
                    'INSERT INTO workouts (id, user_id, day, start, "end", tz, sport, score_state, strain, avg_hr, max_hr, kj, distance_m, zones, raw) '
                    "VALUES (?,?,?,?,?,?,?,'SCORED',?,?,?,?,?,?, '{}')",
                    (str(uuid.UUID(int=rnd.getrandbits(128))), uid, day.isoformat(), _utc(s), _utc(s + dur), TZ, sport,
                     round(strain, 1), round(120 + strain * 3), round(160 + strain * 1.5), round(strain * 180), dist, json.dumps(zones)),
                )
            prev_strain = day_strain

        c.execute("UPDATE users SET last_sync_at=? WHERE id=?", (db.now_iso(), uid))
    return uid


if __name__ == "__main__":
    db.init()
    print("demo user id:", seed())
