import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { AppShell, Button, InputField, Modal, Panel, SelectDropdown } from "@ds/index";
import type { GuardrailConfigView } from "@ds/types";

import { fetchGuardrailConfig } from "../api/client";
import { organization } from "../data/demoData";
import { demoImages } from "../data/demoImages";
import { useDemoMode } from "../demo/useDemoMode";

export function SettingsPage() {
  const [demo, setDemo] = useDemoMode();
  const [open, setOpen] = useState(false);
  const [config, setConfig] = useState<GuardrailConfigView | null>(null);

  useEffect(() => {
    fetchGuardrailConfig()
      .then(setConfig)
      .catch(() => setConfig(null));
  }, [demo]);

  return (
    <AppShell title="Settings" operationalStatus="RESOLVED">
      <Panel title="Demo Mode">
        <label className="ds-toggle">
          <input
            type="checkbox"
            checked={demo}
            onChange={(event) => setDemo(event.target.checked)}
            name="demo-mode"
          />
          <span>Demo Mode</span>
        </label>
        <p style={{ marginTop: 12, color: "var(--chalk-muted)" }}>
          {demo
            ? `Load ${organization.name} sample data across dashboards, tables, and detail views.`
            : "Use real API and database data. Production workflows stay unchanged."}
        </p>
      </Panel>
      <Panel title="Operator preferences" style={{ marginTop: 24 }}>
        <div className="ds-grid" style={{ maxWidth: 420 }}>
          <InputField
            key={demo ? "demo-name" : "live-name"}
            label="Display name"
            name="name"
            defaultValue={demo ? organization.operator.name : "A. Perera"}
          />
          <SelectDropdown
            key={demo ? "demo-site" : "live-site"}
            label="Default site"
            name="site"
            options={
              demo
                ? [
                    { value: "horizon", label: `${organization.name} · ${organization.site}` },
                    { value: "workshop", label: "Main Workshop Floor" },
                  ]
                : [
                    { value: "colombo", label: "Colombo plant" },
                    { value: "kandy", label: "Kandy warehouse" },
                  ]
            }
          />
          <Button onClick={() => setOpen(true)}>Save profile</Button>
        </div>
        <p style={{ marginTop: 24 }}>
          <Link to="/design-system">Design system catalog</Link>
        </p>
      </Panel>
      <Panel title="Evidence Storage Overview" style={{ marginTop: 24 }}>
        <div className="ds-grid ds-grid--metrics">
          <article>
            <p className="ds-metric__label">Total Images</p>
            <p className="ds-metric__value">{demoImages.storage.totalImages}</p>
          </article>
          <article>
            <p className="ds-metric__label">Before Evidence</p>
            <p className="ds-metric__value">{demoImages.storage.beforeEvidence}</p>
          </article>
          <article>
            <p className="ds-metric__label">After Evidence</p>
            <p className="ds-metric__value">{demoImages.storage.afterEvidence}</p>
          </article>
          <article>
            <p className="ds-metric__label">Pending Review</p>
            <p className="ds-metric__value">{demoImages.storage.pendingReview}</p>
          </article>
        </div>
      </Panel>
      <Panel title="AI Safety policies (admin, read-only)" style={{ marginTop: 24 }}>
        <p>Normal users cannot modify these rules. Changes require a configuration deployment.</p>
        <p>AI Budget Ceiling: {config?.ai_budget_ceiling ?? "unset"}</p>
        <p>Guidance Validation Strictness: {config?.guidance_validation_strictness}</p>
        <p>Anonymous Data Policy: {config?.anonymous_data_policy}</p>
        <p>Closure Rules: {config?.closure_rules}</p>
        <p className="ds-mono">Writable: {config?.writable ? "yes" : "no"}</p>
      </Panel>
      <Modal open={open} title="Profile queued" onClose={() => setOpen(false)}>
        <p>Preferences stay local. This dashboard is read-only and does not change incidents or assignments.</p>
        <div style={{ marginTop: 16 }}>
          <Button onClick={() => setOpen(false)}>Close</Button>
        </div>
      </Modal>
    </AppShell>
  );
}
