/** Mobile drawer links — sidebar remains the full ops nav. */
export const SHELL_PRIMARY_NAV = [] as const;

export const SHELL_MOBILE_EXTRA = [
  { to: "/dashboard", label: "Dashboard", end: true },
  { to: "/sandbox", label: "Try It Live", end: false },
  { to: "/report", label: "Log a hazard", end: false },
  { to: "/incidents", label: "Incidents", end: false },
  { to: "/analytics", label: "Analytics", end: false },
  { to: "/settings", label: "Settings", end: false },
] as const;

export type Crumb = { label: string; to?: string };

export function buildBreadcrumbs(pathname: string, pageTitle?: string): Crumb[] {
  const crumbs: Crumb[] = [{ label: "Dashboard", to: "/dashboard" }];

  if (pathname === "/dashboard" || pathname === "/") {
    return crumbs;
  }

  if (pathname.startsWith("/incidents/")) {
    const id = decodeURIComponent(pathname.split("/")[2] || pageTitle || "Incident");
    crumbs.push({ label: "Incidents", to: "/incidents" });
    crumbs.push({ label: id });
    return crumbs;
  }

  if (pathname.startsWith("/incidents")) {
    crumbs.push({ label: "Incidents" });
    return crumbs;
  }

  if (pathname.startsWith("/analytics") || pathname.startsWith("/forecast")) {
    crumbs.push({ label: "Analytics" });
    return crumbs;
  }

  if (pathname.startsWith("/report")) {
    crumbs.push({ label: "Log a hazard" });
    return crumbs;
  }

  if (pathname.startsWith("/sandbox") || pathname.startsWith("/try")) {
    crumbs.push({ label: "Try It Live" });
    return crumbs;
  }

  if (pageTitle) {
    crumbs.push({ label: pageTitle });
  }
  return crumbs;
}
