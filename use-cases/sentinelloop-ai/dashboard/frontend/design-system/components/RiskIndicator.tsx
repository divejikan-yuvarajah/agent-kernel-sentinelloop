import { normalizeRisk, type RiskLevel } from "../colors";

type Props = {
  level: string;
  score?: number | string;
  className?: string;
};

export function RiskIndicator({ level, score, className = "" }: Props) {
  const key: RiskLevel = normalizeRisk(level);
  const scoreLabel = score === undefined ? null : String(score);
  return (
    <span className={`ds-risk ${className}`.trim()}>
      <span className={`ds-risk__bar ds-risk__bar--${key}`} aria-hidden="true" />
      <span className="ds-risk__label">
        {key}
        {scoreLabel ? ` ${scoreLabel}` : ""}
      </span>
    </span>
  );
}
