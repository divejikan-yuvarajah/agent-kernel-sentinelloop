import type { QrLocationStat } from "../types";

type Props = {
  items: QrLocationStat[];
  taggedCount?: number;
};

export function QrLocationsWidget({ items, taggedCount = 0 }: Props) {
  if (items.length === 0) {
    return <p className="ds-empty">No QR-tagged locations yet.</p>;
  }
  return (
    <div>
      <p className="ds-metric__label" title="Workers scan a posted QR so location is never typed.">
        Top QR locations · {taggedCount} tagged reports
      </p>
      <ul className="ds-recurring" aria-label="Most reported QR locations">
        {items.map((item) => (
          <li key={`${item.location}-${item.equipment ?? ""}`}>
            {item.imageSrc ? <img src={item.imageSrc} alt="" className="ds-thumb" style={{ width: "100%", height: 80, marginBottom: 8 }} /> : null}
            <div className="ds-recurring__head">
              <strong>{item.equipment || item.location}</strong>
              <span className="ds-mono">{item.count}</span>
            </div>
            <p className="ds-mono" style={{ margin: "4px 0", fontSize: "var(--font-size-xs)", color: "var(--chalk-muted)" }}>
              {item.location}
              {item.risk_score != null ? ` · location risk ${item.risk_score}` : ""}
            </p>
            {item.insight ? <p style={{ margin: 0, fontSize: "var(--font-size-sm)" }}>{item.insight}</p> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
