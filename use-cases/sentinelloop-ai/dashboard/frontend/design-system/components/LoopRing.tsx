import type { LoopStage } from "../types";

const TEAL_STAGES = new Set(["verify", "learn"]);

type Props = {
  stages: LoopStage[];
  openCount: number;
  activeStage?: string | null;
  onSelectStage?: (stage: string) => void;
  loading?: boolean;
};

function polar(cx: number, cy: number, radius: number, angle: number) {
  const rad = ((angle - 90) * Math.PI) / 180;
  return { x: cx + radius * Math.cos(rad), y: cy + radius * Math.sin(rad) };
}

function donutSegment(cx: number, cy: number, inner: number, outer: number, start: number, end: number) {
  const large = end - start > 180 ? 1 : 0;
  const outerStart = polar(cx, cy, outer, start);
  const outerEnd = polar(cx, cy, outer, end);
  const innerEnd = polar(cx, cy, inner, end);
  const innerStart = polar(cx, cy, inner, start);
  return [
    `M ${outerStart.x} ${outerStart.y}`,
    `A ${outer} ${outer} 0 ${large} 1 ${outerEnd.x} ${outerEnd.y}`,
    `L ${innerEnd.x} ${innerEnd.y}`,
    `A ${inner} ${inner} 0 ${large} 0 ${innerStart.x} ${innerStart.y}`,
    "Z",
  ].join(" ");
}

export function LoopRing({ stages, openCount, activeStage, onSelectStage, loading = false }: Props) {
  const total = stages.reduce((sum, stage) => sum + stage.count, 0);
  const cx = 120;
  const cy = 120;
  const gap = 3;
  const sweep = 360 / Math.max(stages.length, 1);
  const padded = String(openCount).padStart(2, "0");

  return (
    <figure className="ds-loop" aria-label="SentinelLoop operational stages">
      <div className="ds-loop__ring">
        <svg viewBox="0 0 240 240" role="presentation">
          {stages.map((stage, index) => {
            const start = index * sweep + gap / 2;
            const end = (index + 1) * sweep - gap / 2;
            const filled = stage.count > 0;
            const teal = TEAL_STAGES.has(stage.stage);
            const selected = activeStage === stage.stage;
            const className = [
              "ds-loop__segment",
              filled ? (teal ? "ds-loop__segment--teal" : "ds-loop__segment--amber") : "ds-loop__segment--empty",
              selected ? "ds-loop__segment--active" : "",
            ]
              .filter(Boolean)
              .join(" ");
            return <path key={stage.stage} d={donutSegment(cx, cy, 72, 104, start, end)} className={className} />;
          })}
        </svg>
        <div className="ds-loop__center">
          <span className="ds-loop__count ds-mono">{loading ? "—" : padded}</span>
          <span className="ds-loop__center-label">Open incidents</span>
        </div>
      </div>
      <div className="ds-loop__controls" role="tablist" aria-label="Filter incidents by loop stage">
        {stages.map((stage) => {
          const filled = stage.count > 0;
          const percent = total ? stage.percentage : 0;
          return (
            <button
              key={stage.stage}
              type="button"
              role="tab"
              aria-selected={activeStage === stage.stage}
              className={`ds-loop__hit${activeStage === stage.stage ? " is-active" : ""}`}
              title={`${stage.label}: ${stage.count} incidents (${percent}%)`}
              aria-label={`${stage.label}: ${stage.count} incidents, ${percent} percent. ${filled ? "Filter dashboard by this stage." : "No incidents at this stage."}`}
              onClick={() => onSelectStage?.(stage.stage)}
            >
              <span className="ds-loop__hit-label">{stage.label}</span>
              <span className="ds-mono ds-loop__hit-meta">
                {stage.count} · {percent}%
              </span>
            </button>
          );
        })}
      </div>
    </figure>
  );
}
