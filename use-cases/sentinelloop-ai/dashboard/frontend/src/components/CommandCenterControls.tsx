import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { Button, SystemHealthStrip } from "@ds/index";

import { fetchSystemHealth, simulateEmergencyReport, type SystemHealth } from "../api/client";
import { useDemoMode } from "../demo/useDemoMode";
import { useOperatorRole } from "../demo/useOperatorRole";

export function CommandCenterControls() {
  const [demo] = useDemoMode();
  const { canCreate } = useOperatorRole();
  const navigate = useNavigate();
  const location = useLocation();
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [simulating, setSimulating] = useState(false);

  const refreshHealth = useCallback(() => {
    fetchSystemHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    refreshHealth();
    const id = window.setInterval(refreshHealth, 15000);
    return () => window.clearInterval(id);
  }, [refreshHealth, demo, location.pathname]);

  async function simulate() {
    setSimulating(true);
    setNote(null);
    try {
      const result = await simulateEmergencyReport("smoke");
      setNote(
        result.incident_id
          ? `Simulated emergency ${result.incident_id} · risk ${result.risk_level || "calculated"}`
          : result.error || "Simulation completed.",
      );
      refreshHealth();
      if (result.incident_id) navigate(`/incidents/${result.incident_id}`);
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Simulation failed.");
    } finally {
      setSimulating(false);
    }
  }

  return (
    <>
      <SystemHealthStrip health={health} />
      <div className="ds-command-bar">
        {canCreate ? (
          <Link className="ds-btn" to="/report">
            + Log hazard
          </Link>
        ) : (
          <p className="ds-mono">Supervisor role is review-only.</p>
        )}
        {demo ? (
          <Button variant="ghost" disabled={simulating} onClick={() => void simulate()}>
            {simulating ? "Simulating…" : "Simulate Emergency Report"}
          </Button>
        ) : null}
        {note ? <p className="ds-mono">{note}</p> : null}
      </div>
    </>
  );
}
