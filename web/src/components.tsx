import type { ReactNode } from "react";
import type { Palette } from "./theme";

export const fmt = (v: number | null | undefined, nd = 0) =>
  v == null || Number.isNaN(v) ? "—" : v.toLocaleString("ru-RU", { maximumFractionDigits: nd, minimumFractionDigits: nd });

export const dayLabel = (iso: string) =>
  new Date(iso + "T12:00:00").toLocaleDateString("ru-RU", { day: "numeric", month: "short" });

export const dayLabelLong = (iso: string) => {
  const s = new Date(iso + "T12:00:00").toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" });
  return s.charAt(0).toUpperCase() + s.slice(1);
};

export function RecoveryRing({ value, color, size = 168 }: { value?: number | null; color: string; size?: number }) {
  const stroke = 12;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, value ?? 0)) / 100;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img"
         aria-label={`Recovery ${value ?? "нет данных"}%`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-2)" strokeWidth={stroke} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
              strokeLinecap="round" strokeDasharray={`${circ * pct} ${circ}`}
              transform={`rotate(-90 ${size / 2} ${size / 2})`} style={{ transition: "stroke-dasharray .9s cubic-bezier(.22,.61,.36,1), stroke .4s" }} />
      <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central" fill="var(--ink)"
            fontSize={size * 0.3} fontWeight={700} letterSpacing="-0.03em">{value == null ? "—" : Math.round(value)}</text>
      <text x="50%" y={size / 2 + size * 0.2} textAnchor="middle" fill="var(--muted)" fontSize={12} fontWeight={600}>recovery %</text>
    </svg>
  );
}

export function StatTile({
  label, value, unit, nd = 0, base, higherIsGood = true, children,
}: {
  label: string; value?: number | null; unit?: string; nd?: number;
  base?: { mean: number; sd: number }; higherIsGood?: boolean; children?: ReactNode;
}) {
  let delta: ReactNode = null;
  if (value != null && base) {
    const diff = value - base.mean;
    const small = Math.abs(diff) < base.sd * 0.5;
    const good = higherIsGood ? diff > 0 : diff < 0;
    const cls = small ? "flat" : good ? "good" : "bad";
    delta = (
      <div className={`delta ${cls}`}>
        {small ? "≈ " : diff > 0 ? "▲ " : "▼ "}
        {small ? "в норме" : `${diff > 0 ? "+" : "−"}${fmt(Math.abs(diff), nd)} к норме`}
        <span className="muted"> · норма {fmt(base.mean, nd)}</span>
      </div>
    );
  }
  return (
    <div className="card">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{fmt(value, nd)}{unit && <span className="tile-unit">{unit}</span>}</div>
      {delta}
      {children}
    </div>
  );
}

type TTItem = { name: string; value: string; color: string };
export function Tip({ title, items }: { title: string; items: TTItem[] }) {
  return (
    <div className="tt">
      <div className="tt-date">{title}</div>
      {items.map((i) => (
        <div className="tt-row" key={i.name}>
          <span className="tt-name"><span className="tt-key" style={{ background: i.color }} />{i.name}</span>
          <span className="tt-val">{i.value}</span>
        </div>
      ))}
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color: string; kind?: "line" | "rect" }[] }) {
  return (
    <div className="legend">
      {items.map((i) => (
        <span key={i.label}>
          <i className={i.kind === "rect" ? "lk-rect" : "lk-line"} style={{ background: i.color }} />
          {i.label}
        </span>
      ))}
    </div>
  );
}

export const axisProps = (c: Palette) => ({
  stroke: c.axis,
  tick: { fill: c.muted, fontSize: 11 },
  axisLine: false,
  tickLine: false,
});
