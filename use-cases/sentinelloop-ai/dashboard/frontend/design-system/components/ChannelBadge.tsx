import { Badge } from "./Badge";

const CHANNELS: Record<string, { emoji: string; label: string }> = {
  telegram: { emoji: "💬", label: "Telegram" },
  slack: { emoji: "💬", label: "Slack" },
  email: { emoji: "📧", label: "Email" },
};

export function channelLabel(channel?: string | null) {
  const key = (channel || "").trim().toLowerCase();
  return CHANNELS[key] ?? { emoji: "💬", label: channel || "Channel" };
}

type Props = {
  channel?: string | null;
  elapsed?: string | null;
};

export function ChannelBadge({ channel, elapsed }: Props) {
  if (!channel) return null;
  const { emoji, label } = channelLabel(channel);
  return (
    <Badge title={`Reported via ${label}`}>
      {emoji} {label}
      {elapsed ? ` · Reported ${elapsed} ago` : ""}
    </Badge>
  );
}
