import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  ActivityFeed,
  AppShell,
  Card,
  IncidentOverviewCard,
  LoopRing,
  Panel,
  RecurringHazardsWidget,
  ResponsePerformanceWidget,
  RiskDistributionWidget,
  RouterStatusStrip,
} from "@ds/index";
import type { AnalyticsSummary, IncidentSummary, LoopStage, RecurringHazard, RouterStatus } from "@ds/types";

import { fetchAnalyticsSummary, fetchIncidents, fetchRecurring, fetchRouterStatus } from "../api/client";
import { organization } from "../data/demoData";
import { incidentThumbnail, locationImage, recentEvidenceFeed, locationRiskDemo } from "../data/demoImages";
import { EvidenceImage } from "../components/EvidenceImage";
import { useDemoMode } from "../demo/useDemoMode";

const FALLBACK_STAGES: LoopStage[] = [
  { stage: "report", label: "Report", count: 0, percentage: 0 },
  { stage: "understand", label: "Understand", count: 0, percentage: 0 },
  { stage: "assess", label: "Assess", count: 0, percentage: 0 },
  { stage: "alert", label: "Alert", count: 0, percentage: 0 },
  { stage: "act", label: "Act", count: 0, percentage: 0 },
  { stage: "verify", label: "Verify", count: 0, percentage: 0 },
  { stage: "learn", label: "Learn", count: 0, percentage: 0 },
];

function formatFeedTime(value: string) {
  if (/^\d{2}:\d{2}/.test(value)) return value.slice(0, 5);
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toISOString().slice(11, 16);
}

