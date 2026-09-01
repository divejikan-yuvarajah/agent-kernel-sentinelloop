import { lazy, Suspense, useEffect, useState } from "react";

import { AppShell, Card, Panel, RecurringHazardsWidget, QrLocationsWidget, DuplicateInsightsWidget } from "@ds/index";
import type { AnalyticsPoint, AnalyticsSummary, RecurringHazard, PredictionsResponse } from "@ds/types";
import type { RiskLevel } from "@ds/colors";

import { fetchAnalyticsSummary, fetchPredictions, fetchRecurring } from "../api/client";
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
  const [forecast, setForecast] = useState<PredictionsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([fetchAnalyticsSummary(), fetchRecurring(), fetchPredictions()])
      .then(([analytics, repeats, predicted]) => {
        setSummary(analytics);
        setRecurring(repeats.items);
        setForecast(predicted);
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
  const prevention = forecast?.analytics;
  const weekMax = Math.max(...(forecast?.weekly_counts ?? [1]), 1);
  const timeline = forecast?.predictions[0]?.timeline ?? [];

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
      <Panel title="Voice Safety Reports" style={{ marginTop: 24 }}>
        <div className="ds-grid ds-grid--metrics">
          <Card variant="analytics-card">
            <p className="ds-metric__label">Voice Reports Today</p>
            <p className="ds-metric__value">{summary?.voice_analytics?.reports_today ?? 0}</p>
          </Card>
          <Card variant="analytics-card">
            <p className="ds-metric__label">Average Transcription Time</p>
            <p className="ds-metric__value">
              {summary?.voice_analytics?.average_transcription_seconds != null
                ? `${summary.voice_analytics.average_transcription_seconds} sec`
                : "—"}
            </p>
          </Card>
          <Card variant="analytics-card">
            <p className="ds-metric__label">Most Used Language</p>
            <p className="ds-metric__value">{summary?.voice_analytics?.most_used_language ?? "—"}</p>
          </Card>
        </div>
      </Panel>
      <Panel title="Incident Sources" style={{ marginTop: 24 }}>
        <div className="ds-share">
          {Object.entries(summary?.voice_analytics?.incident_sources ?? { Text: 55, Voice: 30, Image: 15 }).map(
            ([label, value]) => (
              <div key={label} className="ds-share__row">
                <span>{label}</span>
                <span className="ds-share__track">
                  <span className="ds-share__fill" style={{ width: `${Math.round(Number(value))}%` }} />
                </span>
                <span className="ds-mono">{value}%</span>
              </div>
            ),
          )}
        </div>
      </Panel>
      <Panel title="Voice reports completion rate" style={{ marginTop: 24 }}>
        <p>Voice: {summary?.voice_analytics?.completion_rate_voice ?? "—"}%</p>
        <p>Text: {summary?.voice_analytics?.completion_rate_text ?? "—"}%</p>
      </Panel>
      <Panel title="Voice Languages" style={{ marginTop: 24 }}>
        <div className="ds-share">
          {Object.entries(summary?.voice_analytics?.languages ?? {}).map(([label, value]) => (
            <div key={label} className="ds-share__row">
              <span>{label}</span>
              <span className="ds-share__track">
                <span className="ds-share__fill" style={{ width: `${Math.round(Number(value))}%` }} />
              </span>
              <span className="ds-mono">{value}%</span>
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="Most reported hazard" style={{ marginTop: 24 }}>
        <div className="ds-share">
          {(summary?.category_share ?? [
            { label: "Electrical", percent: 35 },
            { label: "Chemical", percent: 15 },
            { label: "Machine", percent: 20 },
            { label: "Fire/Smoke", percent: 10 },
          ]).map((item) => (
            <div key={item.label} className="ds-share__row">
              <span>{item.label}</span>
              <span className="ds-share__track">
                <span className="ds-share__fill" style={{ width: `${Math.round(item.percent)}%` }} />
              </span>
              <span className="ds-mono">{item.percent}%</span>
            </div>
          ))}
        </div>
      </Panel>
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
                { channel: "telegram", count: 0, percentage: 55 },
                { channel: "manual", count: 0, percentage: 30 },
                { channel: "qr", count: 0, percentage: 15 },
              ]).map((row) => (
                <div key={row.channel} className="ds-share__row">
                  <span>
                    {row.channel === "telegram"
                      ? "Telegram"
                      : row.channel === "manual"
                        ? "Manual"
                        : row.channel === "qr"
                          ? "QR Reports"
                          : row.channel}
                  </span>
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
      <div className="ds-grid ds-grid--metrics" style={{ marginTop: 24 }}>
        <Card variant="analytics-card">
          <p className="ds-metric__label">Predicted Risk Zones</p>
          <p className="ds-metric__value">{prevention?.predicted_risk_zones ?? 0}</p>
        </Card>
        <Card variant="analytics-card">
          <p className="ds-metric__label">Resolved Future Risks</p>
          <p className="ds-metric__value">{prevention?.resolved_future_risks ?? 0}</p>
        </Card>
        <Card variant="analytics-card">
          <p className="ds-metric__label">Inspections Triggered</p>
          <p className="ds-metric__value">{prevention?.inspections_triggered ?? 0}</p>
        </Card>
        <Card variant="analytics-card">
          <p className="ds-metric__label">Prevented Recurrences</p>
          <p className="ds-metric__value">{prevention?.prevented_recurrences ?? 0}</p>
        </Card>
      </div>
      <Panel title="Risk trend chart" style={{ marginTop: 24 }}>
        <div className="ds-weekbars ds-weekbars--attention" role="img" aria-label="Incident frequency over four weeks">
          {(forecast?.weekly_counts ?? [0, 0, 0, 0]).map((value, index) => (
            <div key={`week-${index}`} className="ds-weekbars__col">
              <div className="ds-weekbars__bar" style={{ height: `${Math.max(8, Math.round((value / weekMax) * 100))}px` }} />
              <span className="ds-mono">
                Week {index + 1}
                <br />
                {value}
              </span>
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="Safety Prediction Heatmap" style={{ marginTop: 24 }}>
        <div className="ds-heatmap">
          {(forecast?.heatmap ?? []).map((cell) => (
            <article key={cell.location}>
              <p>
                <strong>{cell.location}</strong> {cell.marker}
              </p>
              <p className="ds-mono">
                {cell.risk} · {cell.active} active
                {cell.electrical_images ? ` · Electrical images: ${cell.electrical_images}` : ""}
                {cell.machine_images ? ` · Machine images: ${cell.machine_images}` : ""}
              </p>
            </article>
          ))}
        </div>
      </Panel>
      <Panel title="Hazard Detection By Image" style={{ marginTop: 24 }}>
        <div className="ds-share">
          {(summary?.vision_analytics?.hazard_detection_by_image ?? []).map((row) => (
            <div key={row.label} className="ds-share__row">
              <span>{row.label}</span>
              <span className="ds-share__track">
                <span className="ds-share__fill" style={{ width: `${Math.round(row.percent)}%` }} />
              </span>
              <span className="ds-mono">{row.percent}%</span>
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="Confidence Distribution" style={{ marginTop: 24 }}>
        <div className="ds-share">
          {Object.entries(summary?.vision_analytics?.confidence_distribution ?? {}).map(([label, value]) => (
            <div key={label} className="ds-share__row">
              <span>{label} confidence</span>
              <span className="ds-share__track">
                <span className="ds-share__fill" style={{ width: `${Math.round(Number(value))}%` }} />
              </span>
              <span className="ds-mono">{value}%</span>
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="Vision model usage" style={{ marginTop: 24 }}>
        <p>Free Vision Models: {summary?.vision_analytics?.model_usage?.free_percent ?? 0}%</p>
        <p>Paid Fallback: {summary?.vision_analytics?.model_usage?.paid_percent ?? 0}%</p>
        <p>
          Average Cost: ${Number(summary?.vision_analytics?.model_usage?.average_cost_usd ?? 0).toFixed(3)}/image
        </p>
      </Panel>
      <Panel title="Vision location heatmap" style={{ marginTop: 24 }}>
        {(summary?.vision_analytics?.location_heatmap ?? []).map((cell) => (
          <article key={cell.location}>
            <p>
              <strong>{cell.location}</strong>
            </p>
            <p className="ds-mono">
              Electrical images: {cell.electrical_images} · Machine images: {cell.machine_images} · Risk: {cell.risk}
            </p>
          </article>
        ))}
      </Panel>
      <Panel title="Safety intelligence timeline" style={{ marginTop: 24 }}>
        {timeline.length === 0 ? (
          <p className="ds-empty">No prevention timeline yet.</p>
        ) : (
          <ul className="ds-forecast-why">
            {timeline.map((event) => (
              <li key={`${event.date}-${event.label}`}>
                <strong>{event.date}</strong> {event.label}
              </li>
            ))}
          </ul>
        )}
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
        <QrLocationsWidget
          items={summary?.top_qr_locations ?? []}
          taggedCount={summary?.qr_tagged_incidents ?? 0}
        />
      </Panel>
    </AppShell>
  );
}
