import { lazy, Suspense, useEffect, useState } from "react";

import { AppShell, Card, Panel, RecurringHazardsWidget, QrLocationsWidget, DuplicateInsightsWidget } from "@ds/index";
import type { AnalyticsPoint, AnalyticsSummary, RecurringHazard } from "@ds/types";
import type { RiskLevel } from "@ds/colors";

import { fetchAnalyticsSummary, fetchRecurring } from "../api/client";
import { kpis } from "../data/demoData";
import { useDemoMode } from "../demo/useDemoMode";

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
  const [demo] = useDemoMode();
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [recurring, setRecurring] = useState<RecurringHazard[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([fetchAnalyticsSummary(), fetchRecurring()])
      .then(([analytics, repeats]) => {
        setSummary(analytics);
        setRecurring(repeats.items);
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [demo]);

  const riskDistribution = (["LOW", "MEDIUM", "HIGH", "CRITICAL"] as RiskLevel[]).map((level) => ({
    level,
    count: summary?.incidents_by_risk_level[level] ?? 0,
  }));
  const trend = summary?.monthly_trend ?? [];
  const incidentsOverTime: AnalyticsPoint[] =
    trend.length > 0
      ? trend
      : [
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
  const languages = summary?.worker_languages ?? (demo ? kpis.languages : {});
  const langTotal = Object.values(languages).reduce((sum, value) => sum + value, 0) || 1;

  return (
    <AppShell title="Analytics" operationalStatus="RESOLVED">
      <p className="ds-page-lead">
        Volume, severity mix, and closure performance. Chart color is used only for risk categories.
      </p>
      {error ? (
        <p className="ds-empty" role="alert">
          {error}
        </p>
      ) : loading ? (
        <p className="ds-empty">Loading analytics…</p>
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
      <div className="ds-grid ds-grid--metrics" style={{ marginTop: 24 }}>
        <Card variant="analytics-card">
          <p className="ds-metric__label">Average detection</p>
          <p className="ds-metric__value">{summary?.average_detection ?? summary?.fastest_response_time ?? "—"}</p>
        </Card>
        <Card variant="analytics-card">
          <p className="ds-metric__label">Average assignment</p>
          <p className="ds-metric__value">{summary?.average_assignment ?? "—"}</p>
        </Card>
        <Card variant="analytics-card">
          <p className="ds-metric__label">Average resolution</p>
          <p className="ds-metric__value">{summary?.average_resolution_time ?? "—"}</p>
        </Card>
        <Card variant="analytics-card">
          <p className="ds-metric__label">AI accuracy</p>
          <p className="ds-metric__value">{summary?.ai_detection_accuracy ?? "—"}</p>
        </Card>
      </div>
      <Panel title="Reports by Channel" style={{ marginTop: 24 }}>
        <div className="ds-share">
          {(summary?.reports_by_channel ?? [
            { channel: "telegram", count: 0, percentage: 42 },
            { channel: "whatsapp", count: 0, percentage: 48 },
            { channel: "other", count: 0, percentage: 10 },
          ]).map((row) => (
            <div key={row.channel} className="ds-share__row">
              <span>{row.channel === "telegram" ? "Telegram" : row.channel === "whatsapp" ? "WhatsApp" : "Other"}</span>
              <span className="ds-share__track">
                <span className="ds-share__fill" style={{ width: `${Math.round(row.percentage)}%` }} />
              </span>
              <span className="ds-mono">{row.percentage}%</span>
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="Worker analytics" style={{ marginTop: 24 }}>
        <p>Total reports: {summary?.total_incidents ?? 0}</p>
        <p>Anonymous reports: {summary?.anonymous_reports ?? 0}</p>
        <div className="ds-share" style={{ marginTop: 16 }}>
          {Object.entries(languages).map(([label, value]) => (
            <div key={label} className="ds-share__row">
              <span>{label}</span>
              <span className="ds-share__track">
                <span className="ds-share__fill" style={{ width: `${Math.round((value / langTotal) * 100)}%` }} />
              </span>
              <span className="ds-mono">{value}</span>
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="Learn · recurring hazards" style={{ marginTop: 24 }}>
        <RecurringHazardsWidget items={recurring} />
      </Panel>
      <Panel title="Repeated reports" style={{ marginTop: 24 }}>
        <DuplicateInsightsWidget
          hazards={summary?.most_repeated_hazards ?? []}
          locations={summary?.repeated_hazard_locations ?? []}
        />
      </Panel>
      <Panel title="QR locations" style={{ marginTop: 24 }}>
        <QrLocationsWidget items={summary?.top_qr_locations ?? []} taggedCount={summary?.qr_tagged_incidents ?? 0} />
      </Panel>
    </AppShell>
  );
}
