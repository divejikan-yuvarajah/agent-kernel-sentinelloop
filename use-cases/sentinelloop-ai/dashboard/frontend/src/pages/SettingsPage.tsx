import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { AppShell, Badge, Button, InputField, Modal, Panel, SelectDropdown } from "@ds/index";
import type { GuardrailConfigView } from "@ds/types";

import { fetchGuardrailConfig } from "../api/client";
import { locations, organization } from "../data/demoData";
import { demoImages } from "../data/demoImages";
import {
  defaultOperatorPrefs,
  useOperatorPrefs,
  type DigestCadence,
  type OperatorPrefs,
  type ShiftName,
  type WorkerLanguage,
} from "../demo/operatorPrefs";
import { OPERATOR_ROLE_LABEL, readOperatorRole, setOperatorRole, type OperatorRole } from "../demo/operatorRole";
import { useDemoMode } from "../demo/useDemoMode";

const TOC = [
  { href: "#workspace", label: "Workspace" },
  { href: "#profile", label: "Profile" },
  { href: "#alerts", label: "Alerts" },
  { href: "#voice", label: "Voice" },
  { href: "#channels", label: "Channels" },
  { href: "#shift", label: "Shift" },
  { href: "#display", label: "Display" },
  { href: "#evidence", label: "Evidence" },
  { href: "#policies", label: "AI policies" },
];

function SwitchRow({
  title,
  hint,
  checked,
  onChange,
  name,
}: {
  title: string;
  hint: string;
  checked: boolean;
  name: string;
  onChange: (next: boolean) => void;
}) {
  return (
    <label className="sl-switch-row">
      <span>
        <strong>{title}</strong>
        <span className="sl-switch-row__hint">{hint}</span>
      </span>
      <input
        className="sl-switch"
        type="checkbox"
        role="switch"
        name={name}
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        aria-label={title}
      />
    </label>
  );
}

function downloadPrefs(prefs: OperatorPrefs, role: OperatorRole, demo: boolean) {
  const blob = new Blob(
    [JSON.stringify({ demo, role, prefs, exported_at: new Date().toISOString() }, null, 2)],
    { type: "application/json" },
  );
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = "sentinelloop-operator-prefs.json";
  link.click();
  URL.revokeObjectURL(href);
}

