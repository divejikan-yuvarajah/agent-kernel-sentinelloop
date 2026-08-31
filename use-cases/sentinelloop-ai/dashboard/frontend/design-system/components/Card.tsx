import type { HTMLAttributes, ReactNode } from "react";

import { normalizeRisk, type RiskLevel } from "../colors";

export type CardVariant = "incident-card" | "evidence-card" | "officer-card" | "analytics-card" | "activity-card";

type Props = HTMLAttributes<HTMLElement> & {
  variant?: CardVariant;
  riskLevel?: string;
  loading?: boolean;
  empty?: boolean;
  emptyMessage?: string;
  as?: "article" | "div" | "section";
  children?: ReactNode;
};

export function Card({
  variant = "activity-card",
  riskLevel,
  loading = false,
  empty = false,
  emptyMessage = "No records.",
  as: Tag = "article",
  className = "",
  children,
  ...rest
}: Props) {
  const isIncident = variant === "incident-card";
  const risk: RiskLevel | null = isIncident && riskLevel ? normalizeRisk(riskLevel) : null;
  const classes = ["ds-card", isIncident ? "ds-card--incident" : "", loading ? "ds-card--skeleton" : "", className]
    .filter(Boolean)
    .join(" ");

  return (
    <Tag className={classes} tabIndex={rest.onClick ? 0 : rest.tabIndex} {...rest}>
      {risk ? (
        <span className={`ds-card__risk-tab ds-card__risk-tab--${risk}`} aria-hidden="true" />
      ) : null}
      <div className={isIncident ? "ds-card__body" : undefined}>
        {loading ? (
          <>
            <span className="ds-skeleton ds-skeleton--title" />
            <span className="ds-skeleton ds-skeleton--line" />
            <span className="ds-skeleton ds-skeleton--line" />
          </>
        ) : empty ? (
          <p className="ds-empty">{emptyMessage}</p>
        ) : (
          children
        )}
      </div>
    </Tag>
  );
}
