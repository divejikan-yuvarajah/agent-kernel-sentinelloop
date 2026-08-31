import type { RecurringHazard } from "../types";
import { Badge } from "./Badge";

type Props = {
  items: RecurringHazard[];
  loading?: boolean;
  dense?: boolean;
};

export function RecurringHazardsWidget({ items, loading = false, dense = false }: Props) {
  if (loading) {
    return (
      <div>
        <span className="ds-skeleton ds-skeleton--title" />
        <span className="ds-skeleton ds-skeleton--line" />
      </div>
    );
  }
  if (items.length === 0) {
    return <p className="ds-empty">No recurring hazards detected.</p>;
  }
  return (
    <ul className={dense ? "ds-recurring ds-recurring--fill" : "ds-recurring"} aria-label="Recurring workplace problems">
      {items.map((item) => (
        <li key={`${item.category}-${item.location}`}>
          {item.imageSrc ? (
            dense ? (
              <div className="ds-recurring__media">
                <img src={item.imageSrc} alt="" />
              </div>
            ) : (
              <img src={item.imageSrc} alt="" className="ds-thumb" />
            )
          ) : null}
          <div className="ds-recurring__copy">
            <div className="ds-recurring__head">
              <strong>{item.category}</strong>
              <Badge>{item.severity}</Badge>
            </div>
            <p className="ds-mono" style={{ margin: "4px 0", fontSize: "var(--font-size-xs)", color: "var(--chalk-muted)" }}>
              {item.location} · {item.count} in {item.period} · {item.recurrence_percentage}% · {item.trend_direction}
            </p>
            <p style={{ margin: 0, fontSize: "var(--font-size-sm)" }}>{item.recommendation}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}
