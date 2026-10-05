import { useEffect, useState } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type Today as TodayT } from "../api";
import { axisProps, dayLabel, dayLabelLong, fmt, RecoveryRing, StatTile, Tip } from "../components";
import { recoveryStatus, type Palette } from "../theme";
import { QuickNote } from "./Journal";

export default function Today({ c }: { c: Palette }) {
  const [t, setT] = useState<TodayT | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = () => api.today().then(setT).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  if (err) return <div className="card">Не удалось загрузить: {err}</div>;
  if (!t) return <div className="muted">Загрузка…</div>;
  const d = t.day;
  if (!d) return <div className="card">Пока нет данных. Подключи WHOOP в настройках и дождись синхронизации.</div>;

  const st = recoveryStatus(d.recovery, c);
  const b = t.baseline;
  const tgt = t.strain_target;
  const strainNow = d.strain ?? 0;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Сегодня</h1>
          <div className="sub">
            {dayLabelLong(d.date)}{!t.is_today && " · recovery за сегодня ещё не посчитан"}
          </div>
        </div>
      </div>

      <div className="grid g2" style={{ marginBottom: 16 }}>
        <div className="card hero">
          <RecoveryRing value={d.recovery} color={st.color} />
          <div className="stack">
            <span className="pill"><span className="pill-dot" style={{ background: st.color }} />{st.label}</span>
            <div style={{ fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>{tgt.label}</div>
            {tgt.min != null && (
              <div>
                <div className="sub" style={{ marginBottom: 8 }}>
                  Целевой strain {tgt.min}–{tgt.max} · сейчас {fmt(strainNow, 1)}
                </div>
                <div className="meter" aria-label={`Целевой strain от ${tgt.min} до ${tgt.max}, сейчас ${fmt(strainNow, 1)}`}>
                  <div className="meter-zone" style={{
                    left: `${(tgt.min / 21) * 100}%`, width: `${((tgt.max! - tgt.min) / 21) * 100}%`, background: c.strain,
                  }} />
                  <div className="meter-now" style={{ left: `calc(${(Math.min(strainNow, 21) / 21) * 100}% - 2px)` }} />
                </div>
                <div className="meter-scale"><span>0</span><span>7</span><span>14</span><span>21</span></div>
              </div>
            )}
            {t.bedtime && (
              <div className="sub">
                Отбой около <b style={{ color: "var(--ink)" }}>{t.bedtime.bedtime}</b>, чтобы к {t.bedtime.wake_time} получить
                {" "}{fmt(t.bedtime.need_hours, 1)} ч сна
              </div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-head"><h2>Сигналы</h2></div>
          {t.alerts.length === 0 && <div className="sub">Всё в пределах твоей нормы</div>}
          {t.alerts.map((a, i) => (
            <div className="alert" key={i}>
              <span className="alert-dot" style={{ background: a.level === "warn" ? c.warning : a.level === "good" ? c.good : c.hrv }} />
              <span>{a.text}</span>
            </div>
          ))}
          <div style={{ marginTop: 16 }}>
            <div className="card-head" style={{ marginBottom: 4 }}>
              <h2>Recovery за 7 дней</h2>
            </div>
            <ResponsiveContainer width="100%" height={120}>
              <BarChart data={t.last7} margin={{ top: 8, right: 0, left: -28, bottom: 0 }}>
                <XAxis dataKey="date" tickFormatter={dayLabel} {...axisProps(c)} />
                <YAxis domain={[0, 100]} ticks={[0, 50, 100]} {...axisProps(c)} axisLine={false} />
                <Tooltip cursor={{ fill: c.grid, opacity: 0.6, radius: 8 } as object} content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const p = payload[0].payload;
                  const s = recoveryStatus(p.recovery, c);
                  return <Tip title={dayLabel(p.date)} items={[
                    { name: "Recovery", value: `${fmt(p.recovery)}%`, color: s.color },
                    { name: "HRV", value: `${fmt(p.hrv)} мс`, color: c.hrv },
                    { name: "Сон", value: `${fmt(p.sleep_hours, 1)} ч`, color: c.sleep },
                  ]} />;
                }} />
                <Bar dataKey="recovery" maxBarSize={22} radius={[8, 8, 8, 8]}>
                  {t.last7.map((x) => <Cell key={x.date} fill={recoveryStatus(x.recovery, c).color} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="grid g4" style={{ marginBottom: 16 }}>
        <StatTile label="HRV" value={d.hrv} unit="мс" base={b.hrv} />
        <StatTile label="Пульс в покое" value={d.rhr} unit="уд/мин" base={b.rhr} higherIsGood={false} />
        <StatTile label="Сон" value={d.sleep_hours} unit="ч" nd={1} base={b.sleep_hours}>
          <div className="sub" style={{ fontSize: 12, marginTop: 4 }}>
            нужно {fmt(d.sleep_need_hours, 1)} ч · {fmt(d.sleep_performance)}% · глубокий {fmt(d.deep_hours, 1)} ч · REM {fmt(d.rem_hours, 1)} ч
          </div>
        </StatTile>
        <StatTile label="Strain" value={d.strain} nd={1} base={b.strain}>
          <div className="sub" style={{ fontSize: 12, marginTop: 4 }}>
            {d.workouts.length ? d.workouts.map((w) => `${w.sport} ${fmt(w.strain, 1)}`).join(", ") : "тренировок пока нет"}
          </div>
        </StatTile>
        <StatTile label="Температура кожи" value={d.skin_temp} unit="°C" nd={1} base={b.skin_temp} higherIsGood={false} />
        <StatTile label="SpO₂" value={d.spo2} unit="%" nd={1} base={b.spo2} />
        <StatTile label="Дыхание во сне" value={d.resp_rate} unit="/мин" nd={1} base={b.resp_rate} higherIsGood={false} />
        <YesterdayCalendar />
      </div>

      <QuickNote onSaved={load} title="Что было вчера вечером / сегодня?" />
    </>
  );
}

function YesterdayCalendar() {
  const [info, setInfo] = useState<{ n?: number; text: string }>({ text: "…" });
  useEffect(() => {
    const y = new Date(); y.setDate(y.getDate() - 1);
    const iso = y.toLocaleDateString("sv-SE");
    api.days(iso, iso).then((ds) => {
      const d = ds[0];
      if (!d || d.meetings == null) setInfo({ text: "календарь не подключён" });
      else setInfo({ n: d.meetings, text: `${fmt(d.busy_hours, 1)} ч занято${d.late_events ? ` · поздних: ${d.late_events}` : ""}` });
    });
  }, []);
  return (
    <div className="card">
      <div className="tile-label">Встречи вчера</div>
      <div className="tile-value">{info.n ?? "—"}</div>
      <div className="sub" style={{ fontSize: 12, marginTop: 4 }}>{info.text}</div>
    </div>
  );
}
