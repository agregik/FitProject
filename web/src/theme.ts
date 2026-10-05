import { useEffect, useState } from "react";

// Chart colors are read in JS because SVG presentation attributes can't use CSS var().
// Values follow the validated reference palette (categorical slots + fixed status colors).
const LIGHT = {
  surface: "#fffdf9", ink: "#2b2520", ink2: "#6e645a", muted: "#a59a8e",
  grid: "#efe8dd", axis: "#ddd3c5",
  hrv: "#6f93b8", strain: "#d9905f", sleep: "#9283bd", aqua: "#6fae95", need: "#c9bfb2",
  good: "#86b27c", warning: "#e6b865", critical: "#d9806f",
  pos: "#6f93b8", neg: "#d9806f", neutral: "#f2ece2",
};
const DARK: typeof LIGHT = {
  surface: "#25211d", ink: "#f4eee5", ink2: "#c7bcae", muted: "#8f857a",
  grid: "#342f29", axis: "#4a4239",
  hrv: "#8aabcf", strain: "#e3a075", sleep: "#a899d1", aqua: "#84c0a7", need: "#6d645a",
  good: "#94c08a", warning: "#e9c27a", critical: "#e0907f",
  pos: "#8aabcf", neg: "#e0907f", neutral: "#3a342d",
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
