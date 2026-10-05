import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { api, type Me } from "../api";
import type { ThemePref } from "../theme";

export default function Settings({
  me, reload, themePref, setThemePref,
}: { me: Me; reload: () => void; themePref: ThemePref; setThemePref: (t: ThemePref) => void }) {
  const [ics, setIcs] = useState(me.ics_urls.join("\n"));
  const [icsMsg, setIcsMsg] = useState("");
  const [wake, setWake] = useState(me.settings.wake_time);
  const [tz, setTz] = useState(me.settings.tz);
  const [syncMsg, setSyncMsg] = useState("");
  const [tgErr, setTgErr] = useState("");

  const saveCalendar = async () => {
    setIcsMsg("Загружаю…");
    try {
      const r = await api.setCalendar(ics.split("\n").map((s) => s.trim()).filter(Boolean));
      setIcsMsg(`Готово: ${r.events} событий`);
      reload();
    } catch (e) { setIcsMsg((e as Error).message); }
  };

  const sync = async () => {
    setSyncMsg("Синхронизирую…");
    try {
      const r = await api.sync();
      setSyncMsg(Object.entries(r).map(([k, v]) => `${k}: ${v}`).join(" · "));
      reload();
    } catch (e) { setSyncMsg((e as Error).message); }
  };

  const linkTelegram = async () => {
    setTgErr("");
    try { const r = await api.telegramLink(); window.open(r.url, "_blank"); }
    catch (e) { setTgErr((e as Error).message); }
  };

  return (
    <>
      <div className="page-head"><h1>Настройки</h1></div>
      <div className="grid g2">
        <div className="card stack">
          <h2>WHOOP</h2>
          {me.is_demo ? (
            <>
              <div className="sub">Сейчас показываются демо-данные.</div>
              {me.whoop_configured
                ? <a className="btn primary" href="/auth/login" style={{ textDecoration: "none", textAlign: "center" }}>Подключить WHOOP</a>
                : <div className="sub">Чтобы подключить настоящий WHOOP, заполни <code>WHOOP_CLIENT_ID</code> и <code>WHOOP_CLIENT_SECRET</code> в backend/.env (инструкция в README).</div>}
            </>
          ) : (
            <>
              <div className="sub">Подключён: {me.first_name} {me.last_name} · {me.email}</div>
              <div className="sub">Последняя синхронизация: {me.last_sync_at ? new Date(me.last_sync_at).toLocaleString("ru-RU") : "ещё не было"}</div>
              <div className="row">
                <button className="btn" onClick={sync}>Синхронизировать сейчас</button>
                <button className="btn" onClick={() => api.logout().then(() => location.reload())}>Выйти</button>
              </div>
              {syncMsg && <div className="sub">{syncMsg}</div>}
            </>
          )}
        </div>

        <div className="card stack">
          <h2>Telegram-бот</h2>
          <div className="sub">
            Утренняя сводка, как только посчитан recovery. Любое сообщение боту становится записью в журнале. /ask — вопрос коучу, итоги недели по воскресеньям.
          </div>
          {me.telegram_linked ? <div className="sub">✅ Подключён</div> : me.telegram_enabled
            ? <button className="btn primary" onClick={linkTelegram}>Подключить Telegram</button>
            : <div className="sub">Создай бота у @BotFather и впиши <code>TELEGRAM_BOT_TOKEN</code> и <code>TELEGRAM_BOT_USERNAME</code> в backend/.env.</div>}
          {tgErr && <div className="sub">{tgErr}</div>}
        </div>

        <div className="card stack">
          <h2>Календарь</h2>
          <div className="sub">
            Вставь секретные ICS-ссылки, по одной на строку. Google Календарь: Настройки → календарь → «Секретный адрес в формате iCal».
            iCloud: «Поделиться» → «Публичный календарь». В инсайты попадут количество встреч, занятость и поздние события.
          </div>
          <textarea className="textarea" rows={3} value={ics} onChange={(e) => setIcs(e.target.value)}
                    placeholder="https://calendar.google.com/calendar/ical/…/basic.ics" />
          <div className="row">
            <button className="btn" onClick={saveCalendar}>Сохранить и загрузить</button>
            {icsMsg && <span className="sub">{icsMsg}</span>}
          </div>
        </div>

        <div className="card stack">
          <h2>Режим</h2>
          <label className="sub">Во сколько обычно встаёшь (для расчёта отбоя)</label>
          <input className="input" type="time" value={wake} onChange={(e) => setWake(e.target.value)} style={{ width: 140 }} />
          <label className="sub">Часовой пояс</label>
          <input className="input" value={tz} onChange={(e) => setTz(e.target.value)} style={{ width: 240 }} />
          <div className="row">
            <button className="btn" onClick={() => api.settings({ wake_time: wake, tz }).then(reload)}>Сохранить</button>
          </div>
          <label className="sub">Тема</label>
          <div className="seg">
            {(["system", "light", "dark"] as ThemePref[]).map((t) => (
              <button key={t} className={themePref === t ? "on" : ""} onClick={() => setThemePref(t)}>
                {t === "system" ? "Как в системе" : t === "light" ? "Светлая" : "Тёмная"}
              </button>
            ))}
          </div>
        </div>

        <div className="card stack">
          <h2>Данные</h2>
          <div className="sub">Вся история хранится в твоей базе. Выгрузка по дням: метрики, тренировки, теги и заметки.</div>
          <a className="btn" href="/api/export.csv" style={{ textDecoration: "none", textAlign: "center" }}>Скачать CSV</a>
        </div>

        <PhoneCard me={me} />
      </div>
    </>
  );
}

