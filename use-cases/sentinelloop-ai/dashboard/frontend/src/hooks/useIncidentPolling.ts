import { useEffect, useRef, useState } from "react";

import type { IncidentSummary } from "@ds/types";

const POLL_MS = 12000;
const PULSE_MS = 2400;

function signature(item: IncidentSummary) {
  return `${item.incident_id}|${item.status}|${item.risk_level}|${item.updated_at || item.created_at || ""}`;
}

export function diffIncidentPulse(previous: IncidentSummary[], next: IncidentSummary[]) {
  const prior = new Map(previous.map((item) => [item.incident_id, signature(item)]));
  return next.filter((item) => prior.get(item.incident_id) !== signature(item)).map((item) => item.incident_id);
}

export function useIncidentPolling(
  loader: () => Promise<IncidentSummary[]>,
  current: IncidentSummary[],
  setCurrent: (items: IncidentSummary[]) => void,
  enabled = true,
) {
  const [pulseIds, setPulseIds] = useState<string[]>([]);
  const latest = useRef(current);
  latest.current = current;

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const tick = () => {
      loader()
        .then((items) => {
          if (cancelled) return;
          const changed = diffIncidentPulse(latest.current, items);
          setCurrent(items);
          if (changed.length) {
            setPulseIds(changed);
            window.setTimeout(() => {
              if (!cancelled) setPulseIds([]);
            }, PULSE_MS);
          }
        })
        .catch(() => {
          /* keep the last good snapshot */
        });
    };
    const id = window.setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [enabled, loader, setCurrent]);

  return pulseIds;
}
