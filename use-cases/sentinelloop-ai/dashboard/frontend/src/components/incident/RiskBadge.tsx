import { normalizeRisk } from "@ds/colors";

type Props = {
  level: string;
  score?: number | null;
  className?: string;
};

export function RiskBadge({ level, score, className = "" }: Props) {
  const key = normalizeRisk(level);
  return (
    <span className={`ii-risk-badge ii-risk-badge--${key} ${className}`.trim()} role="status">
      <span className="ii-risk-badge__label">{key}</span>
      {score != null ? <span className="ii-risk-badge__score ds-mono">{score}</span> : null}
    </span>
  );
}
