import { Panel } from "@ds/index";
import type { PredictionItem } from "@ds/types";

type Props = {
  warning: PredictionItem | null;
  linkedCount: number;
};

export function LocationSafetyHistory({ warning, linkedCount }: Props) {
  const previous = warning?.incident_count ?? linkedCount;
  const last30 = warning?.span_days ? warning.incident_count : linkedCount;
  return (
    <Panel title="Location Safety History" className="ii-history">
      <dl className="ii-overview__grid">
        <div>
          <dt>Previous incidents</dt>
          <dd className="ds-mono">{previous}</dd>
        </div>
        <div>
          <dt>Last 30 days</dt>
          <dd className="ds-mono">{last30}</dd>
        </div>
        {warning?.trend ? (
          <div>
            <dt>Trend</dt>
            <dd>{warning.trend === "increasing" ? "Increasing" : "Stable"}</dd>
          </div>
        ) : null}
      </dl>
      {warning ? (
        <Panel className="ds-warning-panel" title="Future Risk Warning">
          <p>This location has a recurring hazard pattern.</p>
          <p>
            Probability of repeat incident:{" "}
            {warning.risk_level === "High" || warning.trend === "increasing" ? "High" : "Medium"}
          </p>
          <p>Recommended: {warning.recommendation}</p>
        </Panel>
      ) : (
        <p className="ds-empty">No prediction pattern matched for this location yet</p>
      )}
    </Panel>
  );
}
