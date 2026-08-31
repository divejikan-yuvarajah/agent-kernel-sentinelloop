# Agent Kernel API Notes — SentinelLoop Reconnaissance

Investigation-only. **Not part of the competition submission.** Do not commit unless explicitly asked.

Evidence is from this checkout. Prefer implementation over docs when they disagree.

---

## 1. Repository Layout

Canonical root: this clone of `yaalalabs/agent-kernel`.

| Path | Role |
| --- | --- |
| `ak-py/` | Python package `agentkernel` (authoritative runtime) |
| `ak-py/pyproject.toml` | Package manifest, extras, versions (`agentkernel` **0.6.0**) |
| `ak-py/uv.lock` | Lockfile for the **library** only |
| `ak-py/src/agentkernel/` | Importable package |
| `ak-py/tests/` | Library unit tests |
| `examples/` | Isolated demo projects, each with its own `pyproject.toml` |
| `use-cases/` | End-to-end agents built from `SPEC.md` |
| `.agents/skills/` | **Developer** skills (`ak-dev-*`) for contributing to the kernel |
| `ak-py/src/agentkernel/skills/` | **User** skills (`ak-init`, `ak-build`, …) shipped in the package |
| `ak-deployment/` | Terraform modules |
| `docs/` | Docusaurus site |
| `DEVELOPER_GUIDE.md`, `CODE_OF_CONDUCT.md`, `README.md` | Root docs |
| `Makefile` | `black`/`isort` for `ak-py` and `examples/` |
| `.github/workflows/code-quality.yml` | PR lint: `make lint-check-all` |
| `agent/` | Separate sample app at repo root; **not** the use-case directory |

There is **no** root `uv` workspace that includes use cases. There is **no** `.pre-commit-config.yaml`. There is **no** `ruff` config.

---

## 2. Canonical Use-Case Directory

**Canonical path: `use-cases/` (hyphen).**

**`use_cases/` (underscore) does not exist in this clone.**

Evidence:

- `DEVELOPER_GUIDE.md` Additional Resources links to `use-cases/`
- Directory listing: `use-cases/README.md`, `use-cases/waste-sorting-assistant/`, `use-cases/sentinelloop-ai/SPEC.md`
- Glob for `use_cases/**` returned zero files

Later prompts that say `use_cases/sentinelloop-ai` must be translated to `use-cases/sentinelloop-ai`.

---

## 3. `ak-py` Module Structure

Compact tree of **relevant** modules (`ak-py/src/agentkernel/`):

```
agentkernel/
├── __init__.py
├── openai.py          # public alias → framework.openai
├── slack.py           # public alias → integration.slack
├── whatsapp.py        # public alias → integration.whatsapp
├── aws.py / azure.py / gcp.py
├── cli/cli.py         # CLI.main()
├── api/
│   ├── http.py        # RESTAPI (FastAPI + uvicorn)
│   ├── handler.py     # AgentRESTRequestHandler (/api/v1/chat)
│   ├── a2a/  mcp/
├── core/
│   ├── base.py        # Session, Agent, Runner
│   ├── module.py      # Module.load → Runtime.register
│   ├── runtime.py     # Runtime.run / stream, hook order
│   ├── service.py     # AgentService.select/run
│   ├── chat_service.py
│   ├── config.py      # AKConfig
│   ├── model.py       # AgentRequest*/AgentReply*, BaseRunRequest
│   ├── tool.py        # ToolContext, ToolBuilder
│   ├── hooks.py       # PreHook, PostHook
│   ├── builder.py     # SessionStoreBuilder
│   ├── session/       # in_memory, redis, dynamodb, cosmosdb, firestore
│   └── multimodal/    # PreHook + AnalyzeAttachmentsTool + stores
├── framework/openai/openai.py   # OpenAIModule, OpenAIRunner, OpenAIToolBuilder
├── integration/whatsapp/whatsapp_chat.py
├── integration/slack/slack_chat.py
├── knowledgebase/     # KnowledgeBuilder, chroma, neo4j, starburst
├── guardrail/
├── trace/             # langfuse, openllmetry
├── test/test.py       # agentkernel.test.Test
└── skills/            # user skills pack
```

---

## 4. Agent API

Agents are **not** an Agent Kernel class you construct for OpenAI. You construct **OpenAI Agents SDK** `agents.Agent`, then wrap/register via `OpenAIModule`.

**Public imports (real):**

```python
from agents import Agent
from agentkernel.openai import OpenAIModule, OpenAIToolBuilder
from agentkernel.cli import CLI
from agentkernel.api import RESTAPI
```

`agentkernel.core.base.Agent` is the **wrapper** created by `OpenAIModule._wrap` (`OpenAIAgent`). Application code usually never subclasses it.

**SDK `Agent` (used everywhere in examples):**

