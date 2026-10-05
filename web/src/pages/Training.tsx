import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, isoDaysAgo, type Exercise, type LiftProgress, type LiftSession, type LiftSessionIn } from "../api";
import { axisProps, dayLabel, dayLabelLong, fmt, Legend, Tip } from "../components";
import type { Palette } from "../theme";

type DraftSet = { weight: string; reps: string; rir: string };
type DraftItem = { exercise: string; group: string; sets: DraftSet[] };
type Draft = { id?: number; day: string; title: string; items: DraftItem[] };

const emptySet = (): DraftSet => ({ weight: "", reps: "", rir: "" });
const emptyItem = (): DraftItem => ({ exercise: "", group: "", sets: [emptySet()] });
const emptyDraft = (): Draft => ({ day: isoDaysAgo(0), title: "", items: [emptyItem()] });
const kg = (v: number | null | undefined) => fmt(v, v != null && !Number.isInteger(v) ? 1 : 0);
const num = (s: string) => (s.trim() === "" ? null : Number(s.replace(",", ".")));

const fromSession = (s: LiftSession, keepId: boolean): Draft => ({
  id: keepId ? s.id : undefined,
  day: keepId ? s.day : isoDaysAgo(0),
  title: s.title ?? "",
  items: s.items.map((it) => ({
    exercise: it.exercise, group: it.muscle_group,
    sets: it.sets.map((x) => ({ weight: x.weight_kg?.toString() ?? "", reps: String(x.reps), rir: x.rir?.toString() ?? "" })),
  })),
});

// "4×6 · 80 кг" when all sets match, otherwise "80×6, 80×6, 75×8"
const setsSummary = (sets: LiftSession["items"][number]["sets"]) => {
  const same = sets.every((x) => x.weight_kg === sets[0].weight_kg && x.reps === sets[0].reps);
  if (same) return `${sets.length}×${sets[0].reps}${sets[0].weight_kg ? ` · ${kg(sets[0].weight_kg)} кг` : ""}`;
  return sets.map((x) => (x.weight_kg ? `${kg(x.weight_kg)}×${x.reps}` : `${x.reps}`)).join(", ");
};

