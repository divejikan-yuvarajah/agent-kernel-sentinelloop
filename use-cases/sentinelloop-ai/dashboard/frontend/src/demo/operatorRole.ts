const STORAGE_KEY = "sentinelloop.operatorRole";
const EVENT = "sentinelloop-operator-role";

export type OperatorRole = "officer" | "supervisor" | "admin";

export const OPERATOR_ROLE_LABEL: Record<OperatorRole, string> = {
  officer: "Safety Officer",
  supervisor: "Supervisor",
  admin: "Admin",
};

export function readOperatorRole(): OperatorRole {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === "supervisor" || raw === "admin" || raw === "officer") return raw;
  } catch {
    /* private mode */
  }
  return "officer";
}

export function canLogHazard(role: OperatorRole = readOperatorRole()) {
  return role === "officer" || role === "admin";
}

export function setOperatorRole(role: OperatorRole) {
  try {
    window.localStorage.setItem(STORAGE_KEY, role);
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new Event(EVENT));
}

export function subscribeOperatorRole(listener: () => void) {
  window.addEventListener(EVENT, listener);
  window.addEventListener("storage", listener);
  return () => {
    window.removeEventListener(EVENT, listener);
    window.removeEventListener("storage", listener);
  };
}
