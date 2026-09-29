import { useEffect, useState } from "react";
import { api, type Me } from "./api";
import Coach from "./pages/Coach";
import Insights from "./pages/Insights";
import Journal from "./pages/Journal";
import Settings from "./pages/Settings";
import Today from "./pages/Today";
import Trends from "./pages/Trends";
import { useTheme } from "./theme";

const PAGES = [
  { id: "today", label: "Сегодня", icon: "◉" },
  { id: "trends", label: "Тренды", icon: "📈" },
  { id: "journal", label: "Журнал", icon: "✎" },
  { id: "insights", label: "Инсайты", icon: "💡" },
  { id: "coach", label: "Коуч", icon: "💬" },
  { id: "settings", label: "Настройки", icon: "⚙︎" },
] as const;
type PageId = (typeof PAGES)[number]["id"];

const fromHash = (): PageId => {
  const h = location.hash.slice(1) as PageId;
  return PAGES.some((p) => p.id === h) ? h : "today";
};

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
          <a className="btn primary" href="/auth/login" style={{ textDecoration: "none" }}>Войти через WHOOP</a>
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
            <span className="nav-ico">{p.icon}</span>{p.label}
          </button>
        ))}
        <div className="side-foot">
          {me?.is_demo && <span>🧪 Демо-данные</span>}
          {me && !me.is_demo && <span>{me.first_name} {me.last_name}</span>}
        </div>
      </nav>
      <main>
        {me?.is_demo && page === "today" && (
          <div className="banner">
            <span>🧪 Это демо на синтетических данных за 180 дней. Подключи свой WHOOP в настройках.</span>
            <button className="btn" onClick={() => go("settings")}>Настройки</button>
          </div>
        )}
        {page === "today" && <Today c={c} />}
        {page === "trends" && <Trends c={c} />}
        {page === "journal" && <Journal c={c} />}
        {page === "insights" && <Insights c={c} />}
        {page === "coach" && <Coach me={me} />}
        {page === "settings" && me && <Settings me={me} reload={loadMe} themePref={pref} setThemePref={setPref} />}
      </main>
    </div>
  );
}
