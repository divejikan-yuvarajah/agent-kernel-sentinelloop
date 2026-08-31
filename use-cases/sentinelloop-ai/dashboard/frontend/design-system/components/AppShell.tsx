import type { ReactNode } from "react";

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
  return (
    <div className="ds-shell">
      <Sidebar />
      <Header
        title={title}
        operationalStatus={operationalStatus}
        notificationCount={notificationCount}
        operatorName="A. Perera"
        operatorRole="Duty officer"
        brand={brand}
        openIncidentCount={openIncidentCount}
      />
      <main className="ds-main">{children}</main>
    </div>
  );
}
