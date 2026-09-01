import { Button } from "@ds/index";

import type { AuditExport } from "../api/client";

function stamp(value: string | null | undefined) {
  if (!value) return "—";
  try {
    return new Date(value).toISOString().replace("T", " ").replace(/\.\d+Z$/, " UTC");
  } catch {
    return value;
  }
}

function Pair({ label, value }: { label: string; value?: string | number | null }) {
  if (value == null || value === "") return null;
  return (
    <>
      <dt>{label}</dt>
      <dd className={label.toLowerCase().includes("id") || label === "Time" ? "ds-mono" : undefined}>{String(value)}</dd>
    </>
  );
}

type Props = {
  audit: AuditExport;
  onDownload: () => void;
};

export function AuditTrailView({ audit, onDownload }: Props) {
  const info = audit.incident_information;
  const report = audit.original_report;
  const language = audit.language_processing;
  const ai = audit.ai_decision;
  const risk = audit.risk_analysis;
  const resolution = audit.resolution;
  const status = (info.current_status || "").toUpperCase();
  const rail = [
    { label: "Reported", state: "is-done" },
    { label: "Assessed", state: /INVESTIGAT|ASSIGN|ASSESS|PROGRESS|VERIF|RESOLV|CLOSED/.test(status) ? "is-done" : "is-active" },
    { label: "Assigned", state: /ASSIGN|PROGRESS|VERIF|RESOLV|CLOSED/.test(status) ? "is-done" : "" },
    { label: "Verified", state: /VERIF|RESOLV|CLOSED/.test(status) ? "is-done" : "" },
    { label: "Closed", state: /RESOLV|CLOSED/.test(status) ? "is-done" : "" },
  ];

  return (
    <div className="ds-audit-flow">
      <ol className="ds-audit-rail" aria-label="Audit lifecycle">
        {rail.map((step) => (
          <li key={step.label} className={step.state || undefined}>
            {step.label}
          </li>
        ))}
      </ol>
      <p className="ds-empty" role="status" style={{ padding: 0, textAlign: "left" }}>
        Audit generated successfully
      </p>
      <div className="ds-toolbar" style={{ marginBottom: 0 }}>
        <Button onClick={onDownload}>Download JSON</Button>
        <span className="ds-mono" style={{ color: "var(--chalk-muted)", fontSize: "var(--font-size-xs)" }}>
          {audit.audit_metadata.audit_hash?.slice(0, 16)}
        </span>
      </div>

      <section className="ds-audit-step">
        <h3>1. Incident summary</h3>
        <dl className="ds-audit-dl">
          <Pair label="ID" value={info.incident_id} />
          <Pair label="Status" value={info.current_status} />
          <Pair label="Risk" value={info.current_risk_level} />
          <Pair label="Location" value={info.location} />
          <Pair label="Equipment" value={info.equipment} />
          <Pair label="Opened" value={stamp(info.created_at)} />
        </dl>
      </section>

      <section className="ds-audit-step">
        <h3>2. Worker report</h3>
        <p>
          {report.source || "Channel unknown"} · {stamp(report.received_at)}
          {report.input_method ? ` · ${report.input_method}` : ""}
        </p>
        <p className="ds-mono">{report.message || "No original message stored."}</p>
      </section>

      <section className="ds-audit-step">
        <h3>3. AI understanding</h3>
        <p>
          {language.language || language.detected_language || "Language unknown"}
          {language.translated_text ? ` → ${language.translated_text}` : ""}
        </p>
        <dl className="ds-audit-dl">
          {audit.extracted_information.fields.map((field) => (
            <Pair
              key={field.field}
              label={field.field.replace(/_/g, " ")}
              value={field.confidence != null ? `${field.value} (${field.confidence})` : field.value}
            />
          ))}
        </dl>
      </section>

      <section className="ds-audit-step">
        <h3>4. Risk decision</h3>
        <p>
          AI judgement: {ai.severity || "—"} / {ai.likelihood || "—"}
          {ai.confidence != null ? ` · confidence ${ai.confidence}` : ""}
        </p>
        {ai.explanation_label ? <div className="ds-audit-callout">{ai.explanation_label}</div> : null}
        {risk.rule_validation ? <div className="ds-audit-callout">{risk.rule_validation}</div> : null}
        {risk.explanation ? <p>{risk.explanation}</p> : null}
        {ai.override_reason ? (
          <p>
            Human override: {ai.ai_recommendation} → {ai.human_final_decision}. {ai.override_reason}
          </p>
        ) : null}
      </section>

      {audit.voice_report ? (
        <section className="ds-audit-step">
          <h3>Voice report</h3>
          <dl className="ds-audit-dl">
            <Pair label="Input Method" value={audit.voice_report.input_method} />
            <Pair label="Audio Language" value={audit.voice_report.audio_language} />
            <Pair
              label="Transcription"
              value={audit.voice_report.transcription ? `"${audit.voice_report.transcription}"` : null}
            />
            <Pair label="AI Cost" value={audit.voice_report.ai_cost} />
            <Pair label="Human Override" value={audit.voice_report.human_override} />
            <Pair label="Voice Understanding" value={audit.voice_report.confidence_label} />
            <Pair
              label="Voice Reply Sent"
              value={
                audit.voice_report.voice_reply_sent == null
                  ? null
                  : audit.voice_report.voice_reply_sent
                    ? "Yes"
                    : "No"
              }
            />
            <Pair label="Voice Language" value={audit.voice_report.voice_language} />
            <Pair label="Voice Model" value={audit.voice_report.voice_model} />
            <Pair
              label="Voice Cost"
              value={
                audit.voice_report.voice_cost_usd != null ? `$${audit.voice_report.voice_cost_usd}` : null
              }
            />
            <Pair
              label="Full Accessibility Loop"
              value={
                audit.voice_report.full_accessibility_loop == null
                  ? null
                  : audit.voice_report.full_accessibility_loop
                    ? "Completed"
                    : "Incomplete"
              }
            />
          </dl>
        </section>
      ) : null}
      {audit.vision_suggestion ? (
        <section className="ds-audit-step">
          <h3>AI Vision Suggestion</h3>
          <dl className="ds-audit-dl">
            <Pair label="Category" value={audit.vision_suggestion.category} />
            <Pair
              label="Confidence"
              value={
                audit.vision_suggestion.confidence != null
                  ? String(audit.vision_suggestion.confidence)
                  : null
              }
            />
            <Pair label="Final Decision" value={audit.vision_suggestion.final_decision} />
            <Pair label="Override" value={audit.vision_suggestion.override ? "Yes" : "No"} />
            <Pair label="Override reason" value={audit.vision_suggestion.override_reason} />
            <Pair label="Changed by" value={audit.vision_suggestion.changed_by} />
          </dl>
          <p>Observations:</p>
          <ul>
            {(audit.vision_suggestion.observations || []).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p className="ds-mono">Suggestion only. Human text and deterministic rules remain higher priority.</p>
        </section>
      ) : null}

      {audit.emergency_bypass ? (
        <section className="ds-audit-step">
          <h3>Emergency Bypass</h3>
          <dl className="ds-audit-dl">
            <Pair label="Detected" value={audit.emergency_bypass.detected ? "Yes" : "No"} />
            <Pair label="Reason" value={audit.emergency_bypass.reason} />
            <Pair label="Trigger" value={audit.emergency_bypass.trigger_keyword} />
            <Pair label="AI triage" value={audit.emergency_bypass.ai_triage} />
            <Pair label="Response time" value={audit.emergency_bypass.response_time} />
            <Pair label="Later enrichment" value={audit.emergency_bypass.later_enrichment} />
          </dl>
        </section>
      ) : null}

      <section className="ds-audit-step">
        <h3>5. Safety guidance</h3>
        {audit.guidance_history.length === 0 ? (
          <p>No grounded guidance rows were persisted for this incident.</p>
        ) : (
          audit.guidance_history.map((item, index) => (
            <p key={`${item.rule_id || "g"}-${index}`}>
              {item.guidance}
              {item.source ? ` — ${item.source}` : ""}
              {item.line_reference ? ` (${item.line_reference})` : ""}
            </p>
          ))
        )}
      </section>

      <section className="ds-audit-step">
        <h3>6. Human actions</h3>
        {audit.assignment_history.map((row, index) => (
          <p key={`a-${index}`}>
            Assigned {row.officer || "unassigned"} {row.assigned_at ? `at ${stamp(row.assigned_at)}` : ""}
          </p>
        ))}
        {audit.coordination_history.map((row, index) => (
          <p key={`c-${index}`}>
            {row.event}
            {row.channel ? ` · ${row.channel}` : ""} · {stamp(row.time)}
          </p>
        ))}
        {audit.incident_timeline.map((row, index) => (
          <p key={`t-${index}`} className="ds-mono" style={{ fontSize: "var(--font-size-xs)" }}>
            {stamp(row.time)} — {row.event}
            {row.message ? `: ${row.message}` : ""}
          </p>
        ))}
      </section>

      <section className="ds-audit-step">
        <h3>7. Resolution evidence</h3>
        <p>{resolution.status || "Open"}</p>
        {resolution.human_verification ? <div className="ds-audit-callout">{resolution.human_verification}</div> : null}
        {resolution.evidence.map((url) => (
          <p key={url} className="ds-mono">
            {url}
          </p>
        ))}
      </section>
    </div>
  );
}
