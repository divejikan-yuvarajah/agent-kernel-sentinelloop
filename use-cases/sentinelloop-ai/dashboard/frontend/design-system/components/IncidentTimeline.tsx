import type { TimelineEvent } from "../types";
import { TimelineItem } from "./TimelineItem";

type Props = {
  events: TimelineEvent[];
};

export function IncidentTimeline({ events }: Props) {
  if (events.length === 0) {
    return <p className="ds-empty">No timeline events.</p>;
  }
  return (
    <ol className="ds-timeline">
      {events.map((event) => (
        <TimelineItem key={`${event.timestamp}-${event.title}`} timestamp={event.timestamp} title={event.title}>
          {event.detail}
        </TimelineItem>
      ))}
    </ol>
  );
}
