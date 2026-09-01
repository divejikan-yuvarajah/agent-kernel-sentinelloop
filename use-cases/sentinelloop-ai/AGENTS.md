# SentinelLoop AI Agents

Authoritative behavior lives in [`SPEC.md`](SPEC.md). This file is a compact map of the six agents for implementers.

Framework (verified): OpenAI Agents SDK `Agent` objects registered together through one Agent Kernel `OpenAIModule`. Handoffs use SDK `handoffs=[...]`. Telegram `config.yaml` `telegram.agent` is `intake_agent`.

## Pipeline

```text
Telegram
   ↓
intake_agent
   ↓
incident_agent
   ↓
risk_agent
   ↓
guidance_agent
   ↓
coordination_agent
   ↓
followup_agent
```

The chain is not strictly synchronous. Worker traffic always re-enters at `intake_agent`.

## Lifecycle re-entry

```text
Worker clarification → incident_agent
Risk-changing update → risk_agent
Remediation evidence → followup_agent
Worker rejects fix → followup_agent → coordination_agent
```

New or continuing reports go `intake_agent` → `incident_agent`. Pending worker verification replies go `intake_agent` → `followup_agent`.

## `intake_agent`

- **Responsibility:** Normalize inbound worker communication and attach it to the correct session/incident.
- **Main inputs:** Telegram sender id, message id, text/image (and voice transcript if STT is added), timestamp, session cursor, open incidents for the reporter.
- **Main outputs:** Detected language, normalized content, reporter reference, message type, session reference, new-vs-existing incident, media references, next handoff.
- **Allowed next handoff(s):** `incident_agent`; `followup_agent` when the message is verification or remediation evidence.
- **Must not:** Score risk, invent incident facts, close incidents, send Slack operational alerts.

## `incident_agent`

- **Responsibility:** Extract structured incident facts and ask only safety-critical clarifications. `unknown` is not `false`.
- **Main inputs:** Normalized report, session context, existing incident row, evidence metadata.
- **Main outputs:** Structured facts, missing fields, optional clarification question, extraction confidence when honest.
- **Allowed next handoff(s):** `risk_agent` when minimum viable facts exist; otherwise reply to the worker and wait for the next Telegram turn.
- **Must not:** Compute the official risk score, invent safety procedures, notify Slack, close or reopen.

## `risk_agent`

- **Responsibility:** Interpret facts for severity/likelihood; a **deterministic Python tool** owns score, thresholds, and forced escalation.
- **Main inputs:** Incident facts, category, injury/active/exposure indicators.
- **Main outputs:** Severity, likelihood, score, base level, applied overrides, final level, human-readable explanation.
- **Allowed next handoff(s):** `guidance_agent`.
- **Must not:** Skip the risk tool, lower the tool’s `final_risk_level`, overwrite prior `risk_assessments` rows.

## `guidance_agent`

- **Responsibility:** Retrieve approved safety guidance only. Never fabricate procedures.
- **Main inputs:** Hazard category, incident facts, final risk level, location when known.
- **Main outputs:** Retrieved guidance and source metadata, or an explicit “none retrieved” fallback.
- **Allowed next handoff(s):** `coordination_agent` whether retrieval succeeded or failed.
- **Must not:** Block Critical escalation because retrieval failed; present invented steps as approved SOP.

## `coordination_agent`

- **Responsibility:** Route the incident, notify Slack, and record assignment. Notification delivered is not human acknowledgement.
- **Main inputs:** Incident, latest risk assessment, guidance summary or none, site/location, routing config.
- **Main outputs:** Destination team/channel keys, notify result, assignment record, acknowledgement and escalation state.
- **Allowed next handoff(s):** `followup_agent`.
- **Must not:** Treat Slack delivery as acknowledgement; hardcode channel ids; close the incident.

## `followup_agent`

- **Responsibility:** Drive remediation verification; close only after worker confirmation rules; reopen when the worker says the hazard remains.
- **Main inputs:** Incident state, assignment, remediation updates, evidence, original reporter, verification reply.
- **Main outputs:** Follow-up messages, verification state, lifecycle transition, close/reopen decision, escalation if unresolved.
- **Allowed next handoff(s):** `coordination_agent` on reopen; `risk_agent` if facts change risk; `incident_agent` if new report-like facts arrive.
- **Must not:** Close from `IN_PROGRESS`; treat silence or ambiguity as Yes; discard history.
