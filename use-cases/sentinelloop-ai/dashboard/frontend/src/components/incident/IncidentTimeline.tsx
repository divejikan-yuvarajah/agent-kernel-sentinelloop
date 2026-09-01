import { Panel } from "@ds/index";

export type TimelineRow = {
  timestamp: string;
  title: string;
  detail?: string | null;
  actor?: string | null;
};

type Props = {
  events: TimelineRow[];
  animate?: boolean;
};

function toneForEvent(title: string) {
  const text = title.toLowerCase();
  if (/emergency|critical|danger/.test(text)) return "danger";
  if (/verif|resolved|closed|approved|completed/.test(text)) return "verified";
  if (/duplicate|pending|review|await/.test(text)) return "attention";
  if (/risk|assess/.test(text)) return "attention";
  return "progress";
}

function formatTime(value: string) {
  if (/^\d{1,2}:\d{2}/.test(value)) return value.slice(0, 5);
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value || "--:--";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

export function IncidentTimeline({ events, animate = true }: Props) {
  return (
    <Panel title="Full Incident Timeline" className={animate ? "ii-timeline ii-timeline--animate" : "ii-timeline"}>
      {events.length === 0 ? (
        <p className="ds-empty">No status changes recorded</p>
      ) : (
        <ol className="ii-timeline__list">
          {events.map((event, index) => {
            const tone = toneForEvent(event.title);
            return (
              <li
                key={`${event.timestamp}-${event.title}-${index}`}
                className={`ii-timeline__item ii-timeline__item--${tone}`}
                style={{ animationDelay: animate ? `${Math.min(index, 12) * 60}ms` : undefined }}
              >
                <time className="ii-timeline__time ds-mono">{formatTime(event.timestamp)}</time>
                <span className="ii-timeline__dot" aria-hidden="true" />
                <div className="ii-timeline__body">
                  <p className="ii-timeline__title">{event.title}</p>
                  {event.detail ? <p className="ii-timeline__detail">{event.detail}</p> : null}
                  {event.actor ? <p className="ii-timeline__actor ds-mono">{event.actor}</p> : null}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </Panel>
  );
}
