import { useEffect, useRef, useState } from "react";
import { api, type Me } from "../api";

const SUGGESTIONS = [
  "Почему у меня сегодня низкий recovery?",
  "Что сильнее всего портит мой сон?",
  "Как мне построить тренировки на эту неделю?",
  "Сравни эту неделю с прошлой",
  "Во сколько мне ложиться, чтобы восстановиться?",
];

export default function Coach({ me }: { me: Me | null }) {
  const [msgs, setMsgs] = useState<{ role: "user" | "assistant"; content: string }[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => { api.coachHistory().then(setMsgs); }, []);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, busy]);

  const ask = async (text: string) => {
    if (!text.trim() || busy) return;
    setMsgs((m) => [...m, { role: "user", content: text }]);
    setQ(""); setBusy(true);
    try {
      const r = await api.ask(text);
      setMsgs((m) => [...m, { role: "assistant", content: r.answer }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "assistant", content: `Ошибка: ${(e as Error).message}` }]);
    } finally { setBusy(false); }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>AI-коуч</h1>
          <div className="sub">Видит твои данные WHOOP за 45 дней, журнал, календарь и найденные закономерности.</div>
        </div>
        {msgs.length > 0 && (
          <button className="btn" onClick={() => api.clearCoach().then(() => setMsgs([]))}>Новый диалог</button>
        )}
      </div>
      {me && !me.coach_ai && (
        <div className="banner">
          <span>Сейчас коуч работает в упрощённом режиме, по правилам. Добавь <code>ANTHROPIC_API_KEY</code> в backend/.env,
          и он будет отвечать на любые вопросы.</span>
        </div>
      )}
      <div className="card">
        <div className="chat">
          {msgs.length === 0 && (
            <div className="stack">
              <div className="sub">С чего начнём?</div>
              <div className="chips">
                {SUGGESTIONS.map((s) => <button key={s} className="chip" onClick={() => ask(s)}>{s}</button>)}
              </div>
            </div>
          )}
          {msgs.map((m, i) => <div key={i} className={`msg ${m.role}`}>{m.content}</div>)}
          {busy && <div className="typing">Коуч думает…</div>}
          <div ref={end} />
        </div>
        <div className="row" style={{ marginTop: 16, flexWrap: "nowrap" }}>
          <input className="input" value={q} placeholder="Спроси про сон, нагрузку, восстановление…"
                 onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && ask(q)} />
          <button className="btn primary" disabled={busy || !q.trim()} onClick={() => ask(q)}>Спросить</button>
        </div>
      </div>
    </>
  );
}
