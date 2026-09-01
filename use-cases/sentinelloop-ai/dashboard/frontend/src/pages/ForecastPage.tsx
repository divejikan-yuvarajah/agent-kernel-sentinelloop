import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { AppShell, Button, Panel } from "@ds/index";
import type { PredictionItem, PredictionsResponse } from "@ds/types";

import { fetchPredictions, requestInspection } from "../api/client";
import { useDemoMode } from "../demo/useDemoMode";

export function ForecastPage() {
  const { predictionId = "" } = useParams();
  const [demo] = useDemoMode();
  const [payload, setPayload] = useState<PredictionsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    fetchPredictions()
      .then((data) => {
        setPayload(data);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, [demo, predictionId]);

  const decoded = decodeURIComponent(predictionId);
  const item: PredictionItem | undefined = payload?.predictions.find(
    (row) => row.prediction_id === decoded || `${row.location}-${row.category}` === decoded,
  );
  const maxWeek = Math.max(...(item?.weekly_counts ?? [1]), 1);

  async function inspect() {
    if (!item) return;
    try {
      const result = await requestInspection({
        location: item.location,
        category: item.category,
        reason: item.reason,
        recommendation: item.recommendation,
      });
      setNote(
        result.posted
          ? "Inspection requested. Slack note posted by AI Prevention Agent."
          : result.coordination_error || "Inspection note was not delivered.",
      );
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Inspection request failed.");
    }
  }

  return (
    <AppShell title="Risk Forecast Explanation" operationalStatus="INVESTIGATING">
      <p className="ds-page-lead">
        <Link to="/dashboard">Dashboard</Link>
        {" / "}
        Why this zone is predicted
      </p>
      {error ? (
        <p className="ds-empty" role="alert">
          {error}
        </p>
      ) : !item ? (
        <p className="ds-empty">No matching predicted risk zone.</p>
      ) : (
        <>
          <Panel className="ds-predict-panel" title={`${item.location} · ${item.category}`}>
            <p>
              {item.incident_count} reports in {item.span_days || 30} days · Trend:{" "}
              {item.trend === "increasing" ? "Increasing" : "Stable"}
            </p>
            <p>{item.recommendation}</p>
            {note ? <p className="ds-mono">{note}</p> : null}
            <Button data-testid="schedule-inspection" onClick={inspect}>
              Schedule Inspection
            </Button>
          </Panel>
          <Panel title="Why predicted?" style={{ marginTop: 24 }}>
            <ul className="ds-forecast-why">
              {(item.reason_factors.length
                ? item.reason_factors
                : [
                    `${item.incident_count} incidents detected`,
                    "Same location",
                    item.trend === "increasing" ? "Increasing frequency" : "Stable frequency",
                  ]
              ).map((factor) => (
                <li key={factor}>✓ {factor}</li>
              ))}
            </ul>
          </Panel>
          <Panel title="Risk trend" style={{ marginTop: 24 }}>
            <div className="ds-weekbars ds-weekbars--attention" role="img" aria-label="Incident frequency over four weeks">
              {(item.weekly_counts.length ? item.weekly_counts : [0, 0, 0, 0]).map((value, index) => (
                <div key={`week-${index}`} className="ds-weekbars__col">
                  <div className="ds-weekbars__bar" style={{ height: `${Math.max(8, Math.round((value / maxWeek) * 100))}px` }} />
                  <span className="ds-mono">
                    Week {index + 1}
                    <br />
                    {value}
                  </span>
                </div>
              ))}
            </div>
          </Panel>
          <Panel title="Safety intelligence timeline" style={{ marginTop: 24 }}>
            <ul className="ds-forecast-why">
              {item.timeline.map((event) => (
                <li key={`${event.date}-${event.label}`}>
                  <strong>{event.date}</strong> {event.label}
                </li>
              ))}
            </ul>
          </Panel>
        </>
      )}
    </AppShell>
  );
}
