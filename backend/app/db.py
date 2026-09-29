"""SQLite storage. Schema is multi-user from day one: every row has user_id."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    whoop_user_id    INTEGER UNIQUE,
    email            TEXT,
    first_name       TEXT,
    last_name        TEXT,
    api_token        TEXT UNIQUE NOT NULL,
    access_token     TEXT,
    refresh_token    TEXT,
    token_expires_at REAL,
    last_sync_at     TEXT,
    tg_chat_id       INTEGER,
    tg_link_code     TEXT,
    ics_urls         TEXT DEFAULT '[]',
    settings         TEXT DEFAULT '{}',
    is_demo          INTEGER DEFAULT 0,
    created_at       TEXT
);

CREATE TABLE IF NOT EXISTS cycles (
    id          INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    day         TEXT NOT NULL,
    start       TEXT,
    "end"       TEXT,
    tz          TEXT,
    score_state TEXT,
    strain      REAL,
    kj          REAL,
    avg_hr      REAL,
    max_hr      REAL,
    raw         TEXT,
    PRIMARY KEY (user_id, id)
);
CREATE INDEX IF NOT EXISTS cycles_day ON cycles(user_id, day);

CREATE TABLE IF NOT EXISTS recovery (
    cycle_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    sleep_id    TEXT,
    day         TEXT NOT NULL,
    score_state TEXT,
    score       REAL,
    hrv         REAL,
    rhr         REAL,
    spo2        REAL,
    skin_temp   REAL,
    calibrating INTEGER,
    raw         TEXT,
    PRIMARY KEY (user_id, cycle_id)
);
CREATE INDEX IF NOT EXISTS recovery_day ON recovery(user_id, day);

CREATE TABLE IF NOT EXISTS sleeps (
    id           TEXT NOT NULL,
    user_id      INTEGER NOT NULL,
    cycle_id     INTEGER,
    day          TEXT NOT NULL,
    start        TEXT,
    "end"        TEXT,
    tz           TEXT,
    nap          INTEGER,
    score_state  TEXT,
    performance  REAL,
    consistency  REAL,
    efficiency   REAL,
    resp_rate    REAL,
    in_bed_ms    INTEGER,
    awake_ms     INTEGER,
    light_ms     INTEGER,
    sws_ms       INTEGER,
    rem_ms       INTEGER,
    disturbances INTEGER,
    need_ms      INTEGER,
    raw          TEXT,
    PRIMARY KEY (user_id, id)
);
CREATE INDEX IF NOT EXISTS sleeps_day ON sleeps(user_id, day);

CREATE TABLE IF NOT EXISTS workouts (
    id          TEXT NOT NULL,
    user_id     INTEGER NOT NULL,
    day         TEXT NOT NULL,
    start       TEXT,
    "end"       TEXT,
    tz          TEXT,
    sport       TEXT,
    score_state TEXT,
    strain      REAL,
    avg_hr      REAL,
    max_hr      REAL,
    kj          REAL,
    distance_m  REAL,
    zones       TEXT,
    raw         TEXT,
    PRIMARY KEY (user_id, id)
);
CREATE INDEX IF NOT EXISTS workouts_day ON workouts(user_id, day);

CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    day        TEXT NOT NULL,
    text       TEXT NOT NULL,
    tags       TEXT DEFAULT '[]',
    source     TEXT DEFAULT 'web',
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS notes_day ON notes(user_id, day);

CREATE TABLE IF NOT EXISTS events (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL,
    day      TEXT NOT NULL,
    start    TEXT,
    "end"    TEXT,
    title    TEXT,
    all_day  INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS events_day ON events(user_id, day);

CREATE TABLE IF NOT EXISTS coach_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS notified (
    user_id INTEGER NOT NULL,
    kind    TEXT NOT NULL,
    key     TEXT NOT NULL,
    PRIMARY KEY (user_id, kind, key)
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def conn():
    c = _connect()
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init() -> None:
    with conn() as c:
        c.executescript(SCHEMA)


def rows(sql: str, params=()) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def row(sql: str, params=()) -> dict | None:
    with conn() as c:
        r = c.execute(sql, params).fetchone()
        return dict(r) if r else None


def execute(sql: str, params=()) -> int:
    with conn() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid


def upsert(table: str, data: dict, conflict: list[str]) -> None:
    cols = list(data.keys())
    quoted = [f'"{k}"' for k in cols]
    updates = ", ".join(f'"{k}"=excluded."{k}"' for k in cols if k not in conflict)
    sql = (
        f"INSERT INTO {table} ({', '.join(quoted)}) VALUES ({', '.join('?' for _ in cols)}) "
        f"ON CONFLICT({', '.join(conflict)}) DO UPDATE SET {updates}"
    )
    with conn() as c:
        c.execute(sql, [data[k] for k in cols])


def get_user(user_id: int) -> dict | None:
    u = row("SELECT * FROM users WHERE id=?", (user_id,))
    if u:
        u["settings"] = json.loads(u.get("settings") or "{}")
        u["ics_urls"] = json.loads(u.get("ics_urls") or "[]")
    return u


def user_settings(user: dict) -> dict:
    s = {"tz": config.DEFAULT_TZ, "wake_time": "07:30"}
    s.update(user.get("settings") or {})
    return s


def mark_notified(user_id: int, kind: str, key: str) -> bool:
    """Returns True if this is the first time (i.e. we should notify)."""
    with conn() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO notified (user_id, kind, key) VALUES (?,?,?)", (user_id, kind, key)
        )
        return cur.rowcount == 1
