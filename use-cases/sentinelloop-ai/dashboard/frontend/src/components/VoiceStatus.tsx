import { useEffect, useId, useRef, useState } from "react";

export type VoiceLoopState =
  | "idle"
  | "received"
  | "processing"
  | "generating"
  | "delivered"
  | "failed"
  | "text_only";

type Props = {
  state?: VoiceLoopState | string | null;
  language?: string | null;
  languageName?: string | null;
  voiceReceived?: boolean;
  guidanceGenerated?: boolean;
  voiceReplyDelivered?: boolean;
  textOnly?: boolean;
  playbackUrl?: string | null;
  statusLabel?: string | null;
};

const STATE_LABEL: Record<string, string> = {
  idle: "Idle",
  received: "Voice Received",
  processing: "Processing",
  generating: "Generating Reply",
  delivered: "Delivered",
  failed: "Failed",
  text_only: "Text-only response",
};

function resolveState(props: Props): VoiceLoopState {
  if (props.state && STATE_LABEL[props.state]) return props.state as VoiceLoopState;
  if (props.voiceReplyDelivered) return "delivered";
  if (props.voiceReceived && props.guidanceGenerated) return "generating";
  if (props.voiceReceived) return "processing";
  if (props.textOnly) return "text_only";
  return "idle";
}

export function VoiceStatus(props: Props) {
  const state = resolveState(props);
  const label = props.statusLabel || STATE_LABEL[state] || "Text-only response";
  const lang = props.languageName || props.language || null;
  const audioId = useId();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState<number | null>(null);

  useEffect(() => {
    const node = audioRef.current;
    if (!node) return;
    const onEnded = () => setPlaying(false);
    const onMeta = () => {
      if (Number.isFinite(node.duration)) setDuration(node.duration);
    };
    node.addEventListener("ended", onEnded);
    node.addEventListener("loadedmetadata", onMeta);
    return () => {
      node.removeEventListener("ended", onEnded);
      node.removeEventListener("loadedmetadata", onMeta);
    };
  }, [props.playbackUrl]);

  function togglePlay() {
    const node = audioRef.current;
    if (!node || !props.playbackUrl) return;
    if (playing) {
      node.pause();
      setPlaying(false);
      return;
    }
    void node.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
  }

  const steps = [
    { ok: Boolean(props.voiceReceived), label: "Voice received" },
    { ok: Boolean(props.guidanceGenerated), label: "Guidance generated" },
    { ok: Boolean(props.voiceReplyDelivered), label: "Voice reply delivered" },
  ];

  return (
    <section className="voice-status" aria-labelledby={`${audioId}-title`}>
      <h3 id={`${audioId}-title`} style={{ marginTop: 0 }}>
        Voice Interaction
      </h3>
      <p className="ds-metric__label" style={{ marginBottom: 8 }}>
        Status: {label}
      </p>
      <ul style={{ listStyle: "none", padding: 0, margin: "0 0 12px" }}>
        {steps.map((step) => (
          <li key={step.label} style={{ marginBottom: 4 }}>
            {step.ok ? "✓" : "○"} {step.label}
          </li>
        ))}
      </ul>
      {lang ? (
        <p style={{ margin: "0 0 12px" }}>
          Language: <strong style={{ color: "var(--maroon)" }}>{lang}</strong>
        </p>
      ) : null}
      {props.playbackUrl ? (
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button
            type="button"
            onClick={togglePlay}
            style={{
              background: "var(--maroon)",
              color: "var(--ink)",
              border: "none",
              borderRadius: 6,
              padding: "8px 14px",
              cursor: "pointer",
              fontFamily: "inherit",
            }}
          >
            {playing ? "❚❚ Pause" : "▶ Play guidance audio"}
          </button>
          {duration != null ? (
            <span className="ds-metric__label">{Math.round(duration)}s · {lang || "audio"}</span>
          ) : (
            <span className="ds-metric__label">{lang || "Guidance audio"}</span>
          )}
          <audio ref={audioRef} src={props.playbackUrl} preload="metadata" />
        </div>
      ) : props.voiceReplyDelivered ? (
        <p className="ds-metric__label" style={{ margin: 0 }}>
          Voice reply delivered (audio not retained for worker privacy).
        </p>
      ) : (
        <p className="ds-metric__label" style={{ margin: 0 }}>
          Text-only response
        </p>
      )}
    </section>
  );
}
