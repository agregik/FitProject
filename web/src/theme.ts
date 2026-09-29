import { useEffect, useState } from "react";

// Chart colors are read in JS because SVG presentation attributes can't use CSS var().
// Values follow the validated reference palette (categorical slots + fixed status colors).
const LIGHT = {
  surface: "#fcfcfb", ink: "#0b0b0b", ink2: "#52514e", muted: "#898781",
  grid: "#e1e0d9", axis: "#c3c2b7",
  hrv: "#2a78d6", strain: "#eb6834", sleep: "#4a3aa7", aqua: "#1baf7a", need: "#898781",
  good: "#0ca30c", warning: "#fab219", critical: "#d03b3b",
  pos: "#2a78d6", neg: "#e34948", neutral: "#f0efec",
};
const DARK: typeof LIGHT = {
  surface: "#1a1a19", ink: "#ffffff", ink2: "#c3c2b7", muted: "#898781",
  grid: "#2c2c2a", axis: "#383835",
  hrv: "#3987e5", strain: "#d95926", sleep: "#9085e9", aqua: "#199e70", need: "#898781",
  good: "#0ca30c", warning: "#fab219", critical: "#d03b3b",
  pos: "#3987e5", neg: "#e66767", neutral: "#383835",
};
export type Palette = typeof LIGHT;

export type ThemePref = "system" | "light" | "dark";

function resolve(pref: ThemePref): "light" | "dark" {
  if (pref !== "system") return pref;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function useTheme() {
  const [pref, setPref] = useState<ThemePref>(() => {
    try { return (localStorage.getItem("fp-theme") as ThemePref) || "system"; } catch { return "system"; }
  });
  const [mode, setMode] = useState<"light" | "dark">(() => resolve(pref));

  useEffect(() => {
    const apply = () => setMode(resolve(pref));
    apply();
    if (pref === "system") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", pref);
    try { localStorage.setItem("fp-theme", pref); } catch { /* storage unavailable */ }
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [pref]);

  return { pref, setPref, mode, c: mode === "dark" ? DARK : LIGHT };
}

export function recoveryStatus(r: number | null | undefined, c: Palette) {
  if (r == null) return { color: c.muted, label: "нет данных" };
  if (r >= 67) return { color: c.good, label: "зелёная зона" };
  if (r >= 34) return { color: c.warning, label: "жёлтая зона" };
  return { color: c.critical, label: "красная зона" };
}
