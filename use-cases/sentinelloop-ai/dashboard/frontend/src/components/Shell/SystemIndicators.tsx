import { useEffect, useState } from "react";

import { fetchSystemHealth, type SystemHealth } from "../../api/client";
import { useDemoMode } from "../../demo/useDemoMode";

function tone(value: string) {
  const key = value.toLowerCase();
  if (key === "connected" || key === "available") return "ok";
  if (key === "warning") return "warn";
  return "down";
}

type Props = {
  className?: string;
};

export function SystemIndicators({ className = "" }: Props) {
  const [demo] = useDemoMode();
  const [health, setHealth] = useState<SystemHealth | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      fetchSystemHealth()
        .then((payload) => {
          if (!cancelled) setHealth(payload);
        })
        .catch(() => {
          if (!cancelled) setHealth(null);
        });
    };
    load();
    const id = window.setInterval(load, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [demo]);

  const items = [
    { label: "Telegram", value: health?.telegram || "disconnected" },
    { label: "Slack", value: health?.slack || "disconnected" },
    { label: "Database", value: health?.database || "disconnected" },
    { label: "AI Router", value: health?.ai_services || "unavailable" },
  ];

  return (
    <ul className={`sl-sys ${className}`.trim()} aria-label="Live system indicators">
      {items.map((item) => (
        <li key={item.label} className={`sl-sys__item sl-sys__item--${tone(item.value)}`}>
          <span>{item.label}</span>
          <span className="sl-sys__dot" aria-hidden="true" />
        </li>
      ))}
    </ul>
  );
}
