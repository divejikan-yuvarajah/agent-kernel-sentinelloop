import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { AppShell } from "@ds/index";

import {
  fetchSandboxHistory,
  fetchSandboxUsage,
  sendSandboxMessage,
  type SandboxHistoryItem,
  type SandboxMessageResponse,
  type SandboxUsage,
} from "@/api/client";
import "./sandbox.css";

type ChatMessage = {
  id: string;
  role: "worker" | "ai" | "system";
  text: string;
};

const SCENARIOS = [
  { id: "electrical", label: "Electrical Emergency", text: "There is a damaged wire near machine 4" },
  { id: "chemical", label: "Chemical Spill", text: "Chemical liquid spilled in storage area" },
  { id: "slip", label: "Slip Hazard", text: "Water leaking on factory floor" },
  { id: "ppe", label: "PPE Violation", text: "Worker operating without helmet" },
] as const;

const LANGS = [
  {
    id: "en",
    label: "English",
    text: "Smoke coming from machine 4. Three workers nearby.",
  },
  {
    id: "si",
    label: "Sinhala",
    text: "යන්ත්‍ර 4 වෙතින් දුම් එනවා. කම්කරුවන් තුන් දෙනෙක් අසල සිටිනවා.",
  },
  {
    id: "ta",
    label: "Tamil",
    text: "இயந்திரம் 4 இலிருந்து புகை வருகிறது. மூன்று தொழிலாளர்கள் அருகில் உள்ளனர்.",
  },
] as const;

const PROCESS_STEPS = ["Translating", "Extracting hazards", "Calculating risk", "Preparing response"] as const;

function newSessionId() {
  return `demo-user-${Math.random().toString(36).slice(2, 8)}`;
}

function formatAiReply(result: SandboxMessageResponse): string {
  const lines: string[] = [];
  if (result.translation) {
    lines.push(`Translation → ${result.translation}`);
  }
  if (result.clarification_required && result.worker_reply) {
    lines.push(result.worker_reply);
    return lines.join("\n\n");
  }
  lines.push(`Language: ${result.language || "Detected"}`);
  lines.push(`Category: ${result.category || "Hazard"}`);
  lines.push(`Risk: ${result.risk_level || "—"} (score ${result.risk_score ?? "—"})`);
  if (result.guidance?.length) {
    lines.push("", "Safety guidance:");
    for (const item of result.guidance) lines.push(`• ${item}`);
  } else if (result.guidance_text) {
    lines.push("", result.guidance_text);
  }
  if (result.slack_alert_preview) {
    lines.push("", result.slack_alert_preview);
  }
  return lines.join("\n");
}

