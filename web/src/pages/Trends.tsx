import { useEffect, useMemo, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api, isoDaysAgo, type Day } from "../api";
import { axisProps, dayLabel, fmt, Legend, Tip } from "../components";
import { recoveryStatus, type Palette } from "../theme";

const RANGES = [30, 90, 180, 365] as const;

function rolling(days: Day[], key: keyof Day, win = 7) {
  return days.map((_, i) => {
    const vals = days.slice(Math.max(0, i - win + 1), i + 1)
      .map((d) => d[key] as number | undefined).filter((v): v is number => v != null);
    return vals.length >= Math.min(3, win) ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  });
}

type Series = { key: string; name: string; color: string; unit: string; nd?: number; width?: number };

function LineCard({
  title, sub, data, series, c, domain, refY,
}: {
  title: string; sub?: string; data: Record<string, unknown>[]; series: Series[]; c: Palette;
  domain?: [number | string, number | string]; refY?: number;
}) {
  return (
    <div className="card">
      <div className="card-head">
        <div><h2>{title}</h2>{sub && <div className="sub" style={{ fontSize: 12 }}>{sub}</div>}</div>
        {series.length > 1 && <Legend items={series.map((s) => ({ label: s.name, color: s.color }))} />}
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={c.grid} />
          <XAxis dataKey="date" tickFormatter={dayLabel} minTickGap={32} {...axisProps(c)} />
          <YAxis domain={domain ?? ["auto", "auto"]} {...axisProps(c)} axisLine={false} width={48} />
          {refY != null && <ReferenceLine y={refY} stroke={c.axis} />}
          <Tooltip cursor={{ stroke: c.muted, strokeWidth: 1 }} content={({ active, payload, label }) =>
            active && payload?.length ? (
              <Tip title={dayLabel(String(label))} items={series.map((s) => {
                const v = payload[0].payload[s.key] as number | null;
                return { name: s.name, value: v == null ? "—" : `${fmt(v, s.nd ?? 0)} ${s.unit}`, color: s.color };
              })} />
            ) : null} />
          {series.map((s) => (
            <Line key={s.key} dataKey={s.key} stroke={s.color} strokeWidth={s.width ?? 2} dot={false}
                  connectNulls strokeLinecap="round" strokeLinejoin="round"
                  activeDot={{ r: 4, stroke: c.surface, strokeWidth: 2 }} isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function Trends({ c }: { c: Palette }) {
  const [range, setRange] = useState<number>(90);
  const [days, setDays] = useState<Day[]>([]);
  const [loading, setLoading] = useState(true);
  const [table, setTable] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.days(isoDaysAgo(range - 1)).then((d) => { setDays(d); setLoading(false); });
  }, [range]);

  const data = useMemo(() => {
    const hrv7 = rolling(days, "hrv");
    const rec7 = rolling(days, "recovery");
    const skin = days.map((d) => d.skin_temp).filter((v): v is number => v != null);
    const skinBase = skin.length ? skin.reduce((a, b) => a + b, 0) / skin.length : 0;
    return days.map((d, i) => ({
      ...d, hrv7: hrv7[i], rec7: rec7[i],
      skin_dev: d.skin_temp != null ? d.skin_temp - skinBase : null,
    }));
  }, [days]);

  const avg = (k: keyof Day) => {
    const v = days.map((d) => d[k] as number | undefined).filter((x): x is number => x != null);
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Тренды</h1>
          <div className="sub">
            Среднее за период: recovery {fmt(avg("recovery"))}% · HRV {fmt(avg("hrv"))} мс · сон {fmt(avg("sleep_hours"), 1)} ч · strain {fmt(avg("strain"), 1)}
          </div>
        </div>
        <div className="row">
          <div className="seg">
            {RANGES.map((r) => (
              <button key={r} className={range === r ? "on" : ""} onClick={() => setRange(r)}>{r} дн</button>
            ))}
          </div>
          <div className="seg">
            <button className={!table ? "on" : ""} onClick={() => setTable(false)}>Графики</button>
            <button className={table ? "on" : ""} onClick={() => setTable(true)}>Таблица</button>
          </div>
        </div>
      </div>

      <div className={loading ? "loading" : ""}>
        {table ? <DataTable days={days} /> : (
          <div className="grid g2">
            <div className="card" style={{ gridColumn: "1 / -1" }}>
              <div className="card-head">
                <div><h2>Recovery</h2><div className="sub" style={{ fontSize: 12 }}>Цвет столбца: зона восстановления</div></div>
                <Legend items={[
                  { label: "≥67 зелёная", color: c.good, kind: "rect" },
                  { label: "34–66 жёлтая", color: c.warning, kind: "rect" },
                  { label: "<34 красная", color: c.critical, kind: "rect" },
                  { label: "Среднее 7 дн", color: c.ink2 },
                ]} />
              </div>
              <ResponsiveContainer width="100%" height={220}>
                <ComposedChart data={data} margin={{ top: 8, right: 8, left: -20, bottom: 0 }} barCategoryGap={range > 90 ? 0.5 : 2}>
                  <CartesianGrid vertical={false} stroke={c.grid} />
                  <XAxis dataKey="date" tickFormatter={dayLabel} minTickGap={32} {...axisProps(c)} />
                  <YAxis domain={[0, 100]} ticks={[0, 33, 67, 100]} {...axisProps(c)} axisLine={false} width={48} />
                  <Tooltip cursor={{ fill: c.grid, opacity: 0.6 }} content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const p = payload[0].payload;
                    const s = recoveryStatus(p.recovery, c);
                    return <Tip title={`${dayLabel(p.date)} · ${s.label}`} items={[
                      { name: "Recovery", value: `${fmt(p.recovery)}%`, color: s.color },
                      { name: "Среднее 7 дн", value: `${fmt(p.rec7)}%`, color: c.ink2 },
                      { name: "Теги", value: p.tags.length ? p.tags.map((t: string) => "#" + t).join(" ") : "—", color: "transparent" },
                    ]} />;
                  }} />
                  <Bar dataKey="recovery" maxBarSize={24} radius={range > 90 ? [2, 2, 0, 0] : [4, 4, 0, 0]} isAnimationActive={false}>
                    {data.map((d) => <Cell key={d.date} fill={recoveryStatus(d.recovery, c).color} />)}
                  </Bar>
                  <Line dataKey="rec7" stroke={c.ink2} strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            <LineCard c={c} title="HRV" sub="Главный индикатор восстановления"
                      data={data} series={[
                        { key: "hrv", name: "За день", color: c.need, unit: "мс", width: 1.5 },
                        { key: "hrv7", name: "Среднее 7 дн", color: c.hrv, unit: "мс" },
                      ]} />
            <LineCard c={c} title="Пульс в покое" sub="Ниже — лучше" data={data}
                      series={[{ key: "rhr", name: "Пульс", color: c.aqua, unit: "уд/мин" }]} />
            <LineCard c={c} title="Сон: фактически и нужно" data={data} domain={[4, 10]} series={[
              { key: "sleep_hours", name: "Спал", color: c.sleep, unit: "ч", nd: 1 },
              { key: "sleep_need_hours", name: "Нужно", color: c.need, unit: "ч", nd: 1 },
            ]} />
            <LineCard c={c} title="Температура кожи" sub="Отклонение от средней за период, °C. Рост часто бывает перед болезнью"
                      data={data} refY={0}
                      series={[{ key: "skin_dev", name: "Отклонение", color: c.strain, unit: "°C", nd: 2 }]} />

            <div className="card" style={{ gridColumn: "1 / -1" }}>
              <div className="card-head"><h2>Strain</h2></div>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={data} margin={{ top: 8, right: 8, left: -20, bottom: 0 }} barCategoryGap={range > 90 ? 0.5 : 2}>
                  <CartesianGrid vertical={false} stroke={c.grid} />
                  <XAxis dataKey="date" tickFormatter={dayLabel} minTickGap={32} {...axisProps(c)} />
                  <YAxis domain={[0, 21]} ticks={[0, 7, 14, 21]} {...axisProps(c)} axisLine={false} width={48} />
                  <Tooltip cursor={{ fill: c.grid, opacity: 0.6 }} content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const p = payload[0].payload as Day;
                    return <Tip title={dayLabel(p.date)} items={[
                      { name: "Strain", value: fmt(p.strain, 1), color: c.strain },
                      ...p.workouts.map((w) => ({ name: w.sport, value: fmt(w.strain, 1), color: "transparent" })),
                    ]} />;
                  }} />
                  <Bar dataKey="strain" fill={c.strain} maxBarSize={24} radius={range > 90 ? [2, 2, 0, 0] : [4, 4, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

function DataTable({ days }: { days: Day[] }) {
  return (
    <div className="card">
      <div className="card-head">
        <h2>Все дни</h2>
        <a className="btn" href="/api/export.csv" style={{ textDecoration: "none", color: "inherit" }}>Скачать CSV</a>
      </div>
      <div className="table-wrap" style={{ maxHeight: 600 }}>
        <table className="data">
          <thead><tr>
            <th>Дата</th><th>Recovery</th><th>HRV</th><th>Пульс</th><th>Сон, ч</th><th>Нужно, ч</th><th>Сон %</th>
            <th>Strain</th><th>Темп.</th><th>Встречи</th><th>Теги</th>
          </tr></thead>
          <tbody>
            {[...days].reverse().map((d) => (
              <tr key={d.date}>
                <td>{dayLabel(d.date)}</td><td>{fmt(d.recovery)}</td><td>{fmt(d.hrv)}</td><td>{fmt(d.rhr)}</td>
                <td>{fmt(d.sleep_hours, 1)}</td><td>{fmt(d.sleep_need_hours, 1)}</td><td>{fmt(d.sleep_performance)}</td>
                <td>{fmt(d.strain, 1)}</td><td>{fmt(d.skin_temp, 1)}</td><td>{d.meetings ?? "—"}</td>
                <td className="tag">{d.tags.map((t) => "#" + t).join(" ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
