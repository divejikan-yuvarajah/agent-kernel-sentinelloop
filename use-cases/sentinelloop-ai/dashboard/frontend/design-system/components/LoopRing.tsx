import type { LoopStage } from "../types";

const TEAL_STAGES = new Set(["verify"]);
const AMBER_STAGES = new Set(["assess"]);
const CRITICAL_STAGES = new Set(["alert"]);

function segmentTone(stage: string, filled: boolean) {
  if (!filled) return "ds-loop__segment--empty";
  if (TEAL_STAGES.has(stage)) return "ds-loop__segment--teal";
  if (CRITICAL_STAGES.has(stage)) return "ds-loop__segment--critical";
  if (AMBER_STAGES.has(stage)) return "ds-loop__segment--amber";
  return "ds-loop__segment--maroon";
}

type Props = {
  stages: LoopStage[];
  openCount: number;
  activeStage?: string | null;
  onSelectStage?: (stage: string) => void;
  loading?: boolean;
  className?: string;
  mode?: "filter" | "showcase";
  centerLabel?: string;
  centerValue?: string;
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

export function LoopRing({
  stages,
  openCount,
  activeStage,
  onSelectStage,
  loading = false,
  className = "",
  mode = "filter",
  centerLabel,
  centerValue,
}: Props) {
  const showcase = mode === "showcase";
  const total = stages.reduce((sum, stage) => sum + stage.count, 0);
  const size = showcase ? 280 : 240;
  const cx = size / 2;
  const cy = size / 2;
  const inner = showcase ? 92 : 72;
  const outer = showcase ? 132 : 104;
  const gap = 3;
  const sweep = 360 / Math.max(stages.length, 1);
  const padded = String(openCount).padStart(2, "0");
  const figureClass = ["ds-loop", showcase ? "ds-loop--showcase" : "", className].filter(Boolean).join(" ");

  return (
    <figure className={figureClass} aria-label={showcase ? "SentinelLoop safety loop" : "SentinelLoop operational stages"}>
      <div className="ds-loop__ring">
        <svg viewBox={`0 0 ${size} ${size}`} role="presentation">
          {stages.map((stage, index) => {
            const start = index * sweep + gap / 2;
            const end = (index + 1) * sweep - gap / 2;
            const filled = showcase || stage.count > 0;
            const selected = activeStage === stage.stage;
            const segmentClass = [
              "ds-loop__segment",
              segmentTone(stage.stage, filled),
              selected ? "ds-loop__segment--active" : "",
            ]
              .filter(Boolean)
              .join(" ");
            return <path key={stage.stage} d={donutSegment(cx, cy, inner, outer, start, end)} className={segmentClass} />;
          })}
        </svg>
        <div className="ds-loop__center">
          <span className="ds-loop__count ds-mono">{centerValue ?? (loading ? "—" : padded)}</span>
          <span className="ds-loop__center-label">{centerLabel ?? "Open incidents"}</span>
        </div>
      </div>
      <div
        className="ds-loop__controls"
        role={showcase ? "group" : "tablist"}
        aria-label={showcase ? "Loop stages" : "Filter incidents by loop stage"}
      >
        {stages.map((stage) => {
          const filled = showcase || stage.count > 0;
          const percent = total ? stage.percentage : 0;
          return (
            <button
              key={stage.stage}
              type="button"
              role={showcase ? undefined : "tab"}
              aria-selected={showcase ? undefined : activeStage === stage.stage}
              aria-current={showcase && activeStage === stage.stage ? "true" : undefined}
              className={`ds-loop__hit${activeStage === stage.stage ? " is-active" : ""}`}
              title={showcase ? stage.label : `${stage.label}: ${stage.count} incidents (${percent}%)`}
              aria-label={
                showcase
                  ? stage.label
                  : `${stage.label}: ${stage.count} incidents, ${percent} percent. ${filled ? "Filter dashboard by this stage." : "No incidents at this stage."}`
              }
              onClick={() => onSelectStage?.(stage.stage)}
            >
              <span className="ds-loop__hit-label">{stage.label}</span>
              {showcase ? null : (
                <span className="ds-mono ds-loop__hit-meta">
                  {stage.count} · {percent}%
                </span>
              )}
            </button>
          );
        })}
      </div>
    </figure>
  );
}
