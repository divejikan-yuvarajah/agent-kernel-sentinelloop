import type { EvidenceItem } from "../types";
import { Card } from "./Card";

type Props = {
  items: EvidenceItem[];
};

export function EvidenceViewer({ items }: Props) {
  if (items.length === 0) {
    return <Card variant="evidence-card" empty emptyMessage="No evidence attached." />;
  }
  return (
    <div className="ds-evidence">
      {items.map((item) => (
        <Card key={item.id} variant="evidence-card" className="ds-evidence__item">
          <div className="ds-evidence__frame" aria-hidden="true" />
          <div className="ds-evidence__meta">
            <p className="ds-evidence__id">{item.id}</p>
            <p style={{ margin: "4px 0 0", fontSize: "var(--font-size-sm)" }}>{item.label}</p>
            <p className="ds-mono" style={{ margin: "8px 0 0", fontSize: "var(--font-size-xs)", color: "var(--chalk-muted)" }}>
              {item.timestamp}
            </p>
            <p style={{ margin: "4px 0 0", fontSize: "var(--font-size-xs)", color: "var(--chalk-muted)" }}>{item.source}</p>
          </div>
        </Card>
      ))}
    </div>
  );
}
