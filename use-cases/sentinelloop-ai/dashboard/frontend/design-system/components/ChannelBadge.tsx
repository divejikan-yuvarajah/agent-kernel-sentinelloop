import { Badge } from "./Badge";

const CHANNELS: Record<string, { emoji: string; label: string }> = {
  telegram: { emoji: "💬", label: "Telegram" },
  slack: { emoji: "💬", label: "Slack" },
  email: { emoji: "📧", label: "Email" },
  manual: { emoji: "🖥", label: "Manual Entry" },
  dashboard: { emoji: "🖥", label: "Manual Entry" },
  qr: { emoji: "📍", label: "QR Report" },
  qr_tagged: { emoji: "📍", label: "QR Report" },
};

export function channelLabel(channel?: string | null) {
  const key = (channel || "").trim().toLowerCase();
  if (key === "qr_tagged") return CHANNELS.qr_tagged;
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
