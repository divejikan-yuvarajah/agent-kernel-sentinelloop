import type { ReactNode } from "react";

import { Shell } from "@/components/Shell";

type Props = {
  title: string;
  operationalStatus: string;
  notificationCount?: number;
  children: ReactNode;
  brand?: string;
  subtitle?: string;
  openIncidentCount?: number;
};

/** Authenticated command-center layout. Delegates to the unified Shell. */
export function AppShell({
  title,
  operationalStatus,
  notificationCount,
  children,
  brand,
  subtitle,
  openIncidentCount,
}: Props) {
  return (
    <Shell
      title={title}
      operationalStatus={operationalStatus}
      notificationCount={notificationCount}
      brand={brand}
      subtitle={subtitle}
      openIncidentCount={openIncidentCount}
    >
      {children}
    </Shell>
  );
}