- Required in practice: `name`, `instructions`
- Optional used in-repo: `handoff_description`, `handoffs=[...]`, `tools=...`, `model="gpt-4o-mini"` (knowledge-base demo)
- **Not found** in this repo’s examples: Agent Kernel `session=` on the constructor, `pre_hooks=` on the SDK Agent, `output_type=` structured output

**Registration:** `OpenAIModule([triage_agent, math_agent, ...])` wraps each native agent and `Runtime.current().register(...)`. One Module per process; adding agents means extending that list (`ak-build` skill).

**Execution:**

- CLI: `CLI.main()` → `AgentService.select()` (first agent if unnamed) → `AgentService.run(prompt)`
- REST: `RESTAPI.run()` → `POST /api/v1/chat` with `{prompt, agent, session_id}`
- Programmatic: `await Runtime.current().run(agent, session, [AgentRequestText(text=...)])` (async)

**Streaming:** `OpenAIRunner.stream` + `Runtime.stream` exist (`ak-py/src/agentkernel/framework/openai/openai.py` ~192–217). REST streaming when `execution.mode=stream`.

**Minimal real example** (`examples/cli/openai/demo.py` is slightly larger; smallest REST agent is `examples/api/multimodal/openai/app.py` pattern):

```python
from agents import Agent
from agentkernel.cli import CLI
from agentkernel.openai import OpenAIModule

agent = Agent(name="general", instructions="You are a helpful assistant.")
OpenAIModule([agent])

if __name__ == "__main__":
    CLI.main()
```

That is the smallest correct Agent Kernel OpenAI agent in this repository.

---

## 5. Multi-Agent / Handoff API

**Assumption “OpenAI Agents SDK-style handoffs” is valid.**

Mechanism: SDK-native `handoffs=[other_agent, ...]` on `agents.Agent`. Agent Kernel does not implement a separate handoff graph. `OpenAIRunner.run` calls `Runner.run(agent.agent, input_data, session=openai_session)` (`openai.py` ~182). Intra-run routing is the SDK.

**Session survival:** framework conversation items live in `OpenAISession` stored on the AK `Session` under key `"openai"` (`OpenAIRunner._session`, `openai.py` 86–94). Durable only if `session.type` is redis/dynamodb/etc.

**Restriction (critical):** `PreHook`/`PostHook` run only on the **initial** user invocation. They do **not** wrap agent-to-agent handoffs inside the SDK run.

Evidence: `ak-py/src/agentkernel/core/hooks.py` lines 12–15:

> Currently, they will get only called for the initial execution of an agent when a user prompt is provided. It's unable to hook into agent-to-agent calls within a workflow.

Canonical pattern: `examples/cli/openai/demo.py` (`triage_agent` with `handoffs=[general_agent, math_agent, weather_agent]`).

CrewAI/LangGraph/ADK/Smolagents have different routing; SentinelLoop should stay on OpenAI SDK handoffs.

---

## 6. Tool API

**Canonical (skills + waste-sorting + CLI openai):**

```python
from agentkernel.core import ToolContext
from agentkernel.openai import OpenAIToolBuilder

def lookup_x(item: str) -> str:
    """Docstring becomes the tool description for the LLM."""
    session = ToolContext.get().session
    return "..."

tools = OpenAIToolBuilder.bind([lookup_x])
agent = Agent(name="...", instructions="...", tools=tools)
```

`OpenAIToolBuilder.bind` wraps each callable with SDK `function_tool` (`openai.py` 344–366).

**Alternate (also in-repo):** `examples/api/openai/tool.py` uses `@function_tool` from `agents` and passes `tools=[fetch_customer_activity]` without `OpenAIToolBuilder`. Both work; prefer `OpenAIToolBuilder.bind` for SentinelLoop consistency with `ak-build`.

**Context access:** `ToolContext.get()` (raises `RuntimeError` if called outside `Runtime.run`). Provides `runtime`, `agent`, `session`, `requests`. Do **not** pass context as a function parameter.

**Safe from tools:** session `nv_cache` / `v_cache`, `session.id`. Database clients, Slack/WhatsApp HTTP clients, KB backends: **application code inside the tool** — no DI container.

**Retries:** **Not found** as a ToolBuilder/runtime feature. Tool errors surface to the SDK/runner. OpenAI runner catches exceptions and returns `user_facing_error_message(e)` (`openai.py` 186–187) — the user sees an error string; there is no automatic Slack retry.

---

## 7. Sessions and Memory

| Concept | In this repo |
| --- | --- |
| Session | `agentkernel.core.base.Session` — id + key-value `_data` + two caches |
| Thread | **Not a first-class AK type.** Slack uses `thread_ts` **as** `session_id` |
| Conversation history | OpenAI: `OpenAISession._items` on `session.get("openai")`; SDK session protocol |
| Memory | Informal: `nv_cache` + framework session items |
| Durable incident DB | **Not provided.** App-level (e.g. Supabase) |

