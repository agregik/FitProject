"""Import calendars via secret ICS links (Google, iCloud, Outlook, Яндекс)."""
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import icalendar
import recurring_ical_events

from . import db

log = logging.getLogger("calendar")


class CalendarFetchError(RuntimeError):
    """A calendar couldn't be downloaded or parsed; stored events are left untouched."""


def _to_local(v, tz: ZoneInfo) -> tuple[datetime, bool]:
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=tz)
        return v.astimezone(tz), False
    return datetime(v.year, v.month, v.day, tzinfo=tz), True


async def sync_calendar(user_id: int) -> int:
    user = db.get_user(user_id)
    urls = user["ics_urls"]
    if not urls:
        return 0
    tz = ZoneInfo(db.user_settings(user)["tz"])
    start = date.today() - timedelta(days=400)
    end = date.today() + timedelta(days=14)
    rows = []
    failed = []
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        for n, url in enumerate(urls, 1):
            try:
                r = await client.get(url.replace("webcal://", "https://"))
                r.raise_for_status()
                cal = icalendar.Calendar.from_ical(r.content)
            except Exception as e:  # noqa: BLE001
                # Don't log the URL itself: secret ICS links are credentials.
                log.warning("calendar #%d for user %s failed: %s", n, user_id, type(e).__name__)
                failed.append(n)
                continue
            for ev in recurring_ical_events.of(cal).between(start, end):
                if str(ev.get("TRANSP", "")).upper() == "TRANSPARENT":
                    continue
                s, all_day = _to_local(ev.get("DTSTART").dt, tz)
                e_raw = ev.get("DTEND")
                e = _to_local(e_raw.dt, tz)[0] if e_raw else s + timedelta(hours=1)
                rows.append((user_id, s.date().isoformat(), s.isoformat(), e.isoformat(),
                             str(ev.get("SUMMARY", "")), int(all_day)))
    if failed:
        # Events aren't tagged by source calendar, so a partial replace would silently drop
        # the failed calendar's history. Keep everything until all calendars load cleanly.
        raise CalendarFetchError(
            f"Не удалось загрузить календар{'ь' if len(failed) == 1 else 'и'} №{', №'.join(map(str, failed))}. "
            "Старые события сохранены, попробуй позже или проверь ссылку.")
    with db.conn() as c:
        c.execute("DELETE FROM events WHERE user_id=?", (user_id,))
        c.executemany('INSERT INTO events (user_id, day, start, "end", title, all_day) VALUES (?,?,?,?,?,?)', rows)
    log.info("calendar user %s: %d events", user_id, len(rows))
    return len(rows)
