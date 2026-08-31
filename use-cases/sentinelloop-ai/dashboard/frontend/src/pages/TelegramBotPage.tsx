import { useEffect, useState } from "react";

import { AppShell, Card, Panel } from "@ds/index";

import { fetchAnalyticsSummary, fetchTelegramHealth, type TelegramBotStatus } from "../api/client";
import { demoImages } from "../data/demoImages";
import { EvidenceImage } from "../components/EvidenceImage";
import { useDemoMode } from "../demo/useDemoMode";

function ShareRows({ items }: { items: { label: string; percent: number }[] }) {
  return (
    <div className="ds-share">
      {items.map((item) => (
        <div key={item.label} className="ds-share__row">
          <span>{item.label}</span>
          <span className="ds-share__track">
            <span className="ds-share__fill" style={{ width: `${Math.round(item.percent)}%` }} />
          </span>
          <span className="ds-mono">{item.percent}%</span>
        </div>
      ))}
    </div>
  );
}

export function TelegramBotPage() {
  const [demo] = useDemoMode();
  const [health, setHealth] = useState<TelegramBotStatus | null>(null);
  const [types, setTypes] = useState<{ label: string; percent: number }[]>([]);
  const [languages, setLanguages] = useState<{ label: string; percent: number }[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchTelegramHealth(), fetchAnalyticsSummary()])
      .then(([status, analytics]) => {
        setHealth(status);
        const typeMap = analytics.telegram_message_types ?? status.message_types ?? {};
        const langMap = analytics.telegram_languages ?? status.language_distribution ?? {};
        setTypes(Object.entries(typeMap).map(([label, percent]) => ({ label, percent })));
        setLanguages(Object.entries(langMap).map(([label, percent]) => ({ label, percent })));
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, [demo]);

  return (
    <AppShell title="Telegram Bot Monitoring" operationalStatus={health?.connected ? "OPEN" : "INVESTIGATING"}>
      <p className="ds-page-lead">Transport health for the Telegram safety bot. Incident processing stays in the AI pipeline.</p>
      {error ? (
        <p className="ds-empty" role="alert">
          {error}
        </p>
      ) : (
        <>
          <Panel title="Worker Evidence" style={{ marginBottom: 24 }}>
            <p>Reported by: Kamal</p>
            <p>Channel: 📱 Telegram Image</p>
            <p className="ds-mono">Uploaded: 10:32 AM · AI Processing: Completed</p>
            <EvidenceImage src={demoImages.evidence["EV-422-T"].src} alt="Telegram worker photo" ratio="16/9" />
          </Panel>
          <Panel title="Telegram Bot Status" style={{ marginBottom: 24 }}>
            <p>Connected {health?.connected ? "✓" : "—"}</p>
            <p>Polling Active {health?.polling_active ? "✓" : "—"}</p>
            <p>Last Message: {health?.last_message ?? "—"}</p>
            <p>Errors: {health?.errors ?? 0}</p>
          </Panel>
          <div className="ds-grid ds-grid--metrics">
            <Card variant="analytics-card">
              <p className="ds-metric__label">Messages Today</p>
              <p className="ds-metric__value">{health?.messages_today ?? 0}</p>
            </Card>
            <Card variant="analytics-card">
              <p className="ds-metric__label">Active Sessions</p>
              <p className="ds-metric__value">{health?.active_sessions ?? 0}</p>
            </Card>
            <Card variant="analytics-card">
              <p className="ds-metric__label">Voice Reports</p>
              <p className="ds-metric__value">{health?.voice_reports ?? 0}</p>
            </Card>
            <Card variant="analytics-card">
              <p className="ds-metric__label">Image Reports</p>
              <p className="ds-metric__value">{health?.image_reports ?? 0}</p>
            </Card>
            <Card variant="analytics-card">
              <p className="ds-metric__label">Emergency Reports</p>
              <p className="ds-metric__value">{health?.emergency_reports ?? 0}</p>
            </Card>
          </div>
          <div className="ds-grid ds-grid--split" style={{ marginTop: 24 }}>
            <Panel title="Message Types">
              <ShareRows items={types.length ? types : [{ label: "Text", percent: 60 }, { label: "Image", percent: 25 }, { label: "Voice", percent: 15 }]} />
            </Panel>
            <Panel title="Language Distribution">
              <ShareRows
                items={
                  languages.length
                    ? languages
                    : [
                        { label: "Sinhala", percent: 45 },
                        { label: "Tamil", percent: 35 },
                        { label: "English", percent: 20 },
                      ]
                }
              />
            </Panel>
          </div>
        </>
      )}
    </AppShell>
  );
}