const isLocal = ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);

function PhoneCard({ me }: { me: Me }) {
  const [link, setLink] = useState<{ url: string; qr: string; until: number } | null>(null);
  const [left, setLeft] = useState(0);
  const [err, setErr] = useState("");
  const [showToken, setShowToken] = useState(false);

  useEffect(() => {
    if (!link) return;
    const t = setInterval(() => {
      const s = Math.max(0, Math.round((link.until - Date.now()) / 1000));
      setLeft(s);
      if (!s) setLink(null);
    }, 1000);
    return () => clearInterval(t);
  }, [link]);

  const make = async () => {
    setErr("");
    try {
      const r = await api.deviceLink();
      const qr = await QRCode.toDataURL(r.url, { margin: 1, width: 440, color: { dark: "#2b2520", light: "#ffffff" } });
      setLink({ url: r.url, qr, until: Date.now() + r.expires_in * 1000 });
      setLeft(r.expires_in);
    } catch (e) {
      setErr((e as Error & { status?: number }).status === 409
        ? "Телефон пока не видит этот компьютер: запусти в терминале ./tunnel.sh и дождись строки «✅ Телефон: …», "
          + "потом нажми кнопку ещё раз. Если туннель не подключается — выключи VPN (V2Box)."
        : (e as Error).message);
    }
  };

  // Opened from the phone itself: pairing is done, just explain installing to the home screen.
  if (!isLocal) {
    return (
      <div className="card stack">
        <h2>Приложение на телефоне</h2>
        <div className="sub">
          Safari → кнопка «Поделиться» → «На экран „Домой“». Появится иконка FitProject, приложение откроется
          на весь экран, без адресной строки.
        </div>
      </div>
    );
  }

  return (
    <div className="card stack">
      <h2>Подключить телефон</h2>
      {link ? (
        <>
          <img src={link.qr} alt="QR-код для входа с телефона" className="qr" />
          <div className="sub">
            Наведи камеру iPhone на код и открой ссылку. Затем в Safari: «Поделиться» → «На экран „Домой“».
            Код одноразовый, действует ещё {Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}.
          </div>
          <button className="btn" onClick={() => setLink(null)}>Скрыть</button>
        </>
      ) : (
        <>
          <div className="sub">
            Покажет QR-код: наведёшь камеру айфона, и ты уже вошёл, без логина WHOOP.
            {me.public_url && <> Адрес: <span className="muted">{me.public_url.replace("https://", "")}</span></>}
          </div>
          <button className="btn primary" onClick={make}>Показать QR-код</button>
        </>
      )}
      {err && <div className="sub">{err}</div>}
      <details>
        <summary className="sub" style={{ cursor: "pointer" }}>Токен для виджетов и своих скриптов</summary>
        <div className="stack" style={{ marginTop: 8 }}>
          <div className="sub">Даёт полный доступ к твоим данным. Никому его не показывай.</div>
          {showToken ? <div className="code">{me.api_token}</div>
            : <button className="btn" onClick={() => setShowToken(true)}>Показать токен</button>}
        </div>
      </details>
    </div>
  );
}