export default function Training({ c }: { c: Palette }) {
  const [sessions, setSessions] = useState<LiftSession[] | null>(null);
  const [exercises, setExercises] = useState<Exercise[]>([]);
  const [groups, setGroups] = useState<string[]>([]);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [progressId, setProgressId] = useState<number | null>(null);

  const load = () => {
    api.liftSessions(isoDaysAgo(90)).then(setSessions);
    api.exercises().then((r) => { setExercises(r.exercises); setGroups(r.groups); });
  };
  useEffect(load, []);

  const used = exercises.filter((e) => e.sessions > 0);
  // Default the progress chart to the first exercise of the latest session — usually the main lift.
  useEffect(() => {
    if (progressId == null && sessions?.length) setProgressId(sessions[0].items[0]?.exercise_id ?? null);
  }, [sessions]); // eslint-disable-line react-hooks/exhaustive-deps

  const known = useMemo(() => new Map(exercises.map((e) => [e.name.toLowerCase(), e])), [exercises]);

  const stats = useMemo(() => {
    const since = isoDaysAgo(30);
    const last30 = (sessions ?? []).filter((s) => s.day >= since);
    return { count: last30.length, volume: last30.reduce((a, s) => a + s.volume_kg, 0), sets: last30.reduce((a, s) => a + s.sets, 0) };
  }, [sessions]);

  const setItem = (i: number, patch: Partial<DraftItem>) =>
    setDraft((d) => ({ ...d, items: d.items.map((it, k) => (k === i ? { ...it, ...patch } : it)) }));
  const setSet = (i: number, j: number, patch: Partial<DraftSet>) =>
    setItem(i, { sets: draft.items[i].sets.map((x, k) => (k === j ? { ...x, ...patch } : x)) });

  const save = async () => {
    setErr(null);
    const items: LiftSessionIn["items"] = [];
    for (const it of draft.items) {
      if (!it.exercise.trim()) continue;
      const sets = it.sets.filter((x) => x.reps.trim()).map((x) => ({ weight_kg: num(x.weight), reps: Number(x.reps), rir: num(x.rir) }));
      if (sets.some((x) => !Number.isInteger(x.reps) || x.reps < 1 || (x.weight_kg != null && Number.isNaN(x.weight_kg)))) {
        setErr(`Проверь подходы в «${it.exercise}»: повторы — целое число, вес — число.`);
        return;
      }
      if (sets.length) items.push({ exercise: it.exercise.trim(), muscle_group: it.group || null, sets });
    }
    if (!items.length) { setErr("Добавь хотя бы одно упражнение с подходом."); return; }
    setSaving(true);
    try {
      await api.saveLift({ day: draft.day, title: draft.title.trim() || null, items }, draft.id);
      setDraft(emptyDraft());
      load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async (s: LiftSession) => {
    if (!confirm(`Удалить тренировку «${s.title || dayLabel(s.day)}»?`)) return;
    await api.delLift(s.id);
    if (draft.id === s.id) setDraft(emptyDraft());
    load();
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Тренировки</h1>
          <div className="sub">Силовые: подходы, веса и прогресс. WHOOP видит только пульс, а здесь видно, что именно ты поднял.</div>
        </div>
      </div>

      <div className="grid g3" style={{ marginBottom: 16 }}>
        <div className="card"><div className="tile-label">Тренировок за 30 дней</div><div className="tile-value">{fmt(stats.count)}</div></div>
        <div className="card"><div className="tile-label">Подходов</div><div className="tile-value">{fmt(stats.sets)}</div></div>
        <div className="card"><div className="tile-label">Объём</div>
          <div className="tile-value">{fmt(stats.volume / 1000, 1)}<span className="tile-unit"> т</span></div></div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head">
          <h2>{draft.id ? "Редактирование" : "Новая тренировка"}</h2>
          <div className="row">
            <input className="input" style={{ width: 180 }} placeholder="Название (Ноги, Верх…)" value={draft.title}
                   onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
            <input type="date" className="input" style={{ width: 160 }} value={draft.day} max={isoDaysAgo(0)}
                   onChange={(e) => setDraft({ ...draft, day: e.target.value })} />
          </div>
        </div>
        <datalist id="exercise-list">{exercises.map((e) => <option key={e.id} value={e.name} />)}</datalist>
        <div className="stack">
          {draft.items.map((it, i) => {
            const isNew = it.exercise.trim() !== "" && !known.has(it.exercise.trim().toLowerCase());
            return (
              <div key={i} className="lift-item">
                <div className="row" style={{ flexWrap: "wrap" }}>
                  <input className="input" list="exercise-list" style={{ flex: "1 1 220px" }} placeholder="Упражнение"
                         value={it.exercise} onChange={(e) => setItem(i, { exercise: e.target.value })} />
                  {isNew && (
                    <select className="input" style={{ width: 130 }} value={it.group} onChange={(e) => setItem(i, { group: e.target.value })}
                            aria-label="Группа мышц">
                      <option value="">группа…</option>
                      {groups.map((g) => <option key={g} value={g}>{g}</option>)}
                    </select>
                  )}
                  {!isNew && it.exercise && <span className="muted" style={{ fontSize: 12 }}>{known.get(it.exercise.trim().toLowerCase())?.muscle_group}</span>}
                  <button className="x-btn" title="Убрать упражнение" disabled={draft.items.length === 1}
                          onClick={() => setDraft({ ...draft, items: draft.items.filter((_, k) => k !== i) })}>×</button>
                </div>
                <div className="lift-sets">
                  <span className="muted">#</span><span className="muted">кг</span><span className="muted">повторы</span>
                  <span className="muted" title="Повторов в запасе: сколько ещё мог бы сделать">в запасе</span><span />
                  {it.sets.map((x, j) => (
                    <SetRow key={j} n={j + 1} x={x} onChange={(p) => setSet(i, j, p)}
                            onRemove={it.sets.length > 1 ? () => setItem(i, { sets: it.sets.filter((_, k) => k !== j) }) : undefined} />
                  ))}
                </div>
                <button className="btn ghost sm" onClick={() => setItem(i, { sets: [...it.sets, { ...(it.sets[it.sets.length - 1] ?? emptySet()) }] })}>
                  + подход
                </button>
              </div>
            );
          })}
          <div className="row" style={{ flexWrap: "wrap" }}>
            <button className="btn" onClick={() => setDraft({ ...draft, items: [...draft.items, emptyItem()] })}>+ упражнение</button>
            <span style={{ flex: 1 }} />
            {draft.id && <button className="btn ghost" onClick={() => setDraft(emptyDraft())}>Отмена</button>}
            <button className="btn primary" disabled={saving} onClick={save}>{draft.id ? "Сохранить изменения" : "Сохранить тренировку"}</button>
          </div>
          {err && <div className="sub" style={{ color: c.critical }}>{err}</div>}
        </div>
      </div>

      <div className="grid g2">
        <ProgressCard c={c} used={used} progressId={progressId} setProgressId={setProgressId} version={sessions} />
        <div className="card">
          <div className="card-head"><h2>История</h2><span className="sub">90 дней</span></div>
          {sessions == null && <div className="muted">Загружаю…</div>}
          {sessions?.length === 0 && <div className="sub">Пока пусто. Запиши первую тренировку выше, а потом жми «Повторить», чтобы не вбивать заново.</div>}
          <div className="lift-history">
            {sessions?.map((s) => (
              <div key={s.id} className="lift-session">
                <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
                  <div><b>{s.title || "Тренировка"}</b> <span className="muted" style={{ fontSize: 12 }}>{dayLabelLong(s.day)}</span></div>
                  <span className="sub" style={{ fontSize: 12, whiteSpace: "nowrap" }}>{fmt(s.volume_kg / 1000, 1)} т · {s.sets} подх.</span>
                </div>
                {s.items.map((it) => (
                  <div key={it.exercise_id} className="lift-line">
                    <span>{it.exercise}</span>
                    <span className="muted">{setsSummary(it.sets)}</span>
                  </div>
                ))}
                <div className="row" style={{ gap: 6, marginTop: 6 }}>
                  <button className="btn ghost sm" onClick={() => { setDraft(fromSession(s, false)); window.scrollTo({ top: 0, behavior: "smooth" }); }}>Повторить</button>
                  <button className="btn ghost sm" onClick={() => { setDraft(fromSession(s, true)); window.scrollTo({ top: 0, behavior: "smooth" }); }}>Изменить</button>
                  <button className="btn ghost sm" onClick={() => remove(s)}>Удалить</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

function SetRow({ n, x, onChange, onRemove }: {
  n: number; x: DraftSet; onChange: (p: Partial<DraftSet>) => void; onRemove?: () => void;
}) {
  return (
    <>
      <span className="muted">{n}</span>
      <input className="input" inputMode="decimal" placeholder="—" value={x.weight} onChange={(e) => onChange({ weight: e.target.value })} aria-label={`Вес, подход ${n}`} />
      <input className="input" inputMode="numeric" placeholder="0" value={x.reps} onChange={(e) => onChange({ reps: e.target.value })} aria-label={`Повторы, подход ${n}`} />
      <input className="input" inputMode="numeric" placeholder="—" value={x.rir} onChange={(e) => onChange({ rir: e.target.value })} aria-label={`В запасе, подход ${n}`} />
      {onRemove ? <button className="x-btn" title="Убрать подход" onClick={onRemove}>×</button> : <span />}
    </>
  );
}

function ProgressCard({ c, used, progressId, setProgressId, version }: {
  c: Palette; used: Exercise[]; progressId: number | null; setProgressId: (id: number) => void;
  version: unknown; // changes whenever sessions are reloaded, so the chart refetches after a save
}) {
  const [p, setP] = useState<LiftProgress | null>(null);
  useEffect(() => { if (progressId != null) api.liftProgress(progressId).then(setP); }, [progressId, version]);

  const first = p?.points.find((x) => x.e1rm != null)?.e1rm;
  const last = p ? [...p.points].reverse().find((x) => x.e1rm != null)?.e1rm : null;
  const growth = first && last ? (last / first - 1) * 100 : null;

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <h2>Прогресс</h2>
          <div className="sub" style={{ fontSize: 12 }}>Расчётный максимум на 1 повтор (формула Epley, по подходам до 12 повторов)</div>
        </div>
        {used.length > 0 && (
          <select className="input" style={{ width: 200, flexShrink: 0 }} value={progressId ?? ""} onChange={(e) => setProgressId(Number(e.target.value))}
                  aria-label="Упражнение">
            {used.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
          </select>
        )}
      </div>
      {used.length === 0 && <div className="sub">Здесь появится график, когда запишешь хотя бы одну тренировку.</div>}
      {p && p.points.length > 0 && (
        <>
          <div className="row" style={{ gap: 24, marginBottom: 8 }}>
            <div><div className="tile-label">Лучший e1RM</div><div className="tile-value">{fmt(p.best_e1rm, 1)}<span className="tile-unit"> кг</span></div></div>
            {growth != null && p.points.length > 1 && (
              <div><div className="tile-label">С первой записи</div>
                <div className="tile-value" style={{ color: growth >= 0 ? c.good : c.critical }}>{growth >= 0 ? "+" : ""}{fmt(growth, 1)}<span className="tile-unit"> %</span></div></div>
            )}
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={p.points} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={c.grid} strokeDasharray="3 5" />
              <XAxis dataKey="day" tickFormatter={dayLabel} minTickGap={24} {...axisProps(c)} />
              <YAxis domain={["auto", "auto"]} {...axisProps(c)} axisLine={false} width={48} />
              <Tooltip cursor={{ stroke: c.muted }} content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const d = payload[0].payload as LiftProgress["points"][number];
                return <Tip title={dayLabel(d.day)} items={[
                  { name: "e1RM", value: `${fmt(d.e1rm, 1)} кг`, color: c.strain },
                  { name: "Рабочий вес", value: `${kg(d.top_kg)} кг`, color: c.hrv },
                  { name: "Объём", value: `${fmt(d.volume_kg)} кг · ${d.sets} подх.`, color: "transparent" },
                ]} />;
              }} />
              <Line type="monotone" dataKey="e1rm" stroke={c.strain} strokeWidth={2.2} dot={{ r: 2.5 }} connectNulls isAnimationActive={false} />
              <Line type="monotone" dataKey="top_kg" stroke={c.hrv} strokeWidth={1.6} strokeDasharray="4 4" dot={false} connectNulls isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
          <Legend items={[{ label: "e1RM", color: c.strain, kind: "line" }, { label: "рабочий вес", color: c.hrv, kind: "line" }]} />
        </>
      )}
    </div>
  );
}
