# SentinelLoop AI
### Multilingual Near-Miss and Workplace Hazard Prevention Agent
Built on [Agent Kernel](https://github.com/yaalalabs/agent-kernel) for the IDEALIZE 2026 Mini-Competition

**Report danger in seconds. Prevent the next accident.**

---

## 1. Problem Statement

Workplace accidents are rarely unannounced — exposed wiring, chemical spills, damaged machinery, and blocked exits are usually noticed before anyone gets hurt. But workers often don't report them: the process is in a language they're not comfortable writing in, the forms are slow, no one is clearly responsible for acting on the report, and near-misses in particular get ignored because "nothing actually happened." The result is that organizations keep repeating the same preventable incidents instead of learning from the warnings they already had.

SentinelLoop AI exists to close that gap: give workers a reporting method as easy as sending a WhatsApp message, in their own language, and make sure every report is actually assessed, routed to the right person, and followed through to a verified resolution — not just filed and forgotten.

## 2. Solution Overview

SentinelLoop AI is a multi-agent, multi-channel safety system built on Agent Kernel:

- **Workers** report hazards through **WhatsApp** — text, a photo, or a voice note — in **Sinhala, Tamil, or English**. A QR code at a machine or location can pre-fill where the hazard is, so the worker only has to describe what's wrong.
- **Safety officers** manage incidents through **Slack** — structured alerts with a clear risk level, an explanation of *why* that level was assigned, and one-tap accept/escalate actions.
- A pipeline of focused agents carries each report from raw message to resolved incident:

  | Agent | Responsibility |
  |---|---|
  | `intake_agent` | Language detection, translation, session continuity |
  | `incident_agent` | Extracts structured hazard details, asks for what's missing |
  | `risk_agent` | Estimates severity/likelihood; a **deterministic rule matrix** (not the LLM) makes the final Low/Medium/High/Critical call, with a plain-language explanation |
  | `guidance_agent` | Returns only pre-approved safety guidance from a knowledge base — never invents instructions |
  | `coordination_agent` | Routes the incident to the right team in Slack |
  | `followup_agent` | Tracks the incident to resolution and asks the original worker to confirm the area is actually safe before closing it |
  | `prevention_agent` | Detects recurring hazard patterns and recommends preventive inspection |

- A **deterministic emergency bypass** sits in front of all of this: a worker typing "SOS"/"🆘" (or the Sinhala/Tamil equivalents) gets an instant, hardcoded critical alert with zero LLM calls in the path — the AI is never the thing standing between a worker and help.
- Every AI call is routed through a **cost-governed OpenRouter model router**: it queries OpenRouter's live free-model list at runtime (preferring Qwen → Gemini → DeepSeek → any other free model, whichever is actually free that day), falls back to a cheap paid model only when needed, and hard-stops before exceeding a configured budget ceiling — visible live on the dashboard.
- A lightweight **dashboard** (FastAPI + a small frontend) shows open incidents as risk-tagged cards, a "Loop" radial status ring (Report → Understand → Assess → Alert → Act → Verify → Learn), recurring-hazard predictions, and a one-click **explainable audit-trail export** for any incident — the full decision trail from raw report to resolution.

This directly demonstrates Agent Kernel's multi-agent orchestration, session/memory continuity, WhatsApp and Slack integrations, and guardrail hooks — used for a real accountability workflow, not a demo shell.

**Sustainable Development Goals addressed:** SDG 3 (Good Health & Well-Being), SDG 8 (Decent Work), SDG 9 (Industry & Innovation), SDG 10 (Reduced Inequalities via multilingual/voice access), SDG 16 (accountable institutions via audit trails and anonymous reporting).

## 3. Setup Instructions

### Prerequisites
- Python 3.12+
- [uv](https://github.com/astral-sh/uv)
- Git, Make
- A Supabase account
- An OpenRouter account + API key
- WhatsApp Business Cloud API sandbox credentials
- A Slack app + bot token for a test workspace

### 3.1 Clone and install
```bash
git clone https://github.com/<your-username>/agent-kernel.git
cd agent-kernel
cd ak-py
./build.sh
```

### 3.2 Set up Supabase
1. Create a project at [supabase.com](https://supabase.com).
2. In **Project Settings → API**, copy your Project URL and `service_role` key.
3. In **Storage**, create a private bucket named `evidence`.
4. In the **SQL Editor**, run the schema in [`database/schema.sql`](./database/schema.sql) (creates `incidents`, `incident_evidence`, `risk_assessments`, `assignments`, `incident_updates`, and enables Row Level Security on all of them — access goes through the backend's service-role key only).

### 3.3 Set up OpenRouter
1. Create an account at [openrouter.ai](https://openrouter.ai) and generate an API key.
2. Add credits if you want paid-model fallback (the router works on free-tier models alone, but a small balance makes it more resilient if a free model gets rate-limited).

### 3.4 Configure environment
```bash
cd use-cases/sentinelloop_ai
cp .env.example .env
```
Fill in `.env`:
```
WHATSAPP_API_TOKEN=...
SLACK_BOT_TOKEN=...
OPENROUTER_API_KEY=...
OPENROUTER_BUDGET_CEILING_USD=2.50
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_STORAGE_BUCKET=evidence
```

### 3.5 Install dependencies
```bash
uv sync
```

## 4. How to Run the Solution

### 4.1 Start the service
```bash
uv run python -m sentinelloop_ai.main
```
This starts the WhatsApp/Slack webhook listeners and the dashboard API.

### 4.2 Seed demo data (recommended for judging)
```bash
uv run python scripts/seed_demo_data.py
```
Populates a realistic demo scenario ("Horizon Engineering Workshop") with 8–10 incidents across all risk levels, including a recurring hazard and a closed, evidence-verified case — so the dashboard and analytics are meaningful immediately without needing live WhatsApp traffic.

### 4.3 View the dashboard
```
http://localhost:8000/dashboard
```
Shows the incident list, the Loop status ring, predicted risk zones, and the model-router status/spend strip.

### 4.4 Send a live test report
Message the configured WhatsApp sandbox number, e.g.:
```
Oil spilled near packing machine number four. Workers are walking through it.
```
You should receive a clarification question (if needed) followed by immediate safety guidance, and the incident will appear in Slack and on the dashboard within seconds.

### 4.5 Run the test suite
```bash
cd ak-py
uv run pytest use-cases/sentinelloop_ai/tests/
```
All external calls (WhatsApp, Slack, OpenRouter, Supabase) are mocked, so tests run fully offline.

### 4.6 Formatting check (repo convention)
```bash
make lint-check-all
```

---

See [`AGENTS.md`](./AGENTS.md) for a per-agent breakdown and [`SPEC.md`](./SPEC.md) for the full technical specification, data model, and risk matrix.
