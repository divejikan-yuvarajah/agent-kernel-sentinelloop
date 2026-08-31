import type { RepeatedHazardStat } from "../types";

type Props = {
  hazards: RepeatedHazardStat[];
  locations: RepeatedHazardStat[];
};

export function DuplicateInsightsWidget({ hazards, locations }: Props) {
  if (hazards.length === 0 && locations.length === 0) {
    return <p className="ds-empty">No repeated worker reports yet.</p>;
  }
  return (
    <div className="ds-grid" style={{ gap: 24 }}>
      <div>
        <p className="ds-metric__label">Most repeated hazards</p>
        {hazards.length === 0 ? (
          <p className="ds-empty">None yet.</p>
        ) : (
          <ul className="ds-recurring" aria-label="Most repeated hazards">
            {hazards.map((item) => (
              <li key={item.label}>
                <div className="ds-recurring__head">
                  <strong>{item.label}</strong>
                  <span className="ds-mono">{item.count} reports</span>
                </div>
                {item.insight ? <p style={{ margin: "4px 0 0", fontSize: "var(--font-size-sm)" }}>{item.insight}</p> : null}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <p className="ds-metric__label">Repeated hazard locations</p>
        {locations.length === 0 ? (
          <p className="ds-empty">None yet.</p>
        ) : (
          <ul className="ds-recurring" aria-label="Repeated hazard locations">
            {locations.map((item) => (
              <li key={item.location ?? item.label}>
                <div className="ds-recurring__head">
                  <strong>{item.location || item.label}</strong>
                  <span className="ds-mono">{item.count}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
