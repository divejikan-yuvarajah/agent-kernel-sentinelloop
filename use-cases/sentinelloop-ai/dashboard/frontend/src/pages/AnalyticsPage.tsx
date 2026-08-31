import { lazy, Suspense, useEffect, useState } from "react";

import { AppShell, Panel, RecurringHazardsWidget, QrLocationsWidget } from "@ds/index";
import type { AnalyticsPoint, AnalyticsSummary, RecurringHazard } from "@ds/types";
import type { RiskLevel } from "@ds/colors";

import { fetchAnalyticsSummary, fetchRecurring } from "../api/client";

const AnalyticsDashboard = lazy(() =>
  import("@ds/components/AnalyticsDashboard").then((module) => ({ default: module.AnalyticsDashboard })),
);

function minutesFromDuration(value: string | null) {
  if (!value) return 0;
  const hours = /(\d+)\s*h/.exec(value);
  const mins = /(\d+)\s*m/.exec(value);
  if (hours || mins) {
    return (hours ? Number(hours[1]) * 60 : 0) + (mins ? Number(mins[1]) : 0);
  }
  return Number.parseInt(value, 10) || 0;
}

export function AnalyticsPage() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [recurring, setRecurring] = useState<RecurringHazard[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchAnalyticsSummary(), fetchRecurring()])
      .then(([analytics, repeats]) => {
        setSummary(analytics);
        setRecurring(repeats.items);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  const riskDistribution = (["LOW", "MEDIUM", "HIGH", "CRITICAL"] as RiskLevel[]).map((level) => ({
    level,
    count: summary?.incidents_by_risk_level[level] ?? 0,
  }));
  const incidentsOverTime: AnalyticsPoint[] = [
    { label: "24h", value: summary?.incidents_last_24_hours ?? 0 },
    { label: "7d", value: summary?.incidents_last_7_days ?? 0 },
    { label: "Open", value: summary?.open_incidents ?? 0 },
    { label: "Total", value: summary?.total_incidents ?? 0 },
  ];
  const responseMinutes = minutesFromDuration(summary?.avg_response_time ?? null);
  const resolutionRate =
    summary && summary.total_incidents
      ? Math.round(((summary.total_incidents - summary.open_incidents) / summary.total_incidents) * 100)
      : 0;

  return (
    <AppShell title="Analytics" operationalStatus="RESOLVED">
      <p className="ds-page-lead">
        Volume, severity mix, and closure performance. Chart color is used only for risk categories.
      </p>
      {error ? (
        <p className="ds-empty" role="alert">
          {error}
        </p>
      ) : (
        <Suspense fallback={<p className="ds-empty">Loading analytics…</p>}>
          <AnalyticsDashboard
            incidentsOverTime={incidentsOverTime}
            riskDistribution={riskDistribution}
            responseMinutes={responseMinutes}
            resolutionRate={resolutionRate}
          />
        </Suspense>
      )}
      <Panel title="Learn · recurring hazards" style={{ marginTop: 24 }}>
        <RecurringHazardsWidget items={recurring} />
      </Panel>
      <Panel title="QR locations" style={{ marginTop: 24 }}>
        <QrLocationsWidget items={summary?.top_qr_locations ?? []} taggedCount={summary?.qr_tagged_incidents ?? 0} />
      </Panel>
    </AppShell>
  );
}
