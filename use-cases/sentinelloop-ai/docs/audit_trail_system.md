# Incident audit trail

SentinelLoop stores what happened. The audit export explains **why** it happened — without re-running agents or changing the incident.

```text
Worker report
        ↓
AI understanding (language + extraction)
        ↓
Risk reasoning (model estimate, then deterministic rules)
        ↓
Grounded safety guidance
        ↓
Human action (Slack / assignment)
        ↓
Verified resolution
```

That chain is the product claim: this is not a black-box classifier. An inspector can open one incident and read the same facts the system used.

## Endpoint

`GET /api/incidents/{id}/audit-export`

`{id}` may be `incident_ref` (for example `SL-2026-000088`) or the row UUID. Missing records return `404` with `{"detail":"incident not found"}`. POST/PUT/PATCH/DELETE are rejected (`405`, dashboard is read-only).

The dashboard UI calls this path through the Vite `/api` proxy. Page routes such as `/incidents/:id` remain the React workspace.

## JSON structure

Top-level keys are always present:

| Section | What it proves |
| --- | --- |
| `incident_information` | Identity, status, risk, duplicate count, equipment |
| `original_report` | Exact worker message, channel, masked reporter id |
| `language_processing` | Detected language, original text, translated text |
| `extracted_information` | Intake fields as `{field, value, confidence}` |
| `ai_decision` | Model severity/likelihood/confidence and reasoning |
| `risk_analysis` | Deterministic `calculate_risk` restatement (score, factors, explanation) |
| `guidance_history` | Worker guidance plus knowledge-base source/section/id |
| `coordination_history` | Slack / officer alerts |
| `assignment_history` | Officer changes, previous officer, time |
| `incident_timeline` | Every `incident_updates` row, oldest → newest |
| `resolution` | Close/verify message, actor, evidence URLs |
| `audit_metadata` | Version, models, call count, estimated cost, `audit_hash` |

AI judgement and rule validation are separate objects on purpose. The model may estimate severity; the Python risk engine owns the official score.

## What is not included

- API keys, tokens, environment variables, system prompts
- Unmasked phone numbers (reporter ids are masked; message text is phone-redacted)
- Live Graph/Telegram media URLs

## Integrity and versioning

- `audit_export_version` is `1.0`
- `audit_hash` is SHA-256 of the canonical JSON with `audit_hash` omitted
- Changing a timeline row changes the hash on the next export
- Human overrides appear when the stored incident risk differs from the latest assessment, or when an update records `override_reason`

## Inspector / demo flow

1. Open a critical incident in the command center.
2. Click **Export audit trail**.
3. Wait for **Generating audit trail...** then **Audit generated successfully**.
4. Walk the preview: report → translation → extraction → AI risk → rule confirmation → guidance source → officer action → resolution evidence.
5. Download `SentinelLoop_Audit_<incident_id>.json`.

The packet is intended for workplace safety audits, incident investigations, and regulatory reviews. It is assembled only from already-persisted repository rows, update metadata, evidence URLs, and the spend ledger — never from a new model call.
