export const SHELL_PRIMARY_NAV = [
  { to: "/dashboard", label: "Dashboard", end: true },
  { to: "/incidents", label: "Incidents", end: false },
  { to: "/analytics", label: "Predictions", end: false },
  { to: "/ai-usage", label: "Router Status", end: false },
] as const;

export const SHELL_MOBILE_EXTRA = [{ to: "/settings", label: "Settings" }] as const;

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
    crumbs.push({ label: "Predictions" });
    return crumbs;
  }

  if (pathname.startsWith("/ai-usage")) {
    crumbs.push({ label: "Router Status" });
    return crumbs;
  }

  if (pageTitle) {
    crumbs.push({ label: pageTitle });
  }
  return crumbs;
}
