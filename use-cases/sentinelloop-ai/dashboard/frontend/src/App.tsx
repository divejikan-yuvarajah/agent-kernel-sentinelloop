import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { DashboardPage } from "./pages/DashboardPage";
import { EvidencePage } from "./pages/EvidencePage";
import { IncidentDetailPage } from "./pages/IncidentDetailPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { OfficersPage } from "./pages/OfficersPage";
import { SettingsPage } from "./pages/SettingsPage";

const AnalyticsPage = lazy(() => import("./pages/AnalyticsPage").then((module) => ({ default: module.AnalyticsPage })));
const DesignSystemPage = lazy(() =>
  import("./pages/DesignSystemPage").then((module) => ({ default: module.DesignSystemPage })),
);

export function App() {
  return (
    <Suspense fallback={<p className="ds-empty">Loading…</p>}>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/incidents" element={<IncidentsPage />} />
        <Route path="/incidents/:incidentId" element={<IncidentDetailPage />} />
        <Route path="/evidence" element={<EvidencePage />} />
        <Route path="/officers" element={<OfficersPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/design-system" element={<DesignSystemPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
