import { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis,
} from "recharts";
import { api, type Driver, type Insights as InsightsT } from "../api";
import { axisProps, fmt, Tip } from "../components";
import type { Palette } from "../theme";

const CONF_ICON: Record<string, string> = { "высокая": "●●●", "средняя": "●●○", "низкая": "●○○" };

export default function Insights({ c }: { c: Palette }) {
  const [ins, setIns] = useState<InsightsT | null>(null);
  const [period, setPeriod] = useState(180);
  const [driver, setDriver] = useState<string>("sleep_hours");

  useEffect(() => { api.insights(period).then(setIns); }, [period]);
  if (!ins) return <div className="muted">Считаю закономерности…</div>;

  const maxAbs = Math.max(20, ...ins.tags.flatMap((t) => [Math.abs(t.ci_low), Math.abs(t.ci_high)]));
  const pct = (v: number) => 50 + (v / maxAbs) * 50;
  const d = ins.drivers.find((x) => x.key === driver) ?? ins.drivers[0];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Инсайты</h1>
          <div className="sub">Что влияет именно на твоё восстановление. Считается по {ins.days_with_data} дням с данными.</div>
        </div>
        <div className="seg">
          {[60, 180, 365].map((p) => (
            <button key={p} className={period === p ? "on" : ""} onClick={() => setPeriod(p)}>{p} дн</button>
          ))}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head">
          <div>
            <h2>Привычки → recovery на следующее утро</h2>
            <div className="sub" style={{ fontSize: 12 }}>
              Разница среднего recovery после дней с тегом и без него. Тонкая линия — 95% интервал: если он
              пересекает ноль, эффект может быть случайным. Уверенность учитывает, что тегов много и какой-то
              из них «выстрелит» по чистой случайности.
            </div>
          </div>
          <div className="legend">
            <span><i className="lk-rect" style={{ background: c.pos }} />помогает</span>
            <span><i className="lk-rect" style={{ background: c.neg }} />мешает</span>
          </div>
        </div>
        {ins.tags.length === 0 && (
          <div className="sub">Пока мало записей. Нужно хотя бы 7 дней с тегом и 7 дней с записями без него: веди журнал
            каждый вечер, даже если писать нечего («обычный день»). Дни без записей не считаются «днями без привычки».</div>
        )}
        {ins.tags.map((t) => {
          const w = (Math.abs(t.recovery_diff) / maxAbs) * 50;
          const pos = t.recovery_diff >= 0;
          const dim = t.confidence === "низкая" ? 0.4 : 1;
          return (
            <div className="effect-row" key={t.tag}
                 title={`После #${t.tag}: ${t.recovery_with}% (${t.n} дн.) · без: ${t.recovery_without}% (${t.n_without} дн.)\n`
                   + `95% интервал: ${fmt(t.ci_low, 1)}…${fmt(t.ci_high, 1)} п. · p=${t.p_value} · с поправкой q=${t.q_value}`}>
              <div><span className="tag">#{t.tag}</span> <span className="muted" style={{ fontSize: 12 }}>×{t.n}</span></div>
              <div className="effect-bar-wrap">
                <div className="effect-mid" />
                <div className="effect-bar" style={{
                  left: pos ? "50%" : `${50 - w}%`, width: `${w}%`, background: pos ? c.pos : c.neg, opacity: dim,
                  borderRadius: pos ? "0 4px 4px 0" : "4px 0 0 4px",
                }} />
                <div className="effect-ci" style={{ left: `${pct(t.ci_low)}%`, width: `${pct(t.ci_high) - pct(t.ci_low)}%` }} />
              </div>
              <div className="effect-meta">
                <b style={{ color: "var(--ink)" }}>{pos ? "+" : "−"}{fmt(Math.abs(t.recovery_diff))} п.</b>
                {t.hrv_diff_pct != null && <> · HRV {t.hrv_diff_pct > 0 ? "+" : ""}{fmt(t.hrv_diff_pct)}%</>}
                <br /><span className="muted">{fmt(t.ci_low)}…{fmt(t.ci_high)}</span>
                {" · "}<span title="уверенность">{CONF_ICON[t.confidence]} {t.confidence}</span>
              </div>
            </div>
          );
        })}
        {ins.pending_tags.length > 0 && (
          <div className="pending-tags">
            <span className="sub" style={{ fontSize: 12 }}>Собираем данные:</span>
            {ins.pending_tags.map((p) => (
              <span key={p.tag} className="pending-tag" title={p.n < p.need
                ? `Нужно ещё ${p.need - p.n} дн. с этим тегом`
                : `Не с чем сравнить: нужно ${p.need} дн. с записями, но без этого тега (сейчас ${p.n_without})`}>
                #{p.tag} <span className="muted">{p.n}/{p.need}</span>
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="grid g2">
        <div className="card">
          <div className="card-head"><h2>Факторы</h2></div>
          <div className="stack">
            {ins.drivers.map((x) => (
              <button key={x.key} onClick={() => setDriver(x.key)}
                      className="alert" style={{
                        border: x.key === d?.key ? "1px solid var(--accent)" : "1px solid transparent",
                        cursor: "pointer", textAlign: "left", opacity: x.confidence === "низкая" ? 0.6 : 1,
                      }}>
                <span style={{ flex: 1 }}>
                  <b>{x.label}</b><br />
                  <span className="sub">{x.explain}: {x.slope > 0 ? "+" : ""}{fmt(x.slope, 1)} п. recovery</span>
                </span>
                <span className="sub" style={{ whiteSpace: "nowrap", fontSize: 12 }}>
                  r = {fmt(x.r, 2)} · n = {x.n}<br />{CONF_ICON[x.confidence]}
                </span>
              </button>
            ))}
          </div>
        </div>
        {d && <DriverScatter d={d} c={c} />}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-head"><h2>Recovery по дням недели</h2></div>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={ins.weekday} margin={{ top: 16, right: 8, left: -20, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke={c.grid} strokeDasharray="3 5" />
            <XAxis dataKey="weekday" {...axisProps(c)} />
            <YAxis domain={[0, 100]} ticks={[0, 50, 100]} {...axisProps(c)} axisLine={false} width={48} />
            <Tooltip cursor={{ fill: c.grid, opacity: 0.6 }} content={({ active, payload }) =>
              active && payload?.length ? (
                <Tip title={String(payload[0].payload.weekday)} items={[
                  { name: "Recovery", value: `${fmt(payload[0].payload.recovery)}%`, color: c.hrv },
                  { name: "Дней", value: String(payload[0].payload.n), color: "transparent" },
                ]} />
              ) : null} />
            <Bar dataKey="recovery" fill={c.hrv} maxBarSize={24} radius={[8, 8, 8, 8]} isAnimationActive={false}>
              <LabelList dataKey="recovery" position="top" fill={c.ink2} fontSize={11}
                         formatter={(v: number) => fmt(v)} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}

function DriverScatter({ d, c }: { d: Driver; c: Palette }) {
  const xName = d.key === "bedtime" ? "Отбой (0 = полночь)" : d.label.split("→")[0].trim();
  return (
    <div className="card">
      <div className="card-head">
        <div><h2>{d.label}</h2><div className="sub" style={{ fontSize: 12 }}>
          Каждая точка — один день, n = {d.n} · r = {fmt(d.r, 2)} (95%: {fmt(d.r_low, 2)}…{fmt(d.r_high, 2)})
        </div></div>
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <ScatterChart margin={{ top: 8, right: 8, left: -20, bottom: 8 }}>
          <CartesianGrid stroke={c.grid} strokeDasharray="3 5" />
          <XAxis type="number" dataKey="x" name={xName} domain={["auto", "auto"]} {...axisProps(c)} />
          <YAxis type="number" dataKey="y" name="Recovery" domain={[0, 100]} {...axisProps(c)} width={48} />
          <Tooltip cursor={{ stroke: c.muted }} content={({ active, payload }) =>
            active && payload?.length ? (
              <Tip title={xName} items={[
                { name: xName, value: fmt(payload[0].payload.x, 1), color: "transparent" },
                { name: "Recovery", value: `${fmt(payload[0].payload.y)}%`, color: c.hrv },
              ]} />
            ) : null} />
          <Scatter data={d.points} fill={c.hrv} fillOpacity={0.7} stroke={c.surface} strokeWidth={1}
                   isAnimationActive={false} shape="circle" />
        </ScatterChart>
      </ResponsiveContainer>
      <div className="sub" style={{ fontSize: 12 }}>Корреляция не означает причинность, но показывает, куда смотреть.</div>
    </div>
  );
}
