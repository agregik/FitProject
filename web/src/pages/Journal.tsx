import { useEffect, useMemo, useState } from "react";
import { api, isoDaysAgo, type Day, type Note } from "../api";
import { dayLabelLong, fmt } from "../components";
import { recoveryStatus, type Palette } from "../theme";

export function QuickNote({ onSaved, title }: { onSaved?: () => void; title?: string }) {
  const [text, setText] = useState("");
  const [day, setDay] = useState(isoDaysAgo(0));
  const [tags, setTags] = useState<{ tag: string; count: number }[]>([]);
  const [saving, setSaving] = useState(false);
  const [ok, setOk] = useState(false);

  useEffect(() => { api.tags().then((t) => setTags(t.slice(0, 14))); }, []);

  const toggle = (tag: string) => {
    const h = "#" + tag;
    setText((t) => (t.includes(h) ? t.replace(h, "").replace(/\s+/g, " ").trim() : `${t} ${h}`.trim()));
  };

  const save = async () => {
    if (!text.trim()) return;
    setSaving(true);
    await api.addNote(text, day);
    setText(""); setSaving(false); setOk(true);
    setTimeout(() => setOk(false), 1800);
    onSaved?.();
  };

  return (
    <div className="card">
      <div className="card-head">
        <h2>{title ?? "Новая запись"}</h2>
        <input type="date" className="input" style={{ width: 160 }} value={day} max={isoDaysAgo(0)}
               onChange={(e) => setDay(e.target.value)} />
      </div>
      <div className="stack">
        <textarea className="textarea" rows={2} value={text} placeholder="Например: бокал вина за ужином #алкоголь"
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) save(); }} />
        <div className="chips">
          {tags.map((t) => (
            <button key={t.tag} className={`chip ${text.includes("#" + t.tag) ? "on" : ""}`} onClick={() => toggle(t.tag)}>
              #{t.tag}
            </button>
          ))}
        </div>
        <div className="row">
          <button className="btn primary" disabled={saving || !text.trim()} onClick={save}>Сохранить</button>
          {ok && <span className="sub">Записано ✓</span>}
          <span className="muted" style={{ fontSize: 12 }}>Теги через #, записи вечером влияют на recovery следующего утра</span>
        </div>
      </div>
    </div>
  );
}

export default function Journal({ c }: { c: Palette }) {
  const [notes, setNotes] = useState<Note[]>([]);
  const [days, setDays] = useState<Record<string, Day>>({});
  const [filter, setFilter] = useState<string | null>(null);

  const load = () => {
    const start = isoDaysAgo(60);
    api.notes(start).then(setNotes);
    api.days(start).then((ds) => setDays(Object.fromEntries(ds.map((d) => [d.date, d]))));
  };
  useEffect(load, []);

  const grouped = useMemo(() => {
    const g: Record<string, Note[]> = {};
    for (const n of notes) {
      if (filter && !n.tags.includes(filter)) continue;
      (g[n.day!] ??= []).push(n);
    }
    return Object.entries(g).sort((a, b) => (a[0] < b[0] ? 1 : -1));
  }, [notes, filter]);

  const allTags = useMemo(() => {
    const m: Record<string, number> = {};
    notes.forEach((n) => n.tags.forEach((t) => (m[t] = (m[t] ?? 0) + 1)));
    return Object.entries(m).sort((a, b) => b[1] - a[1]);
  }, [notes]);

  const nextDay = (iso: string) => {
    const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + 1);
    return d.toLocaleDateString("sv-SE");
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Журнал</h1>
          <div className="sub">Твои привычки и события. WHOOP не отдаёт свой журнал через API, поэтому ведём свой, и без ограничений по списку.</div>
        </div>
      </div>
      <QuickNote onSaved={load} />
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-head">
          <h2>Последние 60 дней</h2>
        </div>
        <div className="chips" style={{ marginBottom: 12 }}>
          <button className={`chip ${!filter ? "on" : ""}`} onClick={() => setFilter(null)}>Все</button>
          {allTags.map(([t, n]) => (
            <button key={t} className={`chip ${filter === t ? "on" : ""}`} onClick={() => setFilter(t)}>#{t} · {n}</button>
          ))}
        </div>
        {grouped.length === 0 && <div className="sub">Записей пока нет.</div>}
        {grouped.map(([day, ns]) => {
          const next = days[nextDay(day)];
          const st = recoveryStatus(next?.recovery, c);
          return (
            <div key={day} style={{ marginBottom: 14 }}>
              <div className="row" style={{ justifyContent: "space-between", marginBottom: 2 }}>
                <b style={{ fontSize: 14 }}>{dayLabelLong(day)}</b>
                {next?.recovery != null && (
                  <span className="pill"><span className="pill-dot" style={{ background: st.color }} />
                    на утро: {fmt(next.recovery)}% · HRV {fmt(next.hrv)}</span>
                )}
              </div>
              {ns.map((n) => (
                <div className="note" key={n.id}>
                  <div className="note-text">
                    {n.text.split(/(#[\p{L}\p{N}_-]+)/u).map((part, i) =>
                      part.startsWith("#") ? <span className="tag" key={i}>{part}</span> : part)}
                    <div className="note-src">{n.source === "telegram" ? "из Telegram" : "с сайта"}</div>
                  </div>
                  <button className="x-btn" title="Удалить" onClick={() => api.delNote(n.id).then(load)}>×</button>
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </>
  );
}
