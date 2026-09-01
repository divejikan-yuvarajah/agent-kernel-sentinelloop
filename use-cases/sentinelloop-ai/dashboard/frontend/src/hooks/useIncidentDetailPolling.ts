import { useCallback, useEffect, useRef, useState } from "react";

import { fetchIncident, type IncidentDetail } from "../api/client";

const POLL_MS = 12000;

function detailSignature(detail: IncidentDetail) {
  return [
    detail.status,
    detail.updated_at,
    detail.risk.risk_level,
    detail.risk.risk_score,
    detail.timeline.length,
    detail.evidence.length,
    detail.assigned_officer,
    detail.safety_status,
  ].join("|");
}

export function useIncidentDetailPolling(incidentId: string, enabled: boolean, onUpdate: (detail: IncidentDetail) => void) {
  const onUpdateRef = useRef(onUpdate);
  onUpdateRef.current = onUpdate;
  const lastSig = useRef<string>("");

  const poll = useCallback(() => {
    if (!incidentId || !enabled) return;
    fetchIncident(incidentId)
      .then((detail) => {
        const sig = detailSignature(detail);
        if (sig !== lastSig.current) {
          lastSig.current = sig;
          onUpdateRef.current(detail);
        }
      })
      .catch(() => {
        /* keep last good snapshot */
      });
  }, [enabled, incidentId]);

  useEffect(() => {
    lastSig.current = "";
  }, [incidentId]);

  useEffect(() => {
    if (!enabled || !incidentId) return;
    const id = window.setInterval(poll, POLL_MS);
    return () => window.clearInterval(id);
  }, [enabled, incidentId, poll]);
}

export function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia("(prefers-reduced-motion: reduce)").matches : false,
  );

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  return reduced;
}
