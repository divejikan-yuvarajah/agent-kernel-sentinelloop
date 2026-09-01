import { useEffect, useState } from "react";

const STORAGE_KEY = "sentinelloop.operatorPrefs";
const EVENT = "sentinelloop-operator-prefs";

export type WorkerLanguage = "en" | "si" | "ta";
export type ShiftName = "day" | "night" | "weekend";
export type DigestCadence = "off" | "hourly" | "shift";

export type OperatorPrefs = {
  displayName: string;
  defaultSite: string;
  alerts: {
    critical: boolean;
    handover: boolean;
    duplicates: boolean;
    workerConfirm: boolean;
    digest: DigestCadence;
  };
  voice: {
    spokenReplies: boolean;
    autoDetect: boolean;
    defaultLanguage: WorkerLanguage;
  };
  channels: {
    slackChannel: string;
    telegramLabel: string;
  };
  shift: {
    current: ShiftName;
    autoHandover: boolean;
    quietHours: boolean;
    quietFrom: string;
    quietTo: string;
  };
  display: {
    compactTables: boolean;
  };
};

export const DEFAULT_PREFS: OperatorPrefs = {
  displayName: "",
  defaultSite: "horizon",
  alerts: {
    critical: true,
    handover: true,
    duplicates: true,
    workerConfirm: true,
    digest: "shift",
  },
  voice: {
    spokenReplies: true,
    autoDetect: true,
    defaultLanguage: "en",
  },
  channels: {
    slackChannel: "#electrical-safety",
    telegramLabel: "Worker bot",
  },
  shift: {
    current: "day",
    autoHandover: true,
    quietHours: false,
    quietFrom: "22:00",
    quietTo: "06:00",
  },
  display: {
    compactTables: false,
  },
};

function mergePrefs(raw: Partial<OperatorPrefs> | null | undefined): OperatorPrefs {
  const next = { ...DEFAULT_PREFS, ...(raw ?? {}) };
  return {
    ...next,
    alerts: { ...DEFAULT_PREFS.alerts, ...next.alerts },
    voice: { ...DEFAULT_PREFS.voice, ...next.voice },
    channels: { ...DEFAULT_PREFS.channels, ...next.channels },
    shift: { ...DEFAULT_PREFS.shift, ...next.shift },
    display: { ...DEFAULT_PREFS.display, ...next.display },
  };
}

export function defaultOperatorPrefs(): OperatorPrefs {
  return mergePrefs({});
}

export function applyOperatorPrefs(prefs: OperatorPrefs = readOperatorPrefs()): void {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.density = prefs.display.compactTables ? "compact" : "comfortable";
}

export function readOperatorPrefs(): OperatorPrefs {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) return mergePrefs(JSON.parse(raw) as Partial<OperatorPrefs>);
  } catch {
    /* private mode or invalid JSON */
  }
  return { ...DEFAULT_PREFS, alerts: { ...DEFAULT_PREFS.alerts }, voice: { ...DEFAULT_PREFS.voice }, channels: { ...DEFAULT_PREFS.channels }, shift: { ...DEFAULT_PREFS.shift }, display: { ...DEFAULT_PREFS.display } };
}

export function setOperatorPrefs(prefs: OperatorPrefs): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    /* ignore */
  }
  applyOperatorPrefs(prefs);
  window.dispatchEvent(new Event(EVENT));
}

export function subscribeOperatorPrefs(listener: () => void): () => void {
  window.addEventListener(EVENT, listener);
  window.addEventListener("storage", listener);
  return () => {
    window.removeEventListener(EVENT, listener);
    window.removeEventListener("storage", listener);
  };
}

export function notificationAllowed(
  item: { id: string; title: string; severity: string },
  prefs: OperatorPrefs,
): boolean {
  const title = item.title.toLowerCase();
  if (item.id.includes("handover") || title.includes("handover")) return prefs.alerts.handover;
  if (title.includes("duplicate")) return prefs.alerts.duplicates;
  if (title.includes("inspection") || title.includes("confirmation")) return prefs.alerts.workerConfirm;
  if (item.severity === "CRITICAL") return prefs.alerts.critical;
  return true;
}

export function useOperatorPrefs(): [OperatorPrefs, (next: OperatorPrefs) => void] {
  const [prefs, setPrefs] = useState(readOperatorPrefs);
  useEffect(() => {
    applyOperatorPrefs(prefs);
    return subscribeOperatorPrefs(() => setPrefs(readOperatorPrefs()));
  }, []);
  return [prefs, setOperatorPrefs];
}