**Create:** `runtime.sessions().new(session_id)` or `AgentService.select(session_id=None)` → UUID via `new()`.

**Load:** `AgentService.select(session_id=..., name=...)` → `sessions().load(session_id)`. Missing IDs create a new session unless `strict=True` (`in_memory.py` `load`).

**Who owns lifecycle:** `AgentService` + `Runtime.run` (`async with session`, then `sessions().store(session)`, then clear `v_cache`).

**WhatsApp session id:** phone `from` number (`whatsapp_chat.py` 276–277). Continuity = same sender.

**Slack session id:** `thread_ts` or `ts` (`slack_chat.py` 70–71, 125). Continuity = Slack thread, not user id.

**History injection:** OpenAI text-only path passes `session=OpenAISession` into `Runner.run`. Multimodal path currently passes `session_to_use=None` (`openai.py` 160–163) — follow-up that needs re-analysis of images is a **documented Slack limitation**.

**Arbitrary state:** `session.get_non_volatile_cache().set/get` (`KeyValueCache`). Must be JSON-serializable. Survives restarts only if session store is redis/dynamodb/cosmosdb/firestore.

**Built-in stores:** `in_memory` (default), `redis`, `dynamodb`, `cosmosdb`, `firestore`. **No SQLite. No PostgreSQL. No Supabase session adapter.**

**SentinelLoop split:** AK session = conversation cursor (language, active incident id pointer, pending question). Supabase = canonical incidents. Do not put incident records only in `nv_cache`.

---

## 8. Hooks / Guardrails

**Exact API:**

```python
class MyPre(PreHook):
    async def on_run(self, session, agent, requests) -> list[AgentRequest] | AgentReply: ...
    def name(self) -> str: ...

class MyPost(PostHook):
    async def on_run(self, session, requests, agent, agent_reply) -> AgentReply: ...
    def name(self) -> str: ...

module = OpenAIModule([agent])
module.pre_hook(agent, [MyPre()])   # native SDK Agent instance
module.post_hook(agent, [MyPost()])
```

Evidence: `OpenAIModule.pre_hook` / `post_hook` (`openai.py` 323–341); `Runtime._prepare_requests` / `run` (`runtime.py` 129–198).

**Order:**

- Pre: **agent hooks first**, then **system** hooks (`InputGuardrailFactory`, `MultimodalPreHookFactory`) last (`runtime.py` 145)
- Post: **system first** (`OutputGuardrailFactory`), then agent hooks (`runtime.py` 190)

**Halt:** PreHook returning `AgentReplyText` / `AgentReplyImage` skips the runner.

**Mutate:** Pre can replace `requests`; Post must return `AgentReply`.

**Scope:** initial user turn only — **not** inner handoffs (hooks.py).

**System guardrails:** config `guardrail.input/output` types `openai` | `bedrock` | `walledai`. Separate from custom Pre/Post.

**SentinelLoop mapping:**

| Guardrail idea | Fit |
| --- | --- |
| Sanitize WhatsApp/Slack input | Custom PreHook **or** subclass handler (example: `example_custom_handler.py`) |
| Idempotency | **Not a hook feature** — app store of message IDs (handler currently has none) |
| Deterministic risk overrides | **Python function tool**, optionally re-check in PostHook on **final** text only (cannot intercept inner `risk_agent` handoff) |
| Invalid lifecycle | App persistence layer, not AK hooks |
| Audit | PostHook can log; durable audit is app DB |

---

## 9. Structured Output

**No Agent Kernel structured-output API** was found (no `output_type=` usage, no AK parser/retry loop).

Repo uses Pydantic for **config and request models** (`AKConfig`, `AgentRequestText`, `BaseRunRequest`), not for forcing LLM JSON schemas.

**Requires application-level implementation:** tools returning `json.dumps(...)`, post-parse, or SDK `output_type` if you adopt it (unverified in this checkout’s examples). `OpenAIRunner` does `str(reply.final_output)` (`openai.py` 182–185).

---

## 10. WhatsApp Integration

**Module:** `ak-py/src/agentkernel/integration/whatsapp/whatsapp_chat.py`  
**Public import:** `from agentkernel.whatsapp import AgentWhatsAppRequestHandler`

**Not** a generic `WhatsAppIntegration` class. Cloud API via `httpx` to `https://graph.facebook.com/{api_version}`.

**Constructor:** `AgentWhatsAppRequestHandler()` — no args. Reads `AKConfig.whatsapp`. Raises `ValueError` if `access_token`, `phone_number_id`, or `verify_token` missing (`whatsapp_chat.py` 41–43).

**Config keys / env (prefix `AK_`, nested `__`):**

