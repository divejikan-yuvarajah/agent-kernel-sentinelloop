import type { AnalyticsPoint } from "../types";
import type { RiskLevel } from "../colors";
import { Card } from "./Card";
import { Panel } from "./Panel";

type Props = {
  incidentsOverTime: AnalyticsPoint[];
  riskDistribution: { level: RiskLevel; count: number }[];
  responseMinutes: number;
  resolutionRate: number;
};

export function AnalyticsDashboard({ incidentsOverTime, riskDistribution, responseMinutes, resolutionRate }: Props) {
  const max = Math.max(...incidentsOverTime.map((point) => point.value), 1);
  const riskMax = Math.max(...riskDistribution.map((item) => item.count), 1);
  return (
    <div className="ds-grid" style={{ gap: "var(--space-4)" }}>
      <div className="ds-grid ds-grid--metrics">
        <Card variant="analytics-card">
          <p className="ds-metric__label">Mean response</p>
          <p className="ds-metric__value">{responseMinutes} min</p>
        </Card>
        <Card variant="analytics-card">
          <p className="ds-metric__label">Resolution rate</p>
          <p className="ds-metric__value">{resolutionRate}%</p>
        </Card>
        <Card variant="analytics-card">
          <p className="ds-metric__label">Reports (7d)</p>
          <p className="ds-metric__value">{incidentsOverTime.reduce((sum, point) => sum + point.value, 0)}</p>
        </Card>
        <Card variant="analytics-card">
          <p className="ds-metric__label">Critical share</p>
          <p className="ds-metric__value">
            {riskDistribution.find((item) => item.level === "CRITICAL")?.count ?? 0}
          </p>
        </Card>
      </div>
      <Panel title="Incidents over time">
        <div className="ds-chart" role="img" aria-label="Incident volume by day">
          {incidentsOverTime.map((point) => (
            <div key={point.label} className="ds-chart__col">
              <div className="ds-chart__bar" style={{ height: `${Math.round((point.value / max) * 100)}%` }} />
              <span className="ds-chart__label">{point.label}</span>
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="Risk distribution">
        <div className="ds-chart" role="img" aria-label="Incident counts by risk level">
          {riskDistribution.map((item) => (
            <div key={item.level} className="ds-chart__col">
              <div
                className={`ds-chart__bar ds-chart__bar--${item.level}`}
                style={{ height: `${Math.round((item.count / riskMax) * 100)}%` }}
              />
              <span className="ds-chart__label">{item.level}</span>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
