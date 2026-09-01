import { colors } from "../../design-system/colors";

const STORAGE_KEY = "sentinelloop.theme";
const EVENT = "sentinelloop-theme";

export type ThemeName = "dark" | "light";

export function readTheme(): ThemeName {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === "light" || raw === "dark") return raw;
  } catch {
    /* private mode */
  }
  return "light";
}

export function applyTheme(theme: ThemeName): void {
  document.documentElement.setAttribute("data-theme", theme);
  document.documentElement.style.colorScheme = "light";
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", colors.ink);
}

export function setTheme(theme: ThemeName): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* ignore */
  }
  applyTheme(theme);
  window.dispatchEvent(new Event(EVENT));
}

export function subscribeTheme(listener: () => void): () => void {
  window.addEventListener(EVENT, listener);
  window.addEventListener("storage", listener);
  return () => {
    window.removeEventListener(EVENT, listener);
    window.removeEventListener("storage", listener);
  };
}