| YAML | Env |
| --- | --- |
| `whatsapp.agent` | `AK_WHATSAPP__AGENT` |
| `whatsapp.agent_acknowledgement` | `AK_WHATSAPP__AGENT_ACKNOWLEDGEMENT` |
| `whatsapp.verify_token` | `AK_WHATSAPP__VERIFY_TOKEN` |
| `whatsapp.access_token` | `AK_WHATSAPP__ACCESS_TOKEN` |
| `whatsapp.app_secret` | `AK_WHATSAPP__APP_SECRET` |
| `whatsapp.phone_number_id` | `AK_WHATSAPP__PHONE_NUMBER_ID` |
| `whatsapp.api_version` | `AK_WHATSAPP__API_VERSION` (default `v24.0`) |

Also `OPENAI_API_KEY` for the model.

**Routes (auto-mounted via `RESTAPI.run([handler])`):**

- `GET /health`
- `GET /whatsapp/webhook` — hub challenge verification
- `POST /whatsapp/webhook`

**Inbound:**

| Type | Behavior |
| --- | --- |
| `text` | body → `AgentRequestText` |
| `interactive` button/list | title → text |
| `image` | download media → `AgentRequestImage` (base64) + caption/placeholder text |
| `document` | `AgentRequestFile` |
| `audio` / `video` | **Rejected:** “Sorry, audio and video messages are not supported yet.” (`whatsapp_chat.py` 264–267) |

Sender: `message["from"]`. Message id: `message["id"]` (used as reply context, **not** persisted for idempotency).

**Outbound:** private `async def _send_message(self, to_number, text, reply_to_message_id=None)` — Graph `POST /{phone_number_id}/messages`, type `text`, splits at 4096 chars. **No public media-send API.** No public `send_message` for tools.

**Security:** optional HMAC `x-hub-signature-256` if `app_secret` set. GET verify_token check. **No idempotency store. No retries.** Handler **always HTTP 200** even after processing exceptions (`whatsapp_chat.py` 125–128) to avoid Meta retries — failed processing can be silently dropped.

**Minimal real server:** `examples/api/whatsapp/server.py`.

**Custom outbound / commands:** subclass and call `self._send_message` (`examples/api/whatsapp/example_custom_handler.py`).

---

## 11. Slack Integration

**Module:** `ak-py/src/agentkernel/integration/slack/slack_chat.py`  
**Public import:** `from agentkernel.slack import AgentSlackRequestHandler`

Uses **slack-bolt** `AsyncApp()` (tokens from env, not AKConfig) + FastAPI adapter.

**Env (Bolt, not `AK_` prefix):**

```
SLACK_BOT_TOKEN
SLACK_SIGNING_SECRET
```

**AKConfig:** `slack.agent`, `slack.agent_acknowledgement` only.

**Route:** `POST /slack/events` (+ handler `GET /health`). Challenge handled by Bolt.

**Inbound:** `@slack_app.event("message")` only. **Not found:** slash commands, block_actions / button handlers, interactive component routing. README lists subscribe to `message.im`, `message.channels`, `app_mention` and scopes `chat:write`, `im:write`, `files:read`, `app_mentions:read`.

**Session:** `session_id=thread_ts`. Channel from event. Bot ignores its own `user_id`.

**Outbound in handler:** Bolt `say(...)` with markdown **blocks** (3000-char chunks, max 5). Updates ack message via `chat_update`. **Not a reusable “notify this channel from a tool” API.**

**Proactive safety-channel alerts (SentinelLoop coordination_agent):** **Requires application-level `slack_sdk`/`httpx` in a tool.** Do not invent `AgentSlackRequestHandler.send_alert(...)`.

**Routing:** config `slack.agent` selects which **AK agent** handles inbound Slack chat. Channel routing of incidents is **not** integration-driven.

**Ack vs assignment:** handler can post an acknowledgement string; it does **not** model incident acknowledgement/assignment.

**Minimal real server:** `examples/api/slack/server.py`.

---

## 12. REST / Webhook Runtime

**Stack:** FastAPI + uvicorn (`RESTAPI.run`, `ak-py/src/agentkernel/api/http.py`).

```python
RESTAPI.run()  # default AgentRESTRequestHandler
RESTAPI.run([AgentWhatsAppRequestHandler(), AgentSlackRequestHandler()])
RESTAPI.add(custom_router)  # mounted under api.custom_router_prefix default /custom
```

**Default chat API:** `POST /api/v1/chat` body `BaseRunRequest`: `prompt`, optional `agent`, `session_id`, `files`, `images`. Also `POST /api/v1/chat-multipart`, `GET /api/v1/agents`, global `GET /health`. Host/port: `AKConfig.api` default `0.0.0.0:8000`.

WhatsApp/Slack **create their own routes** when their handlers are passed in. You do not manually register `/whatsapp/webhook` unless subclassing.

Auth: optional `RESTAPI.add_auth_handlers([AuthValidator])` — Bearer header. Not used by WhatsApp (uses signature) or Slack (Bolt signing secret).

