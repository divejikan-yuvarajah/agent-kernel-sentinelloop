const STORAGE_KEY = "sentinelloop.demoMode";
const EVENT = "sentinelloop-demo-mode";

export function isDemoMode(): boolean {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === null) return true;
    return raw === "on";
  } catch {
    return true;
  }
}

export function setDemoMode(enabled: boolean): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, enabled ? "on" : "off");
  } catch {
    /* ignore quota / private-mode failures */
  }
  window.dispatchEvent(new Event(EVENT));
}

export function subscribeDemoMode(listener: () => void): () => void {
  window.addEventListener(EVENT, listener);
  window.addEventListener("storage", listener);
  return () => {
    window.removeEventListener(EVENT, listener);
    window.removeEventListener("storage", listener);
  };
}
