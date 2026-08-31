import { Link } from "react-router-dom";

import type { PredictionItem } from "../types";
import { Button } from "./Button";

type Props = {
  items: PredictionItem[];
  lastUpdated?: string | null;
  loading?: boolean;
  inspectingId?: string | null;
  onInspect?: (item: PredictionItem) => void;
};

export function formatUpdatedAgo(value?: string | null) {
  if (!value) return null;
  const then = Date.parse(value);
  if (Number.isNaN(then)) return null;
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (mins < 1) return "Updated just now";
  if (mins === 1) return "Updated 1 minute ago";
  if (mins < 60) return `Updated ${mins} minutes ago`;
  const hours = Math.round(mins / 60);
  return hours === 1 ? "Updated 1 hour ago" : `Updated ${hours} hours ago`;
}

export function PredictedRiskZones({ items, lastUpdated, loading = false, inspectingId = null, onInspect }: Props) {
  const stamp = formatUpdatedAgo(lastUpdated);
  if (loading) {
    return (
      <div>
        <span className="ds-skeleton ds-skeleton--title" />
        <span className="ds-skeleton ds-skeleton--line" />
      </div>
    );
  }
  return (
    <div>
      {stamp ? <p className="ds-mono ds-predict__updated">{stamp}</p> : null}
      {items.length === 0 ? (
        <p className="ds-empty">No predicted risk zones in the current 30-day window.</p>
      ) : (
        <ul className="ds-predict" aria-label="Predicted risk zones">
          {items.map((item) => {
            const id = item.prediction_id || `${item.location}-${item.category}`;
            return (
              <li key={id} className="ds-predict__card">
                <p className="ds-predict__kicker">⚠ {item.location}</p>
                <p>
                  {item.category} Hazard
                </p>
                <p className="ds-mono">
                  {item.incident_count} reports in {item.span_days || 30} days
                </p>
                <p>
                  Trend: {item.trend === "increasing" ? "Increasing" : "Stable"}
                </p>
                <p>{item.reason}</p>
                <p>
                  <strong>Recommendation:</strong> {item.recommendation}
                </p>
                <div className="ds-predict__actions">
                  <Button
                    data-testid="schedule-inspection"
                    disabled={inspectingId === id}
                    onClick={() => onInspect?.(item)}
                  >
                    Schedule Inspection
                  </Button>
                  <Link to={`/forecast/${encodeURIComponent(id)}`} className="ds-mono">
                    Risk forecast explanation
                  </Link>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
