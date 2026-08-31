import { useState } from "react";
import { Link } from "react-router-dom";

import { AppShell, Button, InputField, Modal, Panel, SelectDropdown } from "@ds/index";

export function SettingsPage() {
  const [open, setOpen] = useState(false);
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
      <Modal open={open} title="Profile queued" onClose={() => setOpen(false)}>
        <p>Preferences stay local. This dashboard is read-only and does not change incidents or assignments.</p>
        <div style={{ marginTop: 16 }}>
          <Button onClick={() => setOpen(false)}>Close</Button>
        </div>
      </Modal>
    </AppShell>
  );
}
