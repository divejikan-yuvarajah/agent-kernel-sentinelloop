import type { ReactNode } from "react";

import { useDemoMode } from "@/demo/useDemoMode";
import { notifications, organization } from "@/data/demoData";

import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

type Props = {
  title: string;
  operationalStatus: string;
  notificationCount?: number;
  children: ReactNode;
  brand?: string;
  openIncidentCount?: number;
};

export function AppShell({
  title,
  operationalStatus,
  notificationCount,
  children,
  brand,
  openIncidentCount,
}: Props) {
  const [demo] = useDemoMode();
  const alerts = notificationCount ?? (demo ? notifications.length : 0);
  return (
    <div className="ds-shell">
      <Sidebar />
      <Header
        title={title}
        operationalStatus={operationalStatus}
        notificationCount={alerts}
        operatorName={demo ? organization.operator.name : "A. Perera"}
        operatorRole={demo ? organization.operator.role : "Duty officer"}
        brand={brand}
        openIncidentCount={openIncidentCount}
        demo={demo}
        notifyHref="/notifications"
      />
      <main className="ds-main">{children}</main>
    </div>
  );
}
