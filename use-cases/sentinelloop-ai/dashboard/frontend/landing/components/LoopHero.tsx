import { useEffect, useState } from "react";

import { LoopRing } from "@ds/index";

import { LOOP_STAGES, STAGE_IDENTITY } from "../constants";
import { usePrefersReducedMotion } from "../usePrefersReducedMotion";

const STEP_MS = 1800;

export function LoopHero() {
  const reducedMotion = usePrefersReducedMotion();
  const [active, setActive] = useState(LOOP_STAGES[0].stage);
  const current = STAGE_IDENTITY[active] ?? STAGE_IDENTITY.report;

  useEffect(() => {
    if (reducedMotion) return;
    const id = window.setInterval(() => {
      setActive((stage) => {
        const index = LOOP_STAGES.findIndex((item) => item.stage === stage);
        return LOOP_STAGES[(index + 1) % LOOP_STAGES.length].stage;
      });
    }, STEP_MS);
    return () => window.clearInterval(id);
  }, [reducedMotion]);

  return (
    <div className={`sl-loop-hero${reducedMotion ? "" : " sl-loop-hero--motion"}`}>
      <LoopRing
        className="sl-loop-hero__ring"
        stages={LOOP_STAGES}
        openCount={LOOP_STAGES.length}
        activeStage={active}
        mode="showcase"
        centerLabel="Safety loop"
        centerValue={current.title}
        onSelectStage={setActive}
      />
      <p className="sl-loop-hero__identity" aria-live="polite">
        <strong>{current.title}</strong>
        <span>{current.body}</span>
      </p>
    </div>
  );
}
