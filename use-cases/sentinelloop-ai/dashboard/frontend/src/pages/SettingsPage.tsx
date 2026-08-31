import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { AppShell, Button, InputField, Modal, Panel, SelectDropdown } from "@ds/index";
import type { GuardrailConfigView } from "@ds/types";

import { fetchGuardrailConfig } from "../api/client";

export function SettingsPage() {
  const [open, setOpen] = useState(false);
  const [config, setConfig] = useState<GuardrailConfigView | null>(null);

  useEffect(() => {
    fetchGuardrailConfig()
      .then(setConfig)
      .catch(() => setConfig(null));
  }, []);
  return (
    <AppShell title="Settings" operationalStatus="RESOLVED">
      <Panel title="Operator preferences">
        <div className="ds-grid" style={{ maxWidth: 420 }}>
          <InputField label="Display name" name="name" defaultValue="A. Perera" />
          <SelectDropdown
            label="Default site"
            name="site"
            options={[
              { value: "colombo", label: "Colombo plant" },
              { value: "kandy", label: "Kandy warehouse" },
            ]}
          />
          <Button onClick={() => setOpen(true)}>Save profile</Button>
        </div>
        <p style={{ marginTop: 24 }}>
          <Link to="/design-system">Design system catalog</Link>
        </p>
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
