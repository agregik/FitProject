export type Workout = {
  id: string; sport: string; strain: number | null; start: string; end: string;
  avg_hr: number | null; max_hr: number | null; kj: number | null; distance_m: number | null;
};
export type Note = { id: number; day?: string; text: string; tags: string[]; source: string; created_at?: string };
export type Day = {
  date: string;
  recovery?: number; hrv?: number; rhr?: number; spo2?: number; skin_temp?: number; resp_rate?: number;
  sleep_hours?: number; sleep_need_hours?: number; sleep_performance?: number; sleep_efficiency?: number;
  sleep_consistency?: number; deep_hours?: number; rem_hours?: number; light_hours?: number; awake_hours?: number;
  disturbances?: number; strain?: number; kj?: number;
  meetings?: number; busy_hours?: number; late_events?: number;
  workouts: Workout[]; notes: Note[]; tags: string[];
  events?: { title: string; start: string; end: string; all_day: boolean }[];
};
export type Baseline = Record<string, { mean: number; sd: number; n: number }>;
export type Alert = { level: "warn" | "info" | "good"; text: string };
export type Today = {
  date: string; day: Day | null; is_today: boolean; baseline: Baseline;
  strain_target: { min: number | null; max: number | null; label: string };
  bedtime: { bedtime: string; wake_time: string; need_hours: number; in_bed_hours: number } | null;
  alerts: Alert[];
  last7: { date: string; recovery?: number; hrv?: number; sleep_hours?: number; strain?: number }[];
};
export type TagEffect = {
  tag: string; n: number; recovery_with: number; recovery_without: number; recovery_diff: number;
  hrv_diff_pct: number | null; p_value: number; confidence: "высокая" | "средняя" | "низкая";
};
export type Driver = {
  key: string; label: string; r: number; n: number; slope: number; unit: string; explain: string;
  confidence: string; points: { x: number; y: number }[];
};
export type Insights = {
  period_days: number; days_with_data: number; tags: TagEffect[]; drivers: Driver[];
  weekday: { weekday: string; recovery: number | null; n: number }[];
};
export type Me = {
  id: number; first_name: string | null; last_name: string | null; email: string | null; is_demo: boolean;
  last_sync_at: string | null; telegram_linked: boolean; telegram_enabled: boolean; whoop_configured: boolean;
  coach_ai: boolean; ics_urls: string[]; settings: { tz: string; wake_time: string }; api_token: string;
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, {
    credentials: "include",
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    ...init,
  });
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail ?? msg; } catch { /* not json */ }
    const err = new Error(msg) as Error & { status: number };
    err.status = r.status;
    throw err;
  }
  return r.json();
}

export const api = {
  me: () => req<Me>("/api/me"),
  today: () => req<Today>("/api/today"),
  days: (start: string, end?: string) =>
    req<Day[]>(`/api/days?start=${start}${end ? `&end=${end}` : ""}`),
  insights: (days = 180) => req<Insights>(`/api/insights?days=${days}`),
  notes: (start?: string) => req<Note[]>(`/api/notes${start ? `?start=${start}` : ""}`),
  addNote: (text: string, day?: string) =>
    req<{ id: number }>("/api/notes", { method: "POST", body: JSON.stringify({ text, day }) }),
  delNote: (id: number) => req(`/api/notes/${id}`, { method: "DELETE" }),
  tags: () => req<{ tag: string; count: number }[]>("/api/tags"),
  coachHistory: () => req<{ role: "user" | "assistant"; content: string }[]>("/api/coach/history"),
  ask: (question: string) =>
    req<{ answer: string; ai: boolean }>("/api/coach", { method: "POST", body: JSON.stringify({ question }) }),
  clearCoach: () => req("/api/coach/history", { method: "DELETE" }),
  sync: () => req<Record<string, number>>("/api/sync", { method: "POST" }),
  setCalendar: (urls: string[]) =>
    req<{ events: number }>("/api/calendar", { method: "POST", body: JSON.stringify({ urls }) }),
  telegramLink: () => req<{ url: string }>("/api/telegram/link", { method: "POST" }),
  settings: (s: { tz?: string; wake_time?: string }) =>
    req("/api/settings", { method: "PATCH", body: JSON.stringify(s) }),
  logout: () => req("/auth/logout", { method: "POST" }),
};

export const isoDaysAgo = (n: number) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toLocaleDateString("sv-SE"); // YYYY-MM-DD in local time
};