export function SandboxPage() {
  const fileInputId = useId();
  const [sessionId] = useState(newSessionId);
  const [text, setText] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "system",
      text: "Safety Operations Simulator ready. Describe a workplace hazard to run the live SentinelLoop pipeline.",
    },
  ]);
  const [busy, setBusy] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [judgeMode, setJudgeMode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [latest, setLatest] = useState<SandboxMessageResponse | null>(null);
  const [usage, setUsage] = useState<SandboxUsage | null>(null);
  const [history, setHistory] = useState<SandboxHistoryItem[]>([]);
  const [photo, setPhoto] = useState<{ base64: string; filename: string; type: string } | null>(null);
  const chatRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void fetchSandboxUsage(sessionId).then(setUsage).catch(() => undefined);
    void fetchSandboxHistory(12)
      .then((rows) => setHistory(rows))
      .catch(() => undefined);
  }, [sessionId]);

  useEffect(() => {
    const node = chatRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, busy]);

  useEffect(() => {
    if (!busy) {
      setStepIndex(0);
      return;
    }
    const timer = window.setInterval(() => {
      setStepIndex((current) => Math.min(current + 1, PROCESS_STEPS.length));
    }, 420);
    return () => window.clearInterval(timer);
  }, [busy]);

  async function runMessage(nextText: string, scenario?: string, replay = false) {
    const body = nextText.trim();
    if (!body || busy) return;
    setError(null);
    setBusy(true);
    setText("");
    setMessages((current) => [
      ...current,
      { id: `w-${Date.now()}`, role: "worker", text: body },
    ]);
    try {
      const result = await sendSandboxMessage({
        session_id: sessionId,
        text: body,
        image_base64: photo?.base64,
        image_filename: photo?.filename,
        image_content_type: photo?.type,
        judge_mode: judgeMode,
        scenario,
        simulate: true,
      });
      setLatest(result);
      setUsage(result.usage || (await fetchSandboxUsage(sessionId)));
      setHistory(await fetchSandboxHistory(12));
      setMessages((current) => [
        ...current,
        { id: `a-${Date.now()}`, role: "ai", text: formatAiReply(result) },
      ]);
      if (photo) setPhoto(null);
      if (replay) {
        setMessages((current) => [
          ...current,
          { id: `s-${Date.now()}`, role: "system", text: "Replay complete — same production pipeline executed again." },
        ]);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Sandbox request failed";
      setError(message);
      setMessages((current) => [
        ...current,
        { id: `e-${Date.now()}`, role: "system", text: message },
      ]);
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void runMessage(text);
  }

  function onFile(file: File | null) {
    if (!file) return;
    const allowed = new Set(["image/jpeg", "image/jpg", "image/png", "image/webp"]);
    if (!allowed.has(file.type)) {
      setError("Image must be jpg, png, or webp");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const raw = String(reader.result || "");
      const base64 = raw.includes(",") ? raw.split(",", 1)[1] : raw;
      setPhoto({ base64, filename: file.name, type: file.type });
    };
    reader.readAsDataURL(file);
  }

  return (
    <AppShell title="Try It Live" operationalStatus="Sandbox isolated" brand="Try It Live">
      <div className="sl-sandbox">
        <header className="sl-sandbox__header">
          <div>
            <h1 className="sl-sandbox__title">SentinelLoop AI Safety Simulator</h1>
            <p className="sl-sandbox__lede">
              Experience the complete safety pipeline without Telegram setup. Worker report → AI understanding → risk →
              guidance → team response → audit evidence.
            </p>
          </div>
          <div className="sl-sandbox__toolbar">
            <button
              type="button"
              className="sl-sandbox__judge"
              aria-pressed={judgeMode}
              onClick={() => setJudgeMode((value) => !value)}
            >
              🎯 Judge Demo Mode
            </button>
            <span className="ds-mono" style={{ fontSize: "var(--font-size-xs)", color: "var(--muted)" }}>
              session {sessionId}
            </span>
          </div>
        </header>

        <div className="sl-sandbox__layout">
          <div className="sl-sandbox__main">
            <section className="sl-sandbox__panel" aria-label="Conversation">
              <h2>Conversation</h2>
              <div className="sl-sandbox__chat" ref={chatRef}>
                {messages.map((item) => (
                  <div
                    key={item.id}
                    className={`sl-sandbox__bubble sl-sandbox__bubble--${item.role === "worker" ? "worker" : "ai"}`}
                  >
                    <span className="sl-sandbox__bubble-meta">
                      {item.role === "worker" ? "Worker report" : item.role === "ai" ? "SentinelLoop AI" : "System"}
                    </span>
                    {item.text}
                  </div>
                ))}
                {busy ? (
                  <div className="sl-sandbox__processing sl-sandbox__processing-pulse" role="status">
                    <strong>Analyzing report...</strong>
                    <ul>
                      {PROCESS_STEPS.map((step, index) => (
                        <li key={step}>
                          {index < stepIndex ? "✓ " : "… "}
                          {step}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>

              <form className="sl-sandbox__composer" onSubmit={onSubmit}>
                <label className="visually-hidden" htmlFor="sandbox-text">
                  Hazard description
                </label>
                <textarea
                  id="sandbox-text"
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                  placeholder="Describe a workplace hazard..."
                  disabled={busy}
                />
                <div className="sl-sandbox__actions">
                  <button className="sl-sandbox__send" type="submit" disabled={busy || !text.trim()}>
                    Send
                  </button>
                  <label className="sl-sandbox__upload" htmlFor={fileInputId}>
                    Upload Image
                  </label>
                  <input
                    id={fileInputId}
                    type="file"
                    accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
                    hidden
                    onChange={(event) => onFile(event.target.files?.[0] || null)}
                  />
                  {photo ? (
                    <span className="ds-mono" style={{ fontSize: "var(--font-size-xs)" }}>
                      {photo.filename}
                    </span>
                  ) : null}
                </div>
                {error ? <p className="sl-sandbox__error">{error}</p> : null}
              </form>
            </section>

            <section className="sl-sandbox__panel">
              <h2>Try Example</h2>
              <div className="sl-sandbox__scenarios">
                {SCENARIOS.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className="sl-sandbox__chip"
                    disabled={busy}
                    onClick={() => void runMessage(item.text, item.id)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              <h2 style={{ marginTop: "var(--space-4)" }}>Multilingual demo</h2>
              <div className="sl-sandbox__langs">
                {LANGS.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className="sl-sandbox__chip"
                    disabled={busy}
                    onClick={() => void runMessage(item.text)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </section>
          </div>

          <aside className="sl-sandbox__side">
            <section className="sl-sandbox__panel">
              <h2>Demo Usage</h2>
              <div className="sl-sandbox__usage">
                <div>
                  <span>Messages</span>
                  <strong>{usage?.session_messages ?? usage?.messages ?? 0}</strong>
                </div>
                <div>
                  <span>AI Cost</span>
                  <strong>${(usage?.ai_cost_usd ?? 0).toFixed(2)}</strong>
                </div>
                <div>
                  <span>Remaining</span>
                  <strong>${(usage?.remaining_usd ?? 10).toFixed(2)}</strong>
                </div>
              </div>
            </section>

            <section className="sl-sandbox__panel">
              <h2>Sandbox Incident Preview</h2>
              {latest ? (
                <dl className="sl-sandbox__preview">
                  <dt>Incident</dt>
                  <dd className="ds-mono">{latest.incident_id || "—"}</dd>
                  <dt>Category</dt>
                  <dd>{latest.category || "Hazard"}</dd>
                  <dt>Risk</dt>
                  <dd>
                    <span className="sl-sandbox__risk">{latest.risk_level || "—"}</span>
                  </dd>
                  <dt>Guidance</dt>
                  <dd>{latest.guidance?.length ? "AI Guidance Generated" : "Pending"}</dd>
                  <dt>Slack</dt>
                  <dd>Slack Alert Simulated</dd>
                </dl>
              ) : (
                <p style={{ margin: 0, color: "var(--muted)", fontSize: "var(--font-size-sm)" }}>
                  Submit a hazard report to generate a sandbox incident card.
                </p>
              )}
              {latest ? (
                <button
                  type="button"
                  className="sl-sandbox__chip"
                  style={{ marginTop: "var(--space-3)" }}
                  disabled={busy}
                  onClick={() => void runMessage(messages.filter((m) => m.role === "worker").at(-1)?.text || "", undefined, true)}
                >
                  Replay Incident
                </button>
              ) : null}
            </section>

            <section className="sl-sandbox__panel">
              <details className="sl-sandbox__trace" open={judgeMode || undefined}>
                <summary>View AI Pipeline</summary>
                <ul className="sl-sandbox__stages">
                  {(latest?.pipeline_stages || []).map((stage) => (
                    <li key={stage.id || stage.label}>
                      <span>{stage.label}</span>
                      <span className="sl-sandbox__ok">
                        {stage.ok ? "✓" : "…"} {stage.detail}
                      </span>
                    </li>
                  ))}
                  {!latest ? <li>Pipeline stages appear after the first response.</li> : null}
                </ul>
              </details>
            </section>

            <section className="sl-sandbox__panel">
              <h2>How did SentinelLoop decide?</h2>
              {latest?.explainability ? (
                <dl className="sl-sandbox__preview">
                  <dt>AI estimates — Severity</dt>
                  <dd>{latest.explainability.ai_estimates?.severity ?? 5}</dd>
                  <dt>AI estimates — Likelihood</dt>
                  <dd>{latest.explainability.ai_estimates?.likelihood ?? 4}</dd>
                  <dt>Deterministic Risk Score</dt>
                  <dd>{latest.explainability.deterministic?.risk_score ?? latest.risk_score}</dd>
                  <dt>Final</dt>
                  <dd>{latest.explainability.deterministic?.final ?? latest.risk_level}</dd>
                  <dt>Note</dt>
                  <dd style={{ fontWeight: 400 }}>{latest.explainability.note}</dd>
                </dl>
              ) : (
                <p style={{ margin: 0, color: "var(--muted)", fontSize: "var(--font-size-sm)" }}>
                  AI estimates. Rules decide.
                </p>
              )}
              {judgeMode && latest?.judge ? (
                <dl className="sl-sandbox__preview" style={{ marginTop: "var(--space-3)" }}>
                  <dt>Processing time</dt>
                  <dd>{latest.judge.processing_ms} ms</dd>
                  <dt>Model used</dt>
                  <dd>{latest.judge.model_used}</dd>
                  <dt>Cost estimate</dt>
                  <dd>${Number(latest.judge.cost_estimate_usd || 0).toFixed(3)}</dd>
                </dl>
              ) : null}
            </section>

            {latest?.vision_suggestion ? (
              <section className="sl-sandbox__panel">
                <h2>AI Vision Analysis</h2>
                <dl className="sl-sandbox__preview">
                  <dt>Status</dt>
                  <dd>{latest.vision_suggestion.status}</dd>
                  <dt>Possible hazard</dt>
                  <dd>{latest.vision_suggestion.possible_hazard}</dd>
                  <dt>Confidence</dt>
                  <dd>{latest.vision_suggestion.confidence}%</dd>
                  <dt>Observations</dt>
                  <dd>
                    {(latest.vision_suggestion.observations || []).map((item) => (
                      <div key={item}>- {item}</div>
                    ))}
                  </dd>
                  <dt>Note</dt>
                  <dd style={{ fontWeight: 400 }}>{latest.vision_suggestion.note}</dd>
                </dl>
              </section>
            ) : null}

            <section className="sl-sandbox__panel">
              <h2>Previous Demo Sessions</h2>
              <ul className="sl-sandbox__history">
                {history.length ? (
                  history.map((row) => (
                    <li key={`${row.session_id}-${row.created_at}-${row.incident_id}`}>
                      <span>
                        <strong className="ds-mono">{row.session_id}</strong>
                        <br />
                        {row.scenario || row.result} · {row.risk_level || "—"}
                      </span>
                      <span>{row.created_at ? new Date(row.created_at).toLocaleString() : ""}</span>
                    </li>
                  ))
                ) : (
                  <li>No sandbox sessions yet.</li>
                )}
              </ul>
            </section>
          </aside>
        </div>
      </div>
    </AppShell>
  );
}

export default SandboxPage;