export function DashboardPage() {
  const navigate = useNavigate();
  const [demo] = useDemoMode();
  const [stage, setStage] = useState<string | null>(null);
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [recurring, setRecurring] = useState<RecurringHazard[]>([]);
  const [router, setRouter] = useState<RouterStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      fetchIncidents({ limit: 8, sort_by: "newest", stage: stage ?? undefined }),
      fetchAnalyticsSummary(),
      fetchRecurring(),
      fetchRouterStatus(),
    ])
      .then(([list, analytics, repeats, routerStatus]) => {
        if (cancelled) return;
        setIncidents(list.items);
        setSummary(analytics);
        setRecurring(repeats.items.map((item) => ({ ...item, imageSrc: locationImage(item.location) })));
        setRouter(routerStatus);
        setError(null);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message || "internal dashboard failure");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [stage, demo]);

  const openCount = summary?.open_incidents ?? 0;
  const operationalStatus = summary?.critical_incidents ? "OPEN" : openCount ? "INVESTIGATING" : "RESOLVED";
  const stages = summary?.loop_stages?.length ? summary.loop_stages : FALLBACK_STAGES;
  const activity = useMemo(
    () =>
      (summary?.recent_activity ?? []).map((event) => ({
        ...event,
        timestamp: formatFeedTime(event.timestamp || ""),
      })),
    [summary],
  );
  const trend = summary?.monthly_trend ?? [];
  const trendMax = Math.max(...trend.map((point) => point.value), 1);
  const watchedLocations = locationRiskDemo.filter(
    (site) => !recurring.some((item) => item.location === site.location),
  );
  const kpis = [
    { label: "Total incidents", value: String(summary?.total_incidents ?? 0) },
    { label: "Open incidents", value: String(openCount) },
    { label: "Critical incidents", value: String(summary?.critical_incidents ?? 0) },
    { label: "Resolved this month", value: String(summary?.resolved_this_month ?? summary?.resolved_today ?? 0) },
    { label: "Average response", value: summary?.avg_response_time ?? "—" },
    { label: "AI detection accuracy", value: summary?.ai_detection_accuracy ?? "—" },
  ];

  return (
    <AppShell
      title="Operations overview"
      brand="SENTINELLOOP"
      operationalStatus={operationalStatus}
      notificationCount={summary?.critical_incidents ?? 0}
      openIncidentCount={openCount}
    >
      <p className="ds-page-lead">
        {demo
          ? `${organization.name} command view. Saturated color is reserved for risk, verification, and the loop ring.`
          : "Workplace safety command view. Saturated color is reserved for risk, verification, and the loop ring."}
      </p>
      {error ? (
        <p className="ds-empty" role="alert">
          Dashboard intelligence unavailable. {error}
        </p>
      ) : null}
      <div className="ds-kpi">
        {kpis.map((item) => (
          <Card key={item.label} variant="analytics-card" loading={loading}>
            {loading ? null : (
              <>
                <p className="ds-metric__label">{item.label}</p>
                <p className="ds-metric__value">{item.value}</p>
              </>
            )}
          </Card>
        ))}
      </div>
      <div className="ds-grid ds-grid--split" style={{ marginBottom: "var(--space-5)" }}>
        <Panel title="Latest Critical Hazard">
          {(() => {
            const critical = incidents.find((row) => (row.risk_level || "").toUpperCase() === "CRITICAL") ?? incidents[0];
            if (!critical) return <p className="ds-empty">No critical hazards in the current window.</p>;
            return (
              <button
                type="button"
                onClick={() => navigate(`/incidents/${critical.incident_id}`)}
                style={{ display: "block", width: "100%", background: "none", border: 0, color: "inherit", textAlign: "left", cursor: "pointer", padding: 0 }}
              >
                <EvidenceImage
                  src={incidentThumbnail(critical.incident_id, critical.category, critical.location)}
                  alt={critical.title || "Critical hazard"}
                  ratio="16/9"
                />
                <p style={{ margin: "12px 0 0" }}>{critical.location}</p>
                <p className="ds-mono">{critical.category} · {critical.risk_level} risk</p>
              </button>
            );
          })()}
        </Panel>
        <Panel title="Recent evidence feed">
          {recentEvidenceFeed.map((item) => (
            <button
              key={item.incident_id + item.when}
              type="button"
              onClick={() => navigate(`/incidents/${item.incident_id}`)}
              style={{ display: "grid", gridTemplateColumns: "72px 1fr", gap: 12, width: "100%", background: "none", border: 0, color: "inherit", textAlign: "left", cursor: "pointer", padding: "8px 0" }}
            >
              <EvidenceImage src={item.src} alt={item.title} ratio="1/1" />
              <span>
                <strong>{item.title}</strong>
                <span className="ds-mono" style={{ display: "block", fontSize: "var(--font-size-xs)" }}>
                  {item.channel === "telegram" ? "📱 Telegram Image" : "💬 WhatsApp Image"} · {item.location}
                </span>
                <span className="ds-mono" style={{ fontSize: "var(--font-size-xs)", color: "var(--chalk-muted)" }}>
                  {item.when}
                </span>
              </span>
            </button>
          ))}
        </Panel>
      </div>
      <Panel title="Workshop Safety Map" style={{ marginBottom: "var(--space-5)" }}>
        <div className="ds-photo-grid">
          {locationRiskDemo.map((site) => (
            <article key={site.location} className="ds-location-tile">
              <EvidenceImage src={site.src} alt={site.location} ratio="16/9" />
              <p>
                <strong>{site.location}</strong>
                {site.risk === "CRITICAL" ? " 🔴" : site.risk === "HIGH" ? " 🟠" : " 🟢"}
              </p>
              <p className="ds-mono">
                Active hazards: {site.active} · Current risk: {site.risk}
              </p>
            </article>
          ))}
        </div>
      </Panel>
      <div className="ds-command">
        <Panel className="ds-command__hero" title="Detect · Understand · Act · Learn">
          <p className="sr-only">
            Loop ring shows how many incidents sit in Report, Understand, Assess, Alert, Act, Verify, and Learn.
          </p>
          <LoopRing
            stages={stages}
            openCount={openCount}
            activeStage={stage}
            loading={loading}
            onSelectStage={(next) => setStage((current) => (current === next ? null : next))}
          />
          <div className="ds-command__metrics">
            {loading ? (
              <>
                <Card variant="analytics-card" loading />
                <Card variant="analytics-card" loading />
              </>
            ) : (
              <>
                <RiskDistributionWidget counts={summary?.incidents_by_risk_level ?? {}} />
                <ResponsePerformanceWidget
                  avgResponse={summary?.avg_response_time ?? null}
                  avgResolution={summary?.average_resolution_time ?? null}
                  fastest={summary?.fastest_response_time ?? null}
                  slowest={summary?.slowest_response_time ?? null}
                />
              </>
            )}
          </div>
        </Panel>
        <Panel title="Live incident feed">
          <ActivityFeed events={activity.slice(0, 6)} loading={loading} />
        </Panel>
      </div>
      {trend.length > 0 ? (
        <div className="ds-grid ds-grid--split" style={{ marginBottom: "var(--space-5)" }}>
          <Panel title="Incident trend · last 12 months">
            <div className="ds-chart" role="img" aria-label="Incident counts by month">
              {trend.map((point) => (
                <div key={point.label} className="ds-chart__col">
                  <div className="ds-chart__bar" style={{ height: `${Math.round((point.value / trendMax) * 100)}%` }} />
                  <span className="ds-chart__label">
                    {point.label}
                    <br />
                    {point.value}
                  </span>
                </div>
              ))}
            </div>
          </Panel>
          <Panel title="Hazard category distribution">
            <div className="ds-share">
              {(summary?.category_share ?? []).map((item) => (
                <div key={item.label} className="ds-share__row">
                  <span>{item.label}</span>
                  <span className="ds-share__track">
                    <span className="ds-share__fill" style={{ width: `${item.percent}%` }} />
                  </span>
                  <span className="ds-mono">{item.percent}%</span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      ) : null}
      <RouterStatusStrip status={router} loading={loading} />
      <div className="ds-dash-learn">
        <Panel title={stage ? `Incidents · ${stage}` : "Active incidents"} titleTooltip="We detect hazards.">
          {loading ? (
            <div className="ds-grid ds-grid--cards">
              <IncidentOverviewCard
                loading
                incident={{
                  incident_id: "—",
                  title: null,
                  category: null,
                  location: null,
                  status: "OPEN",
                  risk_level: "MEDIUM",
                  risk_score: null,
                  created_at: null,
                  updated_at: null,
                  elapsed_time: null,
                  assigned_officer: null,
                  duplicate_count: 0,
                  loop_stage: null,
                }}
              />
              <Card variant="incident-card" loading />
            </div>
          ) : incidents.length === 0 ? (
            <p className="ds-empty">No active incidents. All safety issues are currently resolved.</p>
          ) : (
            <div className="ds-grid ds-grid--cards">
              {incidents.slice(0, 4).map((incident) => (
                <IncidentOverviewCard
                  key={incident.incident_id}
                  incident={incident}
                  imageSrc={incidentThumbnail(incident.incident_id, incident.category, incident.location)}
                  onOpen={(id) => navigate(`/incidents/${id}`)}
                />
              ))}
            </div>
          )}
        </Panel>
        <Panel title="Learn · recurring hazards" titleTooltip="We learn recurring problems.">
          <div className="ds-learn-fill">
            <RecurringHazardsWidget items={recurring.slice(0, watchedLocations.length ? 2 : 4)} loading={loading} dense />
            {!loading && watchedLocations.length > 0 ? (
              <ul className="ds-learn-watch" aria-label="Other watched locations">
                {watchedLocations.map((site) => (
                  <li key={site.location}>
                    <EvidenceImage src={site.src} alt={site.location} ratio="1/1" />
                    <span>
                      <strong>{site.location}</strong>
                      <span className="ds-mono">
                        {site.active} active · {site.risk}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </Panel>
      </div>
    </AppShell>
  );
}
