import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { CoordinationPage } from "./pages/CoordinationPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DuplicatesPage } from "./pages/DuplicatesPage";
import { EmergencyHistoryPage } from "./pages/EmergencyHistoryPage";
import { EmergencyPage } from "./pages/EmergencyPage";
import { HandoverHistoryPage } from "./pages/HandoverHistoryPage";
import { EvidencePage } from "./pages/EvidencePage";
import { FollowUpPage } from "./pages/FollowUpPage";
import { ForecastPage } from "./pages/ForecastPage";
import { GuardrailDebugPage } from "./pages/GuardrailDebugPage";
import { IncidentDetailPage } from "./pages/IncidentDetailPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { KnowledgePage } from "./pages/KnowledgePage";
import { NotificationsPage } from "./pages/NotificationsPage";
import { OfficersPage } from "./pages/OfficersPage";
import { PeoplePage } from "./pages/PeoplePage";
import { ReportsPage } from "./pages/ReportsPage";
import { ReviewQueuePage } from "./pages/ReviewQueuePage";
import { SafetyCenterPage } from "./pages/SafetyCenterPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TelegramBotPage } from "./pages/TelegramBotPage";
import { LandingPage } from "../landing";
import { ReportPage } from "../report";

const AnalyticsPage = lazy(() => import("./pages/AnalyticsPage").then((module) => ({ default: module.AnalyticsPage })));
const DesignSystemPage = lazy(() =>
  import("./pages/DesignSystemPage").then((module) => ({ default: module.DesignSystemPage })),
);

export function App() {
  return (
    <Suspense
      fallback={
        <div className="ds-boot" role="status">
          <img src="/images/sentinelloop-logo.png" alt="" width={56} height={56} />
          <p>SentinelLoop AI</p>
          <p>Loading command center</p>
          <span className="ds-ai-processing">Processing</span>
        </div>
      }
    >
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/report" element={<ReportPage />} />
        <Route path="/emergency" element={<EmergencyPage />} />
        <Route path="/emergency/history" element={<EmergencyHistoryPage />} />
        <Route path="/handover/history" element={<HandoverHistoryPage />} />
        <Route path="/incidents" element={<IncidentsPage />} />
        <Route path="/incidents/:incidentId" element={<IncidentDetailPage />} />
        <Route path="/evidence" element={<EvidencePage />} />
        <Route path="/officers" element={<OfficersPage />} />
        <Route path="/people" element={<PeoplePage />} />
        <Route path="/follow-up" element={<FollowUpPage />} />
        <Route path="/coordination" element={<CoordinationPage />} />
        <Route path="/duplicates" element={<DuplicatesPage />} />
        <Route path="/knowledge" element={<KnowledgePage />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/notifications" element={<NotificationsPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/ai-usage" element={<Navigate to="/analytics" replace />} />
        <Route path="/forecast/:predictionId" element={<ForecastPage />} />
        <Route path="/telegram" element={<TelegramBotPage />} />
        <Route path="/safety" element={<SafetyCenterPage />} />
        <Route path="/safety/review" element={<ReviewQueuePage />} />
        <Route path="/safety/debug" element={<GuardrailDebugPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/design-system" element={<DesignSystemPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