export function SettingsPage() {
  const [demo, setDemo] = useDemoMode();
  const [prefs, setPrefs] = useOperatorPrefs();
  const [open, setOpen] = useState(false);
  const [savedLabel, setSavedLabel] = useState("Profile queued");
  const [config, setConfig] = useState<GuardrailConfigView | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [role, setRole] = useState<OperatorRole>(readOperatorRole);
  const [nameDraft, setNameDraft] = useState(prefs.displayName);
  const [siteDraft, setSiteDraft] = useState(prefs.defaultSite);

  useEffect(() => {
    fetchGuardrailConfig()
      .then((payload) => {
        setConfig(payload);
        setConfigError(null);
      })
      .catch((err: Error) => {
        setConfig(null);
        setConfigError(err.message);
      });
  }, [demo]);

  useEffect(() => {
    setNameDraft(prefs.displayName);
    setSiteDraft(prefs.defaultSite);
  }, [prefs.displayName, prefs.defaultSite]);

  const siteOptions = useMemo(
    () =>
      demo
        ? [
            { value: "horizon", label: `${organization.name} · ${organization.site}` },
            ...locations.map((site) => ({ value: site, label: site })),
          ]
        : [
            { value: "colombo", label: "Colombo plant" },
            { value: "kandy", label: "Kandy warehouse" },
          ],
    [demo],
  );

  const displayName = prefs.displayName || (demo ? organization.operator.name : "A. Perera");

  function saveProfile() {
    setPrefs({ ...prefs, displayName: nameDraft.trim(), defaultSite: siteDraft });
    setSavedLabel("Profile saved in this browser");
    setOpen(true);
  }

  function resetPrefs() {
    setPrefs(defaultOperatorPrefs());
    setNameDraft("");
    setSiteDraft(defaultOperatorPrefs().defaultSite);
    setSavedLabel("Preferences restored to defaults");
    setOpen(true);
  }

  return (
    <AppShell title="Settings" operationalStatus="RESOLVED">
      <p className="ds-page-lead">
        Operator workspace for Horizon Engineering Workshop. These controls stay in this browser — they do not change
        incidents, assignments, or AI guardrails.
      </p>

      <div className="sl-settings-hero">
        <article>
          <p className="ds-metric__label">Workspace</p>
          <p className="ds-metric__value">{demo ? "Demo Mode" : "Live API"}</p>
          <p>{demo ? organization.name : "Production data"}</p>
        </article>
        <article>
          <p className="ds-metric__label">Signed in as</p>
          <p className="ds-metric__value">{displayName}</p>
          <p>{OPERATOR_ROLE_LABEL[role]}</p>
        </article>
        <article>
          <p className="ds-metric__label">Worker voice</p>
          <p className="ds-metric__value">{prefs.voice.spokenReplies ? "On" : "Off"}</p>
          <p>{prefs.voice.defaultLanguage.toUpperCase()} · text always sent first</p>
        </article>
        <article>
          <p className="ds-metric__label">Duty shift</p>
          <p className="ds-metric__value">{prefs.shift.current}</p>
          <p>{prefs.shift.autoHandover ? "Handover auto-opens" : "Manual handover"}</p>
        </article>
      </div>

      <div className="sl-settings">
        <nav className="sl-settings__nav" aria-label="Settings sections">
          {TOC.map((item) => (
            <a
              key={item.href}
              href={item.href}
              onClick={(event) => {
                event.preventDefault();
                document.getElementById(item.href.slice(1))?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
            >
              {item.label}
            </a>
          ))}
        </nav>

        <div className="sl-settings__body">
          <Panel title="Workspace" id="workspace">
            <SwitchRow
              name="demo-mode"
              title="Demo Mode"
              hint={`Load ${organization.name} sample data across dashboards, tables, and detail views.`}
              checked={demo}
              onChange={setDemo}
            />
            <SelectDropdown
              label="Dashboard role"
              name="role"
              value={role}
              onChange={(event) => {
                const next = event.target.value as OperatorRole;
                setRole(next);
                setOperatorRole(next);
              }}
              options={[
                { value: "officer", label: "Safety Officer — create, assign, verify" },
                { value: "supervisor", label: "Supervisor — review risks, approve closure" },
                { value: "admin", label: "Admin — manage system and analytics" },
              ]}
            />
            <p className="ds-field__help">
              Role only changes what this dashboard lets you attempt. Live incident lifecycle still requires Slack and
              officer confirmation.
            </p>
          </Panel>

          <Panel title="Operator profile" id="profile">
            <div className="sl-settings-form">
              <InputField
                label="Display name"
                name="name"
                value={nameDraft}
                placeholder={demo ? organization.operator.name : "A. Perera"}
                onChange={(event) => setNameDraft(event.target.value)}
              />
              <SelectDropdown
                label="Default site"
                name="site"
                value={siteDraft}
                onChange={(event) => setSiteDraft(event.target.value)}
                options={siteOptions}
              />
            </div>
            <div className="sl-settings-actions">
              <Button onClick={saveProfile}>Save profile</Button>
              <Button variant="ghost" onClick={() => downloadPrefs(prefs, role, demo)}>
                Export preferences
              </Button>
              <Button variant="quiet" onClick={resetPrefs}>
                Reset defaults
              </Button>
            </div>
          </Panel>

          <Panel title="Alert routing" id="alerts">
            <p className="ds-field__help">Choose which operational alerts appear in Notification Center for this browser.</p>
            <SwitchRow
              name="alert-critical"
              title="Critical and emergency alerts"
              hint="Keep sparks, smoke, and emergency command items at the top of the list."
              checked={prefs.alerts.critical}
              onChange={(critical) => setPrefs({ ...prefs, alerts: { ...prefs.alerts, critical } })}
            />
            <SwitchRow
              name="alert-handover"
              title="Shift handover items"
              hint="Surface critical items that must be briefed before the next shift starts."
              checked={prefs.alerts.handover}
              onChange={(handover) => setPrefs({ ...prefs, alerts: { ...prefs.alerts, handover } })}
            />
            <SwitchRow
              name="alert-duplicates"
              title="Duplicate hazard clusters"
              hint="Notify when the same bay files repeated electrical or machine reports."
              checked={prefs.alerts.duplicates}
              onChange={(duplicates) => setPrefs({ ...prefs, alerts: { ...prefs.alerts, duplicates } })}
            />
            <SwitchRow
              name="alert-confirm"
              title="Worker confirmation follow-up"
              hint="Remind when a cleaned area still needs worker verification before close."
              checked={prefs.alerts.workerConfirm}
              onChange={(workerConfirm) => setPrefs({ ...prefs, alerts: { ...prefs.alerts, workerConfirm } })}
            />
            <SelectDropdown
              label="Digest cadence"
              name="digest"
              value={prefs.alerts.digest}
              onChange={(event) =>
                setPrefs({ ...prefs, alerts: { ...prefs.alerts, digest: event.target.value as DigestCadence } })
              }
              options={[
                { value: "off", label: "No digest — alerts only" },
                { value: "hourly", label: "Hourly summary" },
                { value: "shift", label: "End of shift summary" },
              ]}
            />
          </Panel>

          <Panel title="Voice and accessibility" id="voice">
            <p className="ds-field__help">
              Spoken replies never replace text. Emergency keep-away guidance is always sent as text first.
            </p>
            <SwitchRow
              name="voice-spoken"
              title="Spoken worker replies"
              hint="After approved guidance, offer a Sinhala, Tamil, or English voice note on Telegram."
              checked={prefs.voice.spokenReplies}
              onChange={(spokenReplies) => setPrefs({ ...prefs, voice: { ...prefs.voice, spokenReplies } })}
            />
            <SwitchRow
              name="voice-detect"
              title="Match the worker language"
              hint="Prefer the language of the incoming voice note or text report when it is known."
              checked={prefs.voice.autoDetect}
              onChange={(autoDetect) => setPrefs({ ...prefs, voice: { ...prefs.voice, autoDetect } })}
            />
            <SelectDropdown
              label="Fallback spoken language"
              name="voice-lang"
              value={prefs.voice.defaultLanguage}
              onChange={(event) =>
                setPrefs({
                  ...prefs,
                  voice: { ...prefs.voice, defaultLanguage: event.target.value as WorkerLanguage },
                })
              }
              options={[
                { value: "en", label: "English" },
                { value: "si", label: "Sinhala" },
                { value: "ta", label: "Tamil" },
              ]}
            />
          </Panel>

          <Panel title="Channel labels" id="channels">
            <p className="ds-field__help">
              Slack stays the officer channel. Telegram stays the worker channel. Labels here are for this dashboard
              only.
            </p>
            <div className="sl-settings-form">
              <InputField
                label="Officer Slack channel"
                name="slack-channel"
                value={prefs.channels.slackChannel}
                onChange={(event) =>
                  setPrefs({ ...prefs, channels: { ...prefs.channels, slackChannel: event.target.value } })
                }
              />
              <InputField
                label="Worker Telegram label"
                name="telegram-label"
                value={prefs.channels.telegramLabel}
                onChange={(event) =>
                  setPrefs({ ...prefs, channels: { ...prefs.channels, telegramLabel: event.target.value } })
                }
              />
            </div>
            <p>
              <Link to="/telegram">Open Telegram bot monitoring</Link>
              {" · "}
              <Link to="/coordination">Open coordination</Link>
            </p>
          </Panel>

          <Panel title="Shift and handover" id="shift">
            <SelectDropdown
              label="Current shift"
              name="shift"
              value={prefs.shift.current}
              onChange={(event) =>
                setPrefs({ ...prefs, shift: { ...prefs.shift, current: event.target.value as ShiftName } })
              }
              options={[
                { value: "day", label: "Day shift (06:00–18:00)" },
                { value: "night", label: "Night shift (18:00–06:00)" },
                { value: "weekend", label: "Weekend cover" },
              ]}
            />
            <SwitchRow
              name="shift-handover"
              title="Open handover on shift change"
              hint="Keep the latest briefing one click away. Generating a handover still requires an officer action."
              checked={prefs.shift.autoHandover}
              onChange={(autoHandover) => setPrefs({ ...prefs, shift: { ...prefs.shift, autoHandover } })}
            />
            <SwitchRow
              name="quiet-hours"
              title="Quiet hours for non-critical digests"
              hint="Critical and emergency alerts still appear. Hourly digests pause in the window below."
              checked={prefs.shift.quietHours}
              onChange={(quietHours) => setPrefs({ ...prefs, shift: { ...prefs.shift, quietHours } })}
            />
            <div className="sl-settings-form sl-settings-form--split">
              <InputField
                label="Quiet from"
                name="quiet-from"
                type="time"
                value={prefs.shift.quietFrom}
                disabled={!prefs.shift.quietHours}
                onChange={(event) =>
                  setPrefs({ ...prefs, shift: { ...prefs.shift, quietFrom: event.target.value } })
                }
              />
              <InputField
                label="Quiet to"
                name="quiet-to"
                type="time"
                value={prefs.shift.quietTo}
                disabled={!prefs.shift.quietHours}
                onChange={(event) => setPrefs({ ...prefs, shift: { ...prefs.shift, quietTo: event.target.value } })}
              />
            </div>
            <p>
              <Link to="/handover/history">Handover history</Link>
            </p>
          </Panel>

          <Panel title="Display" id="display">
            <SwitchRow
              name="compact-tables"
              title="Compact incident tables"
              hint="Tighter row padding on Incidents, Evidence, and similar lists in this browser."
              checked={prefs.display.compactTables}
              onChange={(compactTables) => setPrefs({ ...prefs, display: { compactTables } })}
            />
            <p>
              <Link to="/design-system">Design system catalog</Link>
            </p>
          </Panel>

          <Panel title="Evidence storage" id="evidence">
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
            <p>
              <Link to="/evidence">Open evidence library</Link>
            </p>
          </Panel>

          <Panel title="AI Safety policies" id="policies">
            <p>Normal users cannot modify these rules. Changes require a configuration deployment.</p>
            {configError ? (
              <p className="ds-empty" role="alert">
                Could not load guardrail policy: {configError}
              </p>
            ) : null}
            <dl className="sl-policy-grid">
              <div>
                <dt>AI Budget Ceiling</dt>
                <dd>{config?.ai_budget_ceiling ?? "unset"}</dd>
              </div>
              <div>
                <dt>Guidance Validation</dt>
                <dd>{config?.guidance_validation_strictness ?? "—"}</dd>
              </div>
              <div>
                <dt>Anonymous Data Policy</dt>
                <dd>{config?.anonymous_data_policy ?? "—"}</dd>
              </div>
              <div>
                <dt>Closure Rules</dt>
                <dd>{config?.closure_rules ?? "—"}</dd>
              </div>
              <div>
                <dt>Max report text</dt>
                <dd className="ds-mono">{config?.max_text_length ?? "—"}</dd>
              </div>
              <div>
                <dt>Writable from UI</dt>
                <dd>
                  <Badge>{config?.writable ? "yes" : "no"}</Badge>
                </dd>
              </div>
            </dl>
            <p>
              <Link to="/safety">Open AI Safety Center</Link>
            </p>
          </Panel>
        </div>
      </div>

      <Modal open={open} title={savedLabel} onClose={() => setOpen(false)}>
        <p>Preferences stay local. This dashboard is read-only and does not change incidents or assignments.</p>
        <div style={{ marginTop: 16 }}>
          <Button onClick={() => setOpen(false)}>Close</Button>
        </div>
      </Modal>
    </AppShell>
  );
}
