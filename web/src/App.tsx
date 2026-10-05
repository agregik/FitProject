import { useEffect, useState } from "react";
import { api, type Me } from "./api";
import Coach from "./pages/Coach";
import Insights from "./pages/Insights";
import Journal from "./pages/Journal";
import Settings from "./pages/Settings";
import Today from "./pages/Today";
import Training from "./pages/Training";
import Trends from "./pages/Trends";
import { useTheme } from "./theme";

const I = (d: string) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d={d} />
  </svg>
);
const ICONS: Record<string, JSX.Element> = {
  today: I("M12 3a9 9 0 1 0 9 9M12 7a5 5 0 1 0 5 5M12 11a1 1 0 1 0 1 1"),
  trends: I("M3 17l5-5 4 4 8-9M15 7h5v5"),
  training: I("M6 8v8M18 8v8M3 10v4M21 10v4M6 12h12"),
  journal: I("M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3V4zM9 9h6M9 13h4"),
  insights: I("M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z"),
  coach: I("M20 12a8 8 0 0 1-11.6 7.1L4 20l1-4.2A8 8 0 1 1 20 12z"),
  settings: I("M4 7h10M18 7h2M4 17h4M12 17h8M16 5v4M10 15v4"),
};

const PAGES = [
  { id: "today", label: "Сегодня" },
  { id: "trends", label: "Тренды" },
  { id: "journal", label: "Журнал" },
  { id: "training", label: "Силовые" },
  { id: "insights", label: "Инсайты" },
  { id: "coach", label: "Коуч" },
  { id: "settings", label: "Настройки" },
] as const;
type PageId = (typeof PAGES)[number]["id"];

const fromHash = (): PageId => {
  const h = location.hash.slice(1) as PageId;
  return PAGES.some((p) => p.id === h) ? h : "today";
};

// WHOOP's OAuth redirect points at localhost, so WHOOP login only works on the laptop itself.
const onLaptop = ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
const loginError = new URLSearchParams(location.search).get("error");

export default function App() {
  const { c, pref, setPref } = useTheme();
  const [page, setPage] = useState<PageId>(fromHash);
  const [me, setMe] = useState<Me | null>(null);
  const [authErr, setAuthErr] = useState(false);

  const loadMe = () => api.me().then(setMe).catch(() => setAuthErr(true));
  useEffect(() => { loadMe(); }, []);
  useEffect(() => {
    const on = () => setPage(fromHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const go = (p: PageId) => { location.hash = p; setPage(p); window.scrollTo(0, 0); };

  if (authErr) {
    return (
      <div style={{ display: "grid", placeItems: "center", minHeight: "100vh", padding: 16 }}>
        <div className="card stack" style={{ maxWidth: 420, textAlign: "center" }}>
          <div className="brand" style={{ justifyContent: "center", margin: 0 }}><span className="brand-dot" />FitProject</div>
          <div className="sub">Твой WHOOP, только понятнее: тренды, журнал, инсайты и AI-коуч.</div>
          {loginError === "device_link_expired" && (
            <div className="sub" style={{ color: c.critical }}>QR-код уже использован или истёк. Покажи новый.</div>
          )}
          {onLaptop ? (
            <a className="btn primary" href="/auth/login" style={{ textDecoration: "none" }}>Войти через WHOOP</a>
          ) : (
            <div className="sub">
              Чтобы войти с телефона, открой FitProject на компьютере → Настройки → «Подключить телефон» и наведи
              камеру на QR-код.
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <nav className="side">
        <div className="brand"><span className="brand-dot" />FitProject</div>
        {PAGES.map((p) => (
          <button key={p.id} className={`nav-btn ${page === p.id ? "active" : ""}`} onClick={() => go(p.id)}>
            <span className="nav-ico">{ICONS[p.id]}</span>{p.label}
          </button>
        ))}
        <div className="side-foot">
          {me?.is_demo && <span>Демо-данные</span>}
          {me && !me.is_demo && <span>{me.first_name} {me.last_name}</span>}
        </div>
      </nav>
      <main key={page}>
        {me?.is_demo && page === "today" && (
          <div className="banner">
            <span>Это демо на синтетических данных за 180 дней. Подключи свой WHOOP в настройках.</span>
            <button className="btn" onClick={() => go("settings")}>Настройки</button>
          </div>
        )}
        {page === "today" && <Today c={c} />}
        {page === "trends" && <Trends c={c} />}
        {page === "journal" && <Journal c={c} />}
        {page === "training" && <Training c={c} />}
        {page === "insights" && <Insights c={c} />}
        {page === "coach" && <Coach me={me} />}
        {page === "settings" && me && <Settings me={me} reload={loadMe} themePref={pref} setThemePref={setPref} />}
      </main>
    </div>
  );
}
