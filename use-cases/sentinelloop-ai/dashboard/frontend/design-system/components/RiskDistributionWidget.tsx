import type { RiskLevel } from "../colors";
import { normalizeRisk } from "../colors";

const LEVELS: RiskLevel[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

type Props = {
  counts: Record<string, number>;
};

export function RiskDistributionWidget({ counts }: Props) {
  const max = Math.max(...LEVELS.map((level) => counts[level] ?? 0), 1);
  return (
    <section aria-label="Risk distribution">
      <p className="ds-metric__label" title="We understand risk.">
        Risk distribution
      </p>
      <div className="ds-chart ds-chart--risk" role="img" aria-label="Incident counts by risk level">
        {LEVELS.map((level) => {
          const count = counts[level] ?? 0;
          return (
            <div key={level} className="ds-chart__col">
              <div
                className={`ds-chart__bar ds-chart__bar--${normalizeRisk(level)}`}
                style={{ height: `${Math.round((count / max) * 100)}%` }}
              />
              <span className="ds-chart__label">
                {level}
                <br />
                {count}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
