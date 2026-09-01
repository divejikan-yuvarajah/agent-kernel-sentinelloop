import { useEffect, useId, useState } from "react";

import { Modal } from "@ds/components/Modal";
import { Button } from "@ds/components/Button";
import type { RouterStatus } from "@ds/types";

import { fetchRouterStatus } from "../../api/client";
import { useDemoMode } from "../../demo/useDemoMode";

function money(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `$${value.toFixed(value >= 1 ? 2 : 3)}`;
}

function tone(status: RouterStatus | null, loading: boolean, failed: boolean): "ok" | "warn" | "down" {
  if (loading) return "ok";
  if (failed || !status || (!status.ledger_available && status.recent_calls.length === 0)) return "down";
  const usage = status.budget.usage_percentage ?? 0;
  if (usage >= 85) return "warn";
  return "ok";
}

function statusLabel(toneKey: "ok" | "warn" | "down", loading: boolean, failed: boolean) {
  if (loading) return "Checking";
  if (failed) return "Unavailable";
  if (toneKey === "down") return "Unavailable";
  if (toneKey === "warn") return "Budget warning";
  return "Online";
}

type Props = {
  className?: string;
};

export function RouterStatusPill({ className = "" }: Props) {
  const [demo] = useDemoMode();
  const [status, setStatus] = useState<RouterStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  const titleId = useId();

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      fetchRouterStatus()
        .then((payload) => {
          if (!cancelled) {
            setStatus(payload);
            setFailed(false);
            setLoading(false);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setStatus(null);
            setFailed(true);
            setLoading(false);
          }
        });
    };
    load();
    const id = window.setInterval(load, 20000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [demo]);

  const key = tone(status, loading, failed);
  const model = status?.recent_calls[0]?.model || "openrouter/free-model";
  const spent = status?.budget.spent ?? null;
  const limit = status?.budget.budget_limit ?? null;
  const remaining =
    status?.budget.remaining != null
      ? status.budget.remaining
      : limit != null && spent != null
        ? Math.max(0, limit - spent)
        : null;
  const lastFailure = status?.recent_calls.find((call) => (call.tier || "").toLowerCase().includes("fail"));

  return (
    <>
      <button
        type="button"
        className={`sl-router-pill sl-router-pill--${key} ${className}`.trim()}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={titleId}
        onClick={() => setOpen(true)}
        title="AI Usage Details"
        aria-label={`Router Status: ${statusLabel(key, loading, failed)}`}
      >
        <span className="sl-router-pill__dot" aria-hidden="true" />
        <span className="sl-router-pill__copy">
          <strong className="sr-only">Router Status</strong>
          <span>{statusLabel(key, loading, failed)}</span>
        </span>
      </button>

      <Modal open={open} title="AI Usage Details" onClose={() => setOpen(false)}>
        <div id={titleId} className="sl-router-modal">
          {loading ? (
            <p role="status">Loading router status…</p>
          ) : failed ? (
            <p role="alert">Router status could not be loaded. Try again shortly.</p>
          ) : (
            <dl>
              <div>
                <dt>Current Model</dt>
                <dd className="ds-mono">{model}</dd>
              </div>
              <div>
                <dt>Requests Today</dt>
                <dd className="ds-mono">{status?.request_count ?? "—"}</dd>
              </div>
              <div>
                <dt>Spend Used</dt>
                <dd className="ds-mono">{money(spent)}</dd>
              </div>
              <div>
                <dt>Remaining Budget</dt>
                <dd className="ds-mono">{money(remaining)}</dd>
              </div>
              <div>
                <dt>Last Failure</dt>
                <dd className="ds-mono">{lastFailure ? lastFailure.model || "recorded" : "None on record"}</dd>
              </div>
            </dl>
          )}
          <div className="ds-toolbar">
            <Button variant="quiet" onClick={() => setOpen(false)}>
              Close
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}
