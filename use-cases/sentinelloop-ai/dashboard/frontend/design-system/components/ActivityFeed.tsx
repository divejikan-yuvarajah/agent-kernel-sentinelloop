import type { ActivityEvent } from "../types";
import { Card } from "./Card";

type Props = {
  events: ActivityEvent[];
  loading?: boolean;
};

function formatStamp(value: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function ActivityFeed({ events, loading = false }: Props) {
  if (loading) {
    return <Card variant="activity-card" loading />;
  }
  if (events.length === 0) {
    return <Card variant="activity-card" empty emptyMessage="No live activity." />;
  }
  return (
    <Card variant="activity-card">
      <ul className="ds-feed">
        {events.map((event) => (
          <li key={`${event.timestamp}-${event.summary}`} className="ds-feed__item">
            <time className="ds-feed__time" dateTime={event.timestamp}>
              {formatStamp(event.timestamp)}
            </time>
            <div>
              <strong>{event.kind}</strong>
              <div>{event.summary}</div>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