---

## 13. Multimodal Support

| Input | Request class | Notes |
| --- | --- | --- |
| Text | `AgentRequestText` | Always |
| Image | `AgentRequestImage` | base64 or URL; mime_type required for raw base64 |
| File | `AgentRequestFile` | base64 or URL |
| Other | `AgentRequestAny` | **PreHooks only**, stripped from runner (`AgentRequestAny` skipped in OpenAI `_process_requests`) |
| Audio | — | **Not found** as `AgentRequestAudio`. WhatsApp/Slack reject audio/video |

When `multimodal.enabled: true`, `MultimodalPreHook` describes attachments via **LiteLLM** and stores binaries outside conversation history; agents get `analyze_attachments` system tool.

**Speech-to-text / Whisper / transcription: Not found in current repository inspection.** Voice notes require **application-level** STT before intake.

**Packaging discrepancy:** `examples/api/multimodal/openai/pyproject.toml` depends on `agentkernel[api,openai,multimodal]` but **`ak-py/pyproject.toml` has no `[multimodal]` extra**. LiteLLM is **not** in the `openai` extra; it appears under `langgraph`, `adk`, and `test`. Plan to depend on `litellm` explicitly if enabling vision hooks.

---

## 14. Configuration / Secrets

**Pattern:** Pydantic settings `AKConfig` (`core/config.py`) + `YamlBaseSettingsModified`.

**Sources (implementation order in `settings_customise_sources`, `config_yaml_util.py` 155–160):** init → **environment** → dotenv `.env` → **YAML** (`AK_CONFIG_PATH_OVERRIDE` or `config.yaml`) → file secrets.

Docstring in the same file (lines 115–123) lists YAML above env; **implementation prefers env over YAML**. Follow implementation.

- Prefix: `AK_`
- Nested delimiter: `__`
- Secrets-in-YAML: `<file:relative-path>` with `AK_SECRETS_PATH`
- Provider keys **outside** AK prefix: `OPENAI_API_KEY`, `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, Langfuse keys, etc.

**Do not copy secret values.** None were recorded.

---

## 15. Error Handling / Retry Pattern

- OpenAI runner: catch-all → `user_facing_error_message` (`core/util/error_util.py`) categories: rate_limit, server, connection, auth, not_found, unknown. **No retry/backoff in runner.**
- WhatsApp webhook: log + still `{"status":"ok"}`; per-message errors send a sorry text.
- Slack: `SlackApiError` logged; generic “Error handling your request.”
- Tools: no AK retry wrapper. Failed tools must return explicit error strings if SentinelLoop must not fake success.
- Queue/Lambda path has `max_receive_count` — irrelevant to REST WhatsApp/Slack MVP.

**Exception classes:** no dedicated `WhatsAppError` hierarchy. Use `httpx.HTTPStatusError`, `SlackApiError`, `ValueError` (incomplete WhatsApp config), `RuntimeError` (ToolContext).

---

## 16. Logging / Tracing

- Loggers: `logging.getLogger("ak....")` e.g. `ak.api.whatsapp`, `ak.runtime`. Config `logging.ak.level` / `logging.system.level`.
- Tracing: `trace.enabled` + `trace.type`: `langfuse` | `openllmetry`. Framework Module swaps in a traced Runner (`OpenAIModule` `openai.py` 299–300). Extra: `agentkernel[langfuse]` or `[openllmetry]`.
- **No first-class correlation-ID field** on Session. App must thread incident/session ids in logs.
- Token usage: SDK/trace backends, not AK Session.

---

## 17. Dependency / `uv` Model

**Model B: each use case / example has its own `pyproject.toml` and `uv.lock`.**

**Not Model A.** You do **not** `uv add supabase` inside `ak-py/` for SentinelLoop.

Evidence:

- `use-cases/waste-sorting-assistant/pyproject.toml` — `agentkernel[cli,openai,aws]>=0.6.0`, `[tool.uv] package = false`
- Every `examples/**/pyproject.toml` is isolated
- `ak-py/pyproject.toml` is the **library** (`[tool.uv] package = true`)
- No root workspace `pyproject.toml` listing use cases

**Commands (real):**

```bash
# library
cd ak-py && ./build.sh
cd ak-py && uv run pytest

# a use case / example
cd use-cases/<name>   # or examples/...
./build.sh            # uv venv && uv sync
uv run python demo.py
# or
uv run python server.py
uv run pytest

