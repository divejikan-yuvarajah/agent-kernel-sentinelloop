# SentinelLoop AI

A multilingual workplace hazard-reporting and closed-loop safety follow-up system built as an Agent Kernel use case.

## Status

**Scaffold only — implementation pending.**

Directories, documentation, and configuration placeholders exist. Agents, tools, integrations, persistence, and the dashboard are not implemented.

## Purpose

Workers report workplace hazards in Sinhala, Tamil, or English. SentinelLoop extracts structured incident facts, scores risk with deterministic rules, retrieves approved guidance, notifies the safety team, tracks remediation, and asks the original reporter to confirm the hazard is gone before closing. If the worker says it is not fixed, the same incident reopens.

## Channels

- **WhatsApp** — worker reporting and verification
- **Slack** — safety-team alerts and operational updates

## Languages

- Sinhala
- Tamil
- English
- Reasonable mixed-language input (no language picker)

## Architecture

```text
WhatsApp integration
        ↓
      Agents
        ↓
Deterministic tools / policies
        ↓
     Supabase
        ↓
Slack coordination
```

```text
Knowledge Base
      ↓
guidance_agent
```

```text
Supabase
   ↓
Dashboard API
   ↓
Dashboard Frontend
```

- **Six agents:** intake → incident → risk → guidance → coordination → follow-up (`AGENTS.md`)
- **Agent Kernel sessions:** track where the conversation currently is (language, active incident pointer, pending question). WhatsApp session id is the sender phone number.
- **Supabase:** tracks what actually happened (five MVP tables in `database/README.md`). Session state is not the canonical incident record.
- **Guidance:** retrieval-grounded only; never fabricated when sources are missing (`knowledge_base/README.md`)
- **Dashboard:** separate read/operations layer; do not couple the frontend to agent internals

Demo path (not implemented yet):

```text
Worker scans QR
        ↓
WhatsApp report
        ↓
intake_agent → incident_agent → risk_agent → guidance_agent → coordination_agent
        ↓
Slack safety alert
        ↓
remediation update → followup_agent → worker verification
        ↓
closed / reopened
```

Possible QR demo: a code in `assets/qr/` later opens the WhatsApp reporting conversation. No QR assets are generated in this scaffold.

## Repository Layout

```text
use-cases/sentinelloop-ai/
├── SPEC.md                 # Product / business contract
├── AGENTS.md               # Six-agent map
├── README.md
├── agents/                 # Agent module placeholders
├── tools/                  # Deterministic tools / policies
├── integrations/           # WhatsApp, Slack, Supabase, OpenRouter boundaries
├── guardrails/             # Hooks / safety / budget placeholders
├── knowledge_base/         # Approved guidance corpus (empty)
├── database/               # Durable model / repository placeholders
├── dashboard/              # Operations UI (api.py + frontend/)
├── scripts/                # Future operational scripts
├── assets/qr/              # Future WhatsApp QR assets
├── tests/                  # Placeholder test modules
├── config.yaml             # Agent Kernel + application policy scaffold
├── pyproject.toml          # Isolated uv project
├── build.sh
├── .env.example
└── .python-version
```

## Source of Truth

- [`SPEC.md`](SPEC.md) defines product and business behavior
- [`AGENTS.md`](AGENTS.md) summarizes agent ownership and handoffs
- [`knowledge_base/README.md`](knowledge_base/README.md) describes retrieval-only guidance
- [`database/README.md`](database/README.md) describes the five MVP tables
- Repository root `api-notes.md` documents verified Agent Kernel APIs during development (investigation notes, not a submission artifact)
- Real repository conventions override guessed APIs

Deterministic application code will own numerical risk, threshold mapping, forced escalation, lifecycle validation, webhook idempotency, and persistence correctness. Models may interpret language; they must not replace those policies.

## Development

This use case is its **own uv project** (same pattern as `use-cases/waste-sorting-assistant`). Do not `uv add` SentinelLoop dependencies from `ak-py/`. Do not use a manual `requirements.txt`.

Python 3.12–3.13.x.

```bash
chmod +x build.sh
./build.sh
```

`build.sh` runs `uv venv` and `uv sync --all-extras --dev`. Do not run it until an implementation prompt is ready to install dependencies.

Verified Agent Kernel extras for this use case (declared in `pyproject.toml`, not yet used in code): `cli`, `api`, `openai`, `whatsapp`, `slack`. Local CLI and REST entry points (`demo.py`, `server.py`) will be added in a later implementation phase.

On Windows PowerShell, equivalent: `uv venv` then `uv sync --all-extras --dev` from this directory.

Local unpublished kernel (from this folder), when needed later:

```bash
./build.sh local
```

(`build.sh local` is used by other examples against `ak-py/dist`; add it when implementation starts if the waste-sorting script is extended.)

## Configuration

Copy [`.env.example`](.env.example) to `.env` (gitignored). Never commit tokens or service-role keys.

Agent Kernel loads `config.yaml` plus environment variables prefixed `AK_` with nested `__` (for example `AK_WHATSAPP__ACCESS_TOKEN`). Slack Bolt uses `SLACK_BOT_TOKEN` and `SLACK_SIGNING_SECRET`. SentinelLoop model calls go through `tools.model_router.call_model` (OpenRouter). Agents must not call the provider directly. `OPENROUTER_BUDGET_CEILING_USD` is enforced by the router; Critical reports must never silently disappear if a budget ceiling is hit.

`SPEC.md` remains the authoritative risk and lifecycle definition. Values under `risk:` in `config.yaml` are documentation for later wiring, not a second rule engine.

## Implementation Status

| Component | Status |
| --- | --- |
| `SPEC.md` | Written |
| Agent modules | Scaffolded — not implemented |
| Tools / policies | Model router implemented; other tools still scaffolded |
| WhatsApp / Slack / Supabase / OpenRouter | OpenRouter `call_model` gateway implemented; channels still scaffolded |
| Guardrails / hooks | Budget policy documented via router; other hooks scaffolded |
| Knowledge base corpus | Placeholder only |
| Database schema / client | Scaffolded — not implemented |
| Dashboard API / frontend | Scaffolded — not implemented |
| Tests | Database + model-router unit tests (mocked HTTP) |
| REST / CLI entry points | Not created yet |
