import { useEffect, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";

import { Sidebar } from "@ds/components/Sidebar";

import { CommandCenterControls } from "../CommandCenterControls";
import { useDemoMode } from "../../demo/useDemoMode";
import { notifications, organization } from "../../data/demoData";
import { Breadcrumbs } from "./Breadcrumbs";
import { MobileNav } from "./MobileNav";
import { PageContainer } from "./PageContainer";
import { TopNav } from "./TopNav";
import { buildBreadcrumbs } from "./shellNav";

const COLLAPSED_KEY = "sentinelloop.sidebarCollapsed";

type Props = {
  title: string;
  operationalStatus: string;
  notificationCount?: number;
  children: ReactNode;
  brand?: string;
  subtitle?: string;
  openIncidentCount?: number;
  description?: string;
  actions?: ReactNode;
  showCommandControls?: boolean;
};

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

export function Shell({
  title,
  operationalStatus: _operationalStatus,
  notificationCount,
  children,
  brand,
  subtitle: _subtitle,
  openIncidentCount: _openIncidentCount,
  description: _description,
  actions: _actions,
  showCommandControls = true,
}: Props) {
  const [demo] = useDemoMode();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [navOpen, setNavOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const alerts = notificationCount ?? (demo ? notifications.length : 0);
  const crumbs = buildBreadcrumbs(location.pathname, brand || title);

  useEffect(() => {
    document.title = "SentinelLoop AI Dashboard";
  }, [location.pathname]);

  useEffect(() => {
    setNavOpen(false);
    setMobileOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!navOpen && !mobileOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setNavOpen(false);
        setMobileOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mobileOpen, navOpen]);

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
    "sl-shell",
    collapsed ? "ds-shell--collapsed" : "",
    navOpen ? "ds-shell--nav-open" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={shellClass}>
      {navOpen ? (
        <button
          type="button"
          className="ds-shell__backdrop"
          aria-label="Close navigation"
          onClick={() => setNavOpen(false)}
        />
      ) : null}
      <Sidebar collapsed={collapsed} onToggleCollapsed={toggleCollapsed} onNavigate={() => setNavOpen(false)} />
      <TopNav
        title={title}
        operatorName={demo ? organization.operator.name : "A. Perera"}
        operatorRole={demo ? organization.operator.role : "Safety Officer"}
        notificationCount={alerts}
        demo={demo}
        navOpen={navOpen || mobileOpen}
        onMenuClick={() => {
          if (window.matchMedia("(max-width: 860px)").matches) {
            setMobileOpen((open) => !open);
            setNavOpen(false);
          } else {
            setNavOpen((open) => !open);
            setMobileOpen(false);
          }
        }}
      />
      <MobileNav open={mobileOpen} onClose={() => setMobileOpen(false)} />
      <main className="ds-main sl-shell__main">
        <PageContainer>
          <div className="sl-shell__chrome">
            <Breadcrumbs items={crumbs} />
            {showCommandControls ? <CommandCenterControls /> : null}
          </div>
          <header className="sl-page-header">
            <h1 className="sl-page-header__title">{title}</h1>
          </header>
          <div className="sl-shell__content">{children}</div>
        </PageContainer>
      </main>
    </div>
  );
}

export default Shell;