# local unpublished kernel
./build.sh local      # --find-links ../../../ak-py/dist
```

Python: `requires-python = ">=3.12,<3.14"` (library); examples `>=3.12`. `use-cases/README.md`: 3.12–3.13.x.

---

## 18. Package / Import Conventions

Use cases import **installed** `agentkernel`, not `ak-py` paths.

```python
from agentkernel.openai import OpenAIModule, OpenAIToolBuilder
from agentkernel.api import RESTAPI
from agentkernel.whatsapp import AgentWhatsAppRequestHandler
from agentkernel.slack import AgentSlackRequestHandler
from agentkernel.core import ToolContext, PreHook, PostHook
from agentkernel.cli import CLI
from agents import Agent  # OpenAI Agents SDK
```

`from agentkernel.core.config import AKConfig` or `from agentkernel.core import Config` (alias).

No `PYTHONPATH=ak-py/src` in the official examples. Local app modules use relative imports (`from agent import AGENTS`, `from tool import ...`).

`[tool.uv] package = false` — use cases are **not** installable packages.

---

## 19. Testing Conventions

| Location | Pattern |
| --- | --- |
| `ak-py/tests/` | `test_*.py`, pytest, `@pytest.mark.asyncio`, DummyAgent/DummyRunner, monkeypatch `AKConfig` |
| Examples | `demo_test.py` / `server_test.py` / `app_test.py` using `from agentkernel.test import Test` |
| Waste-sorting | **No test file** in tree |

CLI tests spawn the entry file via `Test("demo.py")`. Config `test.mode`: `fuzzy` \| `judge` \| `fallback`.

```bash
cd ak-py && uv run pytest
cd examples/cli/openai && uv run pytest -s
```

Do not hit live WhatsApp/Slack in unit tests; mock `httpx` / Bolt. Waste-sorting has no tests to copy.

---

## 20. Lint / Format / Type Checks

| Tool | Use |
| --- | --- |
| black | **Yes** — 150 chars `ak-py`, 120 examples/use-cases |
| isort | **Yes** — profile black |
| mypy | Configured in pyproject; `DEVELOPER_GUIDE` / skills mention `uv run mypy src/` — CI **code-quality.yml only runs** `make lint-check-all` |
| ruff | **Not found** |
| pre-commit | **Not found** |

```bash
make lint-check-all
make lint-all
```

---

## 21. Use-Case Reference

Inspected: `use-cases/waste-sorting-assistant/` (complete example). `use-cases/sentinelloop-ai/` currently has **only** `SPEC.md`.

```
use-cases/waste-sorting-assistant/
├── SPEC.md
├── README.md
├── agent.py          # agents.Agent + OpenAIToolBuilder.bind
├── tool.py           # ToolContext + nv_cache
├── demo.py           # OpenAIModule + CLI.main()
├── lambda.py         # OpenAIModule + Lambda.handler
├── config.yaml       # session.type in_memory
├── pyproject.toml    # own uv env
├── build.sh
└── deploy/           # Terraform AWS serverless
```

**Runtime flow (CLI):** `uv run python demo.py` → import registers `OpenAIModule(AGENTS)` → `CLI.main()` → `AgentService.select()` (first agent `waste_sorting_advisor`) → `run(prompt)` → `Runtime.run` → prehooks → `OpenAIRunner` → SDK → tools (`lookup_disposal_category` etc. via `ToolContext`) write `nv_cache` → posthooks → `SessionStore.store` → print reply.

**Lambda:** same agents, `handler = Lambda.handler`, HTTP `{prompt, session_id, agent}`.

**No WhatsApp/Slack in this use case.**

---

## 22. Expected `SPEC.md` Structure

**Documented required structure (`use-cases/README.md` §2):** free-form Markdown describing purpose, tools, memory, local run, deployment, folder/file needs. **Not** machine-parsed. **No** YAML frontmatter. **No** codegen compiler.

**Pattern seen (waste-sorting `SPEC.md` only other complete spec besides SentinelLoop):**

```
# <Name> Specification
## Agent Description
## Functional Requirements
## Local Development
## Deployment
```

**Inference (not a repo rule):** those four H2s are the template to copy; extra requirements go in those sections as bullets.

**Skills:** no skill “reads SPEC.md” as a formal schema. A **coding agent** is told to read SPEC and apply `ak-init` / `ak-build` / … (`use-cases/README.md` §4–5). Generated files are **not** marked; they are normal source.

---

## 23. Agent Kernel Skills Workflow

**Developer skills** (this repo root `.agents/skills/`): architecture, new adapters, testing, docs sync — **not** for scaffolding SentinelLoop.

**User skills** (package `ak-py/src/agentkernel/skills/`): `ak-init`, `ak-build`, `ak-add-capabilities`, `ak-add-integration`, `ak-cloud-deploy`, `ak-test`.

**Documented sequence (`use-cases/README.md`):**

1. Create folder under `use-cases/`
2. Write `SPEC.md`
3. `ak skill install --assistant cursor` **inside that folder** (copies user skills to assistant dir, e.g. Cursor `.cursor/rules/`)
4. Prompt: read SPEC.md and build using the skills pack
5. Iterate with ak-build / capabilities / integrations / deploy / test

Opening the **use-case folder** as workspace root is recommended so nested skills auto-apply.

There is **no** `ak generate-from-spec` CLI.

---

## 24. Generated vs Handwritten Files

| Kind | Ownership |
| --- | --- |
| `SPEC.md` | Handwritten, source of truth for the coding agent |
| `agent.py`, `tool.py`, `demo.py`/`server.py`, `config.yaml`, `pyproject.toml` | Skill-generated **once**, then edited by hand; **no regen marker** |
| `uv.lock` | Generated by `uv sync`; waste-sorting commits it |
| `requirements*.txt`, `dist/` | Generated at package time; gitignored in waste-sorting |
| Installed skills `.agents/skills/` / `.cursor/` **inside use case** | gitignored in waste-sorting |

**Warning:** nothing overwrites on `ak skill update` except the **skill markdown**, not your Python. There is no “generated/” tree.

---

## 25. Versions / Compatibility Notes

From `ak-py/pyproject.toml` (package **0.6.0**):

| Component | Constraint |
| --- | --- |
| Python | `>=3.12,<3.14` |
| pydantic | `>=2.11.7` |
| pydantic-settings | `>=2.10.1` |
| openai-agents | `>=0.6.5` (`openai` extra) |
| fastapi | `>=0.118.0` (`api` extra) |
| uvicorn | `>=0.37.0` |
| slack-bolt | `==1.22.0` (`slack` extra) |
| WhatsApp client | `httpx>=0.27.0` only (`whatsapp` extra) — no official WhatsApp SDK |
| chromadb | `>=0.4.0` (`chromadb` extra) |
| redis | `>=7.1.0` |
| pytest | `>=8.4.1` (`test` extra) |

Use-case `pyproject` pins `agentkernel[...]>=0.6.0` from PyPI unless `./build.sh local`.

---

## 26. SentinelLoop Compatibility Matrix

| SentinelLoop Requirement | Native Agent Kernel Support | Existing Example | Additional App Code Needed | Notes |
| ------------------------ | --------------------------- | ---------------- | -------------------------- | ----- |
| Multi-agent pipeline | Yes | `examples/cli/openai` | Wiring + prompts | `OpenAIModule([...])` |
| Agent handoffs | Yes | same | Handoff lists + triage instructions | SDK `handoffs=` |
| Sessions | Yes | CLI/API/WhatsApp | Choose store | WhatsApp uses phone as id |
| Conversation memory | Partial | OpenAISession | Don’t use as incident DB | Multimodal may drop SDK session |
| Pre-execution hooks | Yes | `examples/api/hooks`, `examples/api/openai` | Custom PreHook classes | **Not** inner handoffs |
| Post-execution hooks | Yes | hooks example | Custom PostHook | Final reply only |
| Structured output | No | — | Yes | Parse JSON / tools / unverified SDK `output_type` |
| WhatsApp text | Yes | `examples/api/whatsapp` | Config + Meta app | Cloud API webhook |
| WhatsApp image | Yes | same | Enable multimodal if desired | Downloaded to `AgentRequestImage` |
| WhatsApp voice | No | — | Yes (STT) | Explicitly unsupported |
| Slack outbound alerts | Partial | inbound `say` only | Yes for proactive channel posts | No tool-level notify API |
| Slack interactions | Partial | message events | Yes for buttons/assign | No block_actions handler |
| REST webhook hosting | Yes | `RESTAPI.run` | Combine handlers | FastAPI |
| Multimodal image input | Yes | `examples/api/multimodal/*` | Config + litellm | Extra name mismatch |
| Audio transcription | No | — | Yes | Not found |
| Supabase persistence | No | — | Yes | No PG/Supabase adapter |
| Knowledge retrieval | Yes | `examples/cli/knowledgebase/openai/chromadb` | Content + `KnowledgeBuilder` | Chroma/Neo4j/Starburst |
| Tracing / observability | Partial | config `trace` | Langfuse/OpenLLMetry extras | No incident correlation built-in |
| Tool retries | No | — | Yes if required | Runner catch-all |
| Webhook idempotency | No | — | Yes | WhatsApp always 200; no message-id store |

---

## 27. Prompt Assumption Reality Check

| Assumption | Verified? | Actual Repository Behavior |
| --- | --- | --- |
| Agents use OpenAI Agents SDK | Yes | `from agents import Agent` + `OpenAIModule` |
| Handoffs are directly supported | Yes | SDK `handoffs=[...]` |
| Sessions persist conversations | Partial | In-memory by default; Redis/Dynamo/etc. if configured; WhatsApp key = phone |
| Pre/post hooks exist | Yes | `PreHook`/`PostHook` on Module; **not** inner handoffs |
| WhatsApp integration exists | Yes | `AgentWhatsAppRequestHandler`; no public send-from-tool API |
| Slack integration exists | Yes | Inbound Events API; proactive alerts are app code |
| REST mode is supported | Yes | `RESTAPI.run` / FastAPI |
| SPEC.md drives skill-based generation | Partial | Human+coding-agent workflow; **not** an automated compiler |
| Use cases share `ak-py` environment | **No** | **Per-use-case `pyproject.toml` + uv** |
| `use_cases/` underscore path | **No** | **`use-cases/` hyphen** |
| `WhatsAppIntegration.send_message` | **No** | Private `_send_message` on handler |
| `Agent(..., session=, pre_hooks=)` | **No** | Session via `AgentService`/`Runtime`; hooks via `module.pre_hook` |
| `uv add` from `ak-py/` for SentinelLoop deps | **No** | Add deps in `use-cases/sentinelloop-ai/pyproject.toml` |
| Built-in STT | **No** | Audio rejected |
| Supabase session store | **No** | App-level DB |
| `agentkernel[multimodal]` extra | **No** in pyproject 0.6.0 | Examples still name it; enable via config + litellm |

---

## 28. Important API Constraints

1. Follow **this checkout’s APIs**, not later guessed constructors.
2. Path is `use-cases/sentinelloop-ai`, not `use_cases/...`.
3. Isolate SentinelLoop deps in **its own** `pyproject.toml`.
4. Register agents with **one** `OpenAIModule`.
5. Tools: `OpenAIToolBuilder.bind` + `ToolContext.get()` inside functions.
6. Hooks do not wrap `risk_agent` after a handoff — put deterministic scoring in **Python tools**.
7. Do not treat AK sessions as the incident database.
8. Do not call non-existent `WhatsAppIntegration.send_message`; subclass handler or use Graph API/`httpx` in tools (keep credentials in env).
9. Slack incident alerts to a **safety channel** are **new app code** (`slack_sdk.WebClient.chat_postMessage` or equivalent), not `AgentSlackRequestHandler`.
10. WhatsApp voice is unsupported until you add STT.
11. Implement **idempotency yourself** (store WhatsApp `message.id`).
12. Never report Slack/Supabase/KB success if the tool/HTTP call failed.
13. Secrets: `AK_*` + `OPENAI_API_KEY` + `SLACK_*`; never commit tokens.
14. Line length 120 in the use case; black/isort.

---

## 29. Open Questions

1. Duplicate `GET /health` if both WhatsApp and Slack handlers plus `RESTAPI._create_app` define `/health` — FastAPI behavior not verified at runtime here.
2. Whether unpublished `ak-py` 0.6.0 on this branch matches PyPI 0.6.0 extras (especially missing `multimodal` extra).
3. Whether OpenAI Agents SDK `output_type=` works through `OpenAIRunner.str(final_output)` without losing structure.
4. Production Redis vs in-memory for WhatsApp (phone-keyed sessions) on a single demo process.
5. Slack Bolt `AsyncApp()` credential discovery vs documenting only `SLACK_*` — assumed Bolt defaults; not unit-tested in this pass.

---

## Hackathon shortest path (analysis only)

| Demo need | Classification | Reuse |
| --- | --- | --- |
| 1. Inbound WhatsApp webhook | **directly reusable** | `AgentWhatsAppRequestHandler` + `RESTAPI.run` |
| 2. Multilingual agent input | **adaptable** | Plain `instructions` + LLM; no AK i18n API |
| 3. Image evidence | **directly reusable** | WhatsApp image → `AgentRequestImage`; optional multimodal hook |
| 4. Session continuity | **adaptable** | Phone as `session_id`; store `active_incident_id` in `nv_cache` |
| 5. Structured incident extraction | **new app code required** | Tools returning JSON + Python validation |
| 6. Deterministic risk tool | **new app code required** | Plain function + `OpenAIToolBuilder.bind` (like waste-sorting lookup) |
| 7. Knowledge retrieval | **adaptable** | `KnowledgeBuilder` + Chroma example |
| 8. Slack notification | **new app code required** | Proactive `chat_postMessage`; inbound Slack optional |
| 9. Supabase persistence | **new app code required** | Tools wrapping supabase-py; not an AK store |
| 10. Worker follow-up | **adaptable** | Same WhatsApp session + outbound `_send_message` via subclass/tool |
| 11. REST deployment | **directly reusable** | `RESTAPI.run([whatsapp, slack?])` |

Closest technical starting points (compose, do not copy blindly):

1. `examples/api/whatsapp/server.py`
2. `examples/cli/openai/demo.py` (handoffs + tools)
3. `examples/cli/knowledgebase/openai/chromadb/demo.py`
4. `use-cases/waste-sorting-assistant/` (SPEC + isolated uv project + `nv_cache` tools)
5. `examples/api/hooks/` (PreHook halt/mutate)
6. `examples/api/slack/server.py` only if officers chat with the bot in Slack

Do not implement SentinelLoop in this file’s creation pass.
