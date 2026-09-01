export type SystemHealth = {
  telegram: string;
  slack: string;
  database: string;
  ai_services: string;
  last_incident: string | null;
  last_incident_label?: string | null;
  demo_mode?: boolean;
};

type Item = {
  key: string;
  label: string;
  value: string;
};

function tone(value: string) {
  const key = value.toLowerCase();
  if (key === "connected" || key === "available") return "ok";
  if (key === "warning") return "warn";
  return "down";
}

function display(value: string) {
  const key = value.toLowerCase();
  if (key === "connected") return "Connected";
  if (key === "available") return "Available";
  if (key === "warning") return "Simulated";
  if (key === "unavailable") return "Unavailable";
  return "Disconnected";
}

type Props = {
  health: SystemHealth | null;
  loading?: boolean;
};

export function SystemHealthStrip({ health, loading = false }: Props) {
  const items: Item[] = [
    { key: "telegram", label: "Telegram", value: health?.telegram || "disconnected" },
    { key: "slack", label: "Slack", value: health?.slack || "disconnected" },
    { key: "database", label: "Database", value: health?.database || "disconnected" },
    { key: "ai", label: "AI Services", value: health?.ai_services || "unavailable" },
  ];
  return (
    <section className="ds-live-status" aria-label="SentinelLoop live status">
      <p className="ds-live-status__title">SentinelLoop Live Status</p>
      <ul className="ds-live-status__list">
        {items.map((item) => (
          <li key={item.key} className={`ds-live-status__item ds-live-status__item--${tone(item.value)}`}>
            <span className="ds-live-status__dot" aria-hidden="true" />
            <span>
              {item.label}: {loading ? "…" : display(item.value)}
            </span>
          </li>
        ))}
        <li className="ds-live-status__item ds-live-status__item--last">
          Last incident: {health?.last_incident_label || (health?.last_incident ? "received" : "no incidents yet")}
        </li>
      </ul>
    </section>
  );
}
