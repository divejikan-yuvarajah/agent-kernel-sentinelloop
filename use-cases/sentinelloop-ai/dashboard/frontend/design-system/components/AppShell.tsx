import { useEffect, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";

import { useDemoMode } from "@/demo/useDemoMode";
import { notifications, organization } from "@/data/demoData";

import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

const COLLAPSED_KEY = "sentinelloop.sidebarCollapsed";

type Props = {
  title: string;
  operationalStatus: string;
  notificationCount?: number;
  children: ReactNode;
  brand?: string;
  subtitle?: string;
  openIncidentCount?: number;
};

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

export function AppShell({
  title,
  operationalStatus,
  notificationCount,
  children,
  brand,
  subtitle,
  openIncidentCount,
}: Props) {
  const [demo] = useDemoMode();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [navOpen, setNavOpen] = useState(false);
  const alerts = notificationCount ?? (demo ? notifications.length : 0);

  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!navOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setNavOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navOpen]);

  const toggleCollapsed = () => {
    setCollapsed((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(COLLAPSED_KEY, next ? "1" : "0");
      } catch {
        /* private mode */
      }
      return next;
    });
  };

  const shellClass = [
    "ds-shell",
    collapsed ? "ds-shell--collapsed" : "",
    navOpen ? "ds-shell--nav-open" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={shellClass}>
      {navOpen ? (
        <button type="button" className="ds-shell__backdrop" aria-label="Close navigation" onClick={() => setNavOpen(false)} />
      ) : null}
      <Sidebar collapsed={collapsed} onToggleCollapsed={toggleCollapsed} onNavigate={() => setNavOpen(false)} />
      <Header
        title={title}
        operationalStatus={operationalStatus}
        notificationCount={alerts}
        operatorName={demo ? organization.operator.name : "A. Perera"}
        operatorRole={demo ? organization.operator.role : "Duty officer"}
        brand={brand}
        subtitle={subtitle}
        openIncidentCount={openIncidentCount}
        demo={demo}
        notifyHref="/notifications"
        navOpen={navOpen}
        onMenuClick={() => setNavOpen((open) => !open)}
      />
      <main className="ds-main">{children}</main>
    </div>
  );
}
