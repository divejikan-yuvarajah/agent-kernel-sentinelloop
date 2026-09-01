import { Badge, ChannelBadge, Panel } from "@ds/index";

type Props = {
  category: string | null;
  location: string | null;
  peopleExposed: number | null | undefined;
  active: boolean | null | undefined;
  injury: boolean | null | undefined;
  inputChannel: string | null | undefined;
  inputMethod?: string | null;
  source?: string | null;
  equipment?: string | null;
};

function sourceBadges(source?: string | null, channel?: string | null, method?: string | null) {
  const badges: string[] = [];
  const src = (source || "").toUpperCase();
  const ch = (channel || "").toLowerCase();
  const meth = (method || "").toLowerCase();
  if (src.includes("QR") || ch === "qr" || ch === "qr_tagged") badges.push("QR Report");
  if (ch === "telegram") badges.push("Telegram");
  if (ch === "manual" || ch === "dashboard" || meth === "dashboard") badges.push("Manual Entry");
  if (meth === "voice") badges.push("Voice Report");
  if (meth === "image" || meth === "photo") badges.push("Image Report");
  if (!badges.length && channel) badges.push(channel);
  return [...new Set(badges)];
}

export function IncidentOverviewCard({
  category,
  location,
  peopleExposed,
  active,
  injury,
  inputChannel,
  inputMethod,
  source,
  equipment,
}: Props) {
  const badges = sourceBadges(source, inputChannel, inputMethod);
  return (
    <Panel title="Incident Overview" className="ii-overview">
      <dl className="ii-overview__grid">
        <div>
          <dt>Category</dt>
          <dd>{category || "—"}</dd>
        </div>
        <div>
          <dt>Location</dt>
          <dd>{location || "—"}</dd>
        </div>
        <div>
          <dt>People Exposed</dt>
          <dd>{peopleExposed ?? "—"}</dd>
        </div>
        <div>
          <dt>Active</dt>
          <dd>{active == null ? "—" : active ? "Yes" : "No"}</dd>
        </div>
        <div>
          <dt>Injury</dt>
          <dd>{injury == null ? "—" : injury ? "Yes" : "No"}</dd>
        </div>
        <div>
          <dt>Reported Via</dt>
          <dd>
            <ChannelBadge channel={inputChannel} />
          </dd>
        </div>
        {equipment ? (
          <div>
            <dt>Equipment</dt>
            <dd>{equipment}</dd>
          </div>
        ) : null}
      </dl>
      {badges.length ? (
        <div className="ii-overview__badges" aria-label="Report source badges">
          {badges.map((badge) => (
            <Badge key={badge}>{badge}</Badge>
          ))}
        </div>
      ) : null}
    </Panel>
  );
}
