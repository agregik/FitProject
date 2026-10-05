import asyncio
import json

import httpx
import pytest

from app import calendar_ics, db

ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:1
DTSTART:%s
DTEND:%s
SUMMARY:New meeting
END:VEVENT
END:VCALENDAR
"""


def _ics_today() -> bytes:
    from datetime import date
    d = date.today().strftime("%Y%m%d")
    return ICS % (f"{d}T100000Z".encode(), f"{d}T110000Z".encode())


def _setup(user_id, urls):
    db.execute("UPDATE users SET ics_urls=? WHERE id=?", (json.dumps(urls), user_id))
    db.execute('INSERT INTO events (user_id, day, start, "end", title, all_day) VALUES (?,?,?,?,?,0)',
               (user_id, "2026-01-10", "2026-01-10T10:00:00+03:00", "2026-01-10T11:00:00+03:00", "Old meeting"))


def _fake_get(fail_urls):
    async def get(self, url, *a, **kw):
        if url in fail_urls:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, content=_ics_today(), request=httpx.Request("GET", url))
    return get


def test_failed_calendar_keeps_existing_events(user_id, monkeypatch):
    _setup(user_id, ["https://ok.example/a.ics", "https://down.example/b.ics"])
    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get({"https://down.example/b.ics"}))
    with pytest.raises(calendar_ics.CalendarFetchError) as e:
        asyncio.run(calendar_ics.sync_calendar(user_id))
    assert "down.example" not in str(e.value)  # secret ICS links must not leak into messages
    titles = [r["title"] for r in db.rows("SELECT title FROM events WHERE user_id=?", (user_id,))]
    assert titles == ["Old meeting"]


def test_successful_sync_replaces_events(user_id, monkeypatch):
    _setup(user_id, ["https://ok.example/a.ics"])
    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get(set()))
    assert asyncio.run(calendar_ics.sync_calendar(user_id)) == 1
    titles = [r["title"] for r in db.rows("SELECT title FROM events WHERE user_id=?", (user_id,))]
    assert titles == ["New meeting"]
