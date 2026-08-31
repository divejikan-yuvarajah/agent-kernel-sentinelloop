import type { RecurringHazard } from "../types";
import { Badge } from "./Badge";

type Props = {
  items: RecurringHazard[];
  loading?: boolean;
};

export function RecurringHazardsWidget({ items, loading = false }: Props) {
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
    <ul className="ds-recurring" aria-label="Recurring workplace problems">
      {items.map((item) => (
        <li key={`${item.category}-${item.location}`}>
          <div className="ds-recurring__head">
            <strong>{item.category}</strong>
            <Badge>{item.severity}</Badge>
          </div>
          <p className="ds-mono" style={{ margin: "4px 0", fontSize: "var(--font-size-xs)", color: "var(--chalk-muted)" }}>
            {item.location} · {item.count} in {item.period} · {item.recurrence_percentage}% · {item.trend_direction}
          </p>
          <p style={{ margin: 0, fontSize: "var(--font-size-sm)" }}>{item.recommendation}</p>
        </li>
      ))}
    </ul>
  );
}
