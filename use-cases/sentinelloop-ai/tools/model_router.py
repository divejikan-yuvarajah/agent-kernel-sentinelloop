"""OpenRouter model gateway for SentinelLoop.

Agents call ``call_model(role, messages, **kwargs)`` only. This module owns
catalog discovery, free-first ranking, fallback, and paid-budget governance.

OpenRouter ``/models`` ``pricing.prompt`` / ``pricing.completion`` are USD
**per token** (website cards show per-million; do not multiply by 1e6 again).

This module does not compute risk scores, persist incidents, or invent
safety guidance.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger("sentinelloop.model_router")

MODELS_URL = "https://openrouter.ai/api/v1/models"
CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"

ROLE_FAST = "role_fast"
ROLE_REASONING = "role_reasoning"
ROLE_GUIDANCE = "role_guidance"
REQUIRED_ROLES = (ROLE_FAST, ROLE_REASONING, ROLE_GUIDANCE)
FAMILY_ORDER = ("qwen", "gemini", "deepseek")

_BLOCKED_KWARGS = frozenset(
    {
        "model",
        "api_key",
        "api-key",
        "authorization",
        "base_url",
        "extra_headers",
        "extra_body",
        "http_client",
    }
)
_ALLOWED_KWARGS = frozenset(
    {
        "temperature",
        "max_tokens",
        "max_completion_tokens",
        "response_format",
        "stop",
        "top_p",
        "seed",
        "tools",
        "tool_choice",
        "frequency_penalty",
        "presence_penalty",
        "reasoning",
        "include_reasoning",
    }
)

_DEFAULT_MAX_TOKENS = {
    ROLE_FAST: 512,
    ROLE_REASONING: 1024,
    ROLE_GUIDANCE: 768,
}
_DEFAULT_TEMPERATURE = {
    ROLE_FAST: 0.3,
    ROLE_REASONING: 0.1,
    ROLE_GUIDANCE: 0.2,
}

_ZERO = Decimal("0")
_WARNED_BUDGET_BANDS: set[str] = set()
_RECENT_CALLS_MAX = 40


class ModelRouterConfigError(ValueError):
    """Missing or invalid router configuration."""


class ModelRouterAuthError(RuntimeError):
    """OpenRouter rejected the API key. Do not cycle models."""


class ModelRouterError(RuntimeError):
    """Controlled routing failure (no silent discard of safety work)."""


class CatalogModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str | None = None
    context_length: int | None = None
    created: int | None = None
    prompt_price: Decimal | None = None
    completion_price: Decimal | None = None
    input_modalities: list[str] = Field(default_factory=lambda: ["text"])
    output_modalities: list[str] = Field(default_factory=lambda: ["text"])
    pricing_raw: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_free(self) -> bool:
        return self.prompt_price == _ZERO and self.completion_price == _ZERO

    @property
    def is_paid(self) -> bool:
        if self.prompt_price is None or self.completion_price is None:
            return False
        return self.prompt_price > _ZERO or self.completion_price > _ZERO

    @property
    def combined_price(self) -> Decimal:
        return (self.prompt_price or _ZERO) + (self.completion_price or _ZERO)

    def supports_text_chat(self) -> bool:
        ins = {m.lower() for m in self.input_modalities}
        outs = {m.lower() for m in self.output_modalities}
        if "text" not in ins or "text" not in outs:
            return False
        if "audio" in outs:
            return False
        lowered = f"{self.id} {self.name or ''}".lower()
        if "lyria" in lowered or "content-safety" in lowered:
            return False
        return True


class ModelCallResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: str | None = None
    model: str | None = None
    role: str
    usage: dict[str, Any] | None = None
    estimated_cost_usd: Decimal = _ZERO
    paid: bool = False
    budget_limited: bool = False
    fallback_used: bool = False
    attempted_models: list[str] = Field(default_factory=list)
    finish_reason: str | None = None
    latency_s: float | None = None
    degraded: bool = False
    error: str | None = None
    message: str | None = None


def parse_price(raw: Any) -> Decimal | None:
    if raw is None or raw == "":
        return None
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if value < _ZERO:
        return None
    return value


def _family(model: CatalogModel) -> str | None:
    blob = f"{model.id} {model.name or ''}".lower()
    if "qwen" in blob:
        return "qwen"
    if "gemini" in blob:
        return "gemini"
    if "deepseek" in blob:
        return "deepseek"
    return None


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(payload, indent=2, default=str)
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decimal_env(name: str) -> Decimal | None:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ModelRouterConfigError(f"{name} must be a non-negative number") from exc
    if value < _ZERO:
        raise ModelRouterConfigError(f"{name} must be a non-negative number")
    return value


def _estimate_prompt_tokens(messages: list[dict[str, Any]]) -> int:
    chars = 0
    for item in messages:
        content = item.get("content")
        chars += len(str(content))
    return max(16, chars // 4)


def _message_modalities(messages: list[dict[str, Any]]) -> set[str]:
    mods = {"text"}
    for item in messages:
        content = item.get("content")
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                kind = str(part.get("type") or "")
                if kind in {"image_url", "image"}:
                    mods.add("image")
                if kind in {"audio", "input_audio"}:
                    mods.add("audio")
    return mods


def _validate_messages(messages: Any) -> list[dict[str, Any]]:
    if not isinstance(messages, list) or not messages:
        raise ModelRouterConfigError("messages must be a non-empty OpenAI-compatible list")
    cleaned: list[dict[str, Any]] = []
    for item in messages:
        if not isinstance(item, dict) or "role" not in item or "content" not in item:
            raise ModelRouterConfigError("each message needs role and content")
        cleaned.append(item)
    return cleaned


def _sanitize_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    for blocked in _BLOCKED_KWARGS:
        kwargs.pop(blocked, None)
        kwargs.pop(blocked.replace("-", "_"), None)
    return {key: value for key, value in kwargs.items() if key in _ALLOWED_KWARGS}


def catalog_model_from_api(entry: dict[str, Any]) -> CatalogModel | None:
    model_id = entry.get("id")
    if not isinstance(model_id, str) or not model_id:
        log.warning("[model-router] skipped catalog entry without id")
        return None
    pricing_raw = entry.get("pricing")
    pricing: dict[str, Any] = pricing_raw if isinstance(pricing_raw, dict) else {}
    arch_raw = entry.get("architecture")
    arch: dict[str, Any] = arch_raw if isinstance(arch_raw, dict) else {}
    ins = arch.get("input_modalities") or ["text"]
    outs = arch.get("output_modalities") or ["text"]
    if not isinstance(ins, list):
        ins = ["text"]
    if not isinstance(outs, list):
        outs = ["text"]
    ctx = entry.get("context_length")
    context_length = int(ctx) if isinstance(ctx, int) else None
    created = entry.get("created")
    created_i = int(created) if isinstance(created, int) else None
    return CatalogModel(
        id=model_id,
        name=entry.get("name") if isinstance(entry.get("name"), str) else None,
        context_length=context_length,
        created=created_i,
        prompt_price=parse_price(pricing.get("prompt")),
        completion_price=parse_price(pricing.get("completion")),
        input_modalities=[str(x) for x in ins],
        output_modalities=[str(x) for x in outs],
        pricing_raw={k: str(v) for k, v in pricing.items()},
    )


class ModelRouter:
    """Process-local OpenRouter router. File ledger is not cross-process safe."""

    def __init__(
        self,
        *,
        api_key: str | None,
        budget_ceiling: Decimal | None,
        roles_config: dict[str, Any],
        runtime_dir: Path,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 30.0,
        max_attempts: int = 6,
        max_free_attempts: int = 3,
        per_model_retries: int = 1,
        circuit_failures: int = 3,
        circuit_cooldown_s: float = 60.0,
    ) -> None:
        if not api_key:
            raise ModelRouterConfigError("OPENROUTER_API_KEY is missing")
        missing = [role for role in REQUIRED_ROLES if role not in roles_config]
        if missing:
            raise ModelRouterConfigError("config.yaml models.roles missing: " + ", ".join(missing))
        self._api_key = api_key
        self._budget_ceiling = budget_ceiling
        self._paid_enabled = budget_ceiling is not None
        self._roles_config = roles_config
        self._runtime_dir = runtime_dir
        self._cache_path = runtime_dir / "models_cache.json"
        self._ledger_path = runtime_dir / "spend_ledger.json"
        self._timeout = timeout_seconds
        self._max_attempts = max_attempts
        self._max_free_attempts = max_free_attempts
        self._per_model_retries = per_model_retries
        self._circuit_failures = circuit_failures
        self._circuit_cooldown_s = circuit_cooldown_s
        self._own_client = client is None
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds))
        self._catalog: dict[str, CatalogModel] = {}
        self._catalog_source = "none"
        self._catalog_loaded = False
        self._ledger_lock = asyncio.Lock()
        self._reserved = _ZERO
        self._ledger_corrupt = False
        self._cumulative = _ZERO
        self._ledger: dict[str, Any] = {}
        self._circuit: dict[str, dict[str, Any]] = {}
        self._load_ledger()

    @classmethod
    def from_project(cls, project_root: Path | None = None, **kwargs: Any) -> "ModelRouter":
        root = project_root or Path(__file__).resolve().parents[1]
        config_path = root / "config.yaml"
        with config_path.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        models_cfg = raw.get("models") or {}
        roles = models_cfg.get("roles") or {}
        runtime = root / ".runtime"
        ceiling = _decimal_env("OPENROUTER_BUDGET_CEILING_USD")
        if ceiling is None:
            log.warning("[model-router] OPENROUTER_BUDGET_CEILING_USD unset; paid fallbacks disabled")
        return cls(
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            budget_ceiling=ceiling,
            roles_config=roles,
            runtime_dir=kwargs.pop("runtime_dir", None) or runtime,
            timeout_seconds=float(models_cfg.get("timeout_seconds", 30)),
            max_attempts=int(models_cfg.get("max_attempts", 6)),
            max_free_attempts=int(models_cfg.get("max_free_attempts", 3)),
            per_model_retries=int(models_cfg.get("per_model_retries", 1)),
            circuit_failures=int(models_cfg.get("circuit_failures", 3)),
            circuit_cooldown_s=float(models_cfg.get("circuit_cooldown_seconds", 60)),
            **kwargs,
        )

    @property
    def cache_path(self) -> Path:
        return self._cache_path

    @property
    def ledger_path(self) -> Path:
        return self._ledger_path

    def diagnostics(self) -> dict[str, Any]:
        remaining = None
        if self._budget_ceiling is not None:
            remaining = str(self._budget_ceiling - self._cumulative)
        return {
            "catalog_loaded": self._catalog_loaded,
            "catalog_source": self._catalog_source,
            "free_model_count": len([m for m in self._catalog.values() if m.is_free and m.supports_text_chat()]),
            "role_models": (
                {role: [c.id for c in self._free_chain(role)[:3]] for role in REQUIRED_ROLES}
                if self._catalog_loaded
                else {}
            ),
            "cumulative_spend_usd": str(self._cumulative),
            "budget_ceiling_usd": str(self._budget_ceiling) if self._budget_ceiling is not None else None,
            "budget_remaining_usd": remaining,
            "paid_enabled": self._paid_enabled and not self._ledger_corrupt,
        }

    async def aclose(self) -> None:
        if self._own_client:
            await self._client.aclose()

    async def ensure_catalog(self) -> None:
        if self._catalog_loaded:
            return
        live = await self._fetch_live_catalog()
        if live is not None:
            self._catalog = live
            self._catalog_source = "live"
            self._write_cache()
        else:
            cached = self._read_cache()
            if cached:
                self._catalog = cached
                self._catalog_source = "cache"
                log.warning("[model-router] using stale models_cache.json after live /models failure")
            else:
                self._catalog = {}
                self._catalog_source = "none"
                log.warning("[model-router] no live catalog and no cache; paid config IDs only")
        self._catalog_loaded = True
        self._log_startup_summary()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Title": "SentinelLoop AI",
        }
        referer = os.environ.get("OPENROUTER_HTTP_REFERER")
        if referer:
            headers["HTTP-Referer"] = referer
        return headers

    async def _fetch_live_catalog(self) -> dict[str, CatalogModel] | None:
        try:
            response = await self._client.get(MODELS_URL, headers=self._headers())
        except httpx.HTTPError as exc:
            log.warning("[model-router] GET /models failed: %s", type(exc).__name__)
            return None
        if response.status_code in {401, 403}:
            raise ModelRouterAuthError("OpenRouter rejected OPENROUTER_API_KEY")
        if response.status_code >= 400:
            log.warning("[model-router] GET /models HTTP %s", response.status_code)
            return None
        try:
            payload = response.json()
        except ValueError:
            log.warning("[model-router] GET /models returned non-JSON")
            return None
        entries = payload.get("data")
        if not isinstance(entries, list):
            log.warning("[model-router] GET /models missing data list")
            return None
        catalog: dict[str, CatalogModel] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            try:
                model = catalog_model_from_api(entry)
            except Exception:
                log.warning("[model-router] skipped malformed catalog model")
                continue
            if model is not None:
                catalog[model.id] = model
        return catalog

    def _write_cache(self) -> None:
        free = [m for m in self._catalog.values() if m.is_free and m.supports_text_chat()]
        payload = {
            "version": 1,
            "discovered_at": _now_iso(),
            "source": "live",
            "models": [m.model_dump(mode="json") for m in self._catalog.values()],
            "free_ids": [m.id for m in free],
            "role_picks": {role: [c.id for c in self._free_chain(role)[:5]] for role in REQUIRED_ROLES},
        }
        _atomic_write_json(self._cache_path, payload)

    def _read_cache(self) -> dict[str, CatalogModel] | None:
        if not self._cache_path.exists():
            return None
        try:
            payload = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.warning("[model-router] ignoring corrupt models_cache.json")
            return None
        if not isinstance(payload, dict) or payload.get("version") != 1:
            log.warning("[model-router] ignoring incompatible models_cache.json")
            return None
        models = payload.get("models")
        if not isinstance(models, list):
            return None
        catalog: dict[str, CatalogModel] = {}
        for row in models:
            if not isinstance(row, dict) or not row.get("id"):
                continue
            try:
                if "prompt_price" in row and row["prompt_price"] is not None:
                    row["prompt_price"] = Decimal(str(row["prompt_price"]))
                if "completion_price" in row and row["completion_price"] is not None:
                    row["completion_price"] = Decimal(str(row["completion_price"]))
                catalog[row["id"]] = CatalogModel.model_validate(row)
            except Exception:
                continue
        return catalog or None

    def _load_ledger(self) -> None:
        if not self._ledger_path.exists():
            self._ledger = {
                "version": 1,
                "cumulative_spend_usd": "0",
                "updated_at": _now_iso(),
                "request_count": 0,
                "paid_call_count": 0,
                "per_model_spend_usd": {},
                "recent_calls": [],
            }
            _atomic_write_json(self._ledger_path, self._ledger)
            self._cumulative = _ZERO
            return
        try:
            payload = json.loads(self._ledger_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("version") != 1:
                raise ValueError("bad ledger")
            self._cumulative = Decimal(str(payload.get("cumulative_spend_usd", "0")))
            if self._cumulative < _ZERO:
                raise ValueError("negative spend")
            self._ledger = payload
        except Exception:
            log.error("[model-router] corrupt spend_ledger.json; paid calls disabled until repaired")
            self._ledger_corrupt = True
            self._paid_enabled = False
            self._cumulative = _ZERO

    def _persist_ledger(self) -> None:
        self._ledger["cumulative_spend_usd"] = str(self._cumulative)
        self._ledger["updated_at"] = _now_iso()
        _atomic_write_json(self._ledger_path, self._ledger)

    def _log_startup_summary(self) -> None:
        free_n = len([m for m in self._catalog.values() if m.is_free and m.supports_text_chat()])
        log.info("[model-router] catalog: %s free candidates discovered (%s)", free_n, self._catalog_source)
        for role in REQUIRED_ROLES:
            chain = self._free_chain(role)
            pick = chain[0].id if chain else "(none — paid/config only)"
            log.info("[model-router] %s → %s", role, pick)
        ceiling = self._budget_ceiling if self._budget_ceiling is not None else "paid-disabled"
        log.info("[model-router] Budget ceiling → %s  Spend so far → %s", ceiling, self._cumulative)

    def _eligible_free(self, role: str, modalities: set[str]) -> list[CatalogModel]:
        out = []
        for model in self._catalog.values():
            if not model.is_free or not model.supports_text_chat():
                continue
            if not self._compatible(model, modalities):
                continue
            out.append(model)
        return out

    def _compatible(self, model: CatalogModel, modalities: set[str]) -> bool:
        ins = {m.lower() for m in model.input_modalities}
        for need in modalities:
            if need != "text" and need not in ins:
                return False
        return True

    def _sort_family(self, models: list[CatalogModel]) -> list[CatalogModel]:
        return sorted(
            models,
            key=lambda m: (
                -(m.context_length or -1),
                -(m.created or 0),
                m.id,
            ),
        )

    def _family_order(self, role: str) -> tuple[str, ...]:
        configured = (self._roles_config.get(role) or {}).get("preferred_family_order")
        if isinstance(configured, list) and configured:
            return tuple(str(item).lower() for item in configured)
        return FAMILY_ORDER

    def _role_generation_defaults(self, role: str) -> tuple[float, int]:
        cfg = self._roles_config.get(role) or {}
        temperature = cfg.get("temperature", _DEFAULT_TEMPERATURE[role])
        max_tokens = cfg.get("max_tokens", _DEFAULT_MAX_TOKENS[role])
        return float(temperature), int(max_tokens)

    def _free_chain(self, role: str, modalities: set[str] | None = None) -> list[CatalogModel]:
        modalities = modalities or {"text"}
        free = self._eligible_free(role, modalities)
        ordered: list[CatalogModel] = []
        seen: set[str] = set()
        for family in self._family_order(role):
            group = [m for m in free if _family(m) == family]
            for model in self._sort_family(group):
                if model.id not in seen:
                    ordered.append(model)
                    seen.add(model.id)
        others = [m for m in free if _family(m) is None]
        others_known = [m for m in others if m.context_length is not None]
        others_unknown = [m for m in others if m.context_length is None]
        others_known.sort(key=lambda m: (-(m.context_length or 0), m.id))
        for model in others_known + others_unknown:
            if model.id not in seen:
                ordered.append(model)
                seen.add(model.id)
        return ordered

    def _paid_chain(self, role: str, modalities: set[str]) -> list[CatalogModel]:
        configured = list((self._roles_config.get(role) or {}).get("paid_fallbacks") or [])
        found: list[CatalogModel] = []
        for model_id in configured:
            if not isinstance(model_id, str):
                continue
            model = self._catalog.get(model_id)
            if model is None:
                log.warning(
                    "[model-router] Configured fallback %s not present in current OpenRouter catalog.", model_id
                )
                continue
            if model.is_free:
                continue
            if not model.is_paid:
                log.warning("[model-router] fallback %s has unknown pricing; skipping", model_id)
                continue
            if not model.supports_text_chat() or not self._compatible(model, modalities):
                continue
            found.append(model)
        # Eligibility from config; runtime prefers cheapest combined token price.
        found.sort(key=lambda m: (m.combined_price, -(m.context_length or 0), m.id))
        return found

    def _on_circuit(self, model_id: str) -> bool:
        state = self._circuit.get(model_id)
        if not state:
            return False
        until = float(state.get("until") or 0)
        return time.monotonic() < until

    def _note_failure(self, model_id: str) -> None:
        state = self._circuit.setdefault(model_id, {"n": 0, "until": 0.0})
        state["n"] = int(state["n"]) + 1
        if int(state["n"]) >= self._circuit_failures:
            state["until"] = time.monotonic() + self._circuit_cooldown_s
            log.info("[model-router] %s cooling down after repeated transient failures", model_id)

    def _note_success(self, model_id: str) -> None:
        self._circuit.pop(model_id, None)

    def _candidate_ids(self, role: str, modalities: set[str]) -> tuple[list[CatalogModel], list[CatalogModel]]:
        free = [m for m in self._free_chain(role, modalities) if not self._on_circuit(m.id)]
        paid = [m for m in self._paid_chain(role, modalities) if not self._on_circuit(m.id)]
        return free, paid

    async def call_model(self, role: str, messages: list, **kwargs: Any) -> ModelCallResult:
        await self.ensure_catalog()
        if role not in REQUIRED_ROLES:
            raise ModelRouterConfigError(f"unknown model role {role!r}")
        messages = _validate_messages(messages)
        gen = _sanitize_kwargs(dict(kwargs))
        temperature, max_tokens = self._role_generation_defaults(role)
        gen.setdefault("temperature", temperature)
        gen.setdefault("max_tokens", max_tokens)
        modalities = _message_modalities(messages)
        if "image" in modalities or "audio" in modalities:
            compatible = any(self._compatible(m, modalities) for m in self._catalog.values())
            if not compatible:
                raise ModelRouterError(
                    "messages include image/audio content but no catalog model supports those modalities"
                )
        log.info("[model-router] request role=%s", role)
        from guardrails.output_validation import validate_model_budget

        validate_model_budget(current_cost=self._cumulative, requested_cost=0, ceiling=self._budget_ceiling)
        free, paid = self._candidate_ids(role, modalities)
        attempted: list[str] = []

        result = await self._try_chain(role, messages, gen, free, attempted, limit=self._max_free_attempts)
        if result is not None:
            return result
        attempts = len(attempted)

        budget_limited = False
        if self._paid_enabled and not self._ledger_corrupt:
            for model in paid:
                if attempts >= self._max_attempts:
                    break
                allowed, _projected = await self._preflight_paid(model, messages, gen)
                if not allowed:
                    budget_limited = True
                    validate_model_budget(
                        current_cost=self._cumulative,
                        requested_cost=_projected,
                        ceiling=self._budget_ceiling,
                    )
                    log.info("[model-router] paid fallback=%s refused (budget)", model.id)
                    continue
                attempts += 1
                call = await self._complete(role, model, messages, gen, paid=True)
                attempted.append(model.id)
                if call is None:
                    continue
                if call.paid:
                    return call.model_copy(update={"attempted_models": attempted, "fallback_used": True})
        elif self._ledger_corrupt:
            budget_limited = True

        retry_free = await self._try_chain(role, messages, gen, free, attempted, budget_limited=True)
        if retry_free is not None:
            return retry_free.model_copy(update={"budget_limited": True, "fallback_used": True})

        log.error("[model-router] no model capacity role=%s attempted=%s", role, attempted)
        return ModelCallResult(
            content=None,
            model=None,
            role=role,
            budget_limited=budget_limited or not self._paid_enabled,
            fallback_used=bool(attempted),
            attempted_models=attempted,
            degraded=True,
            error="no_capacity",
            message="No eligible OpenRouter model could serve this request. Preserve the incident and use deterministic/human paths.",
        )

    async def _try_chain(
        self,
        role: str,
        messages: list[dict[str, Any]],
        gen: dict[str, Any],
        chain: list[CatalogModel],
        attempted: list[str],
        *,
        budget_limited: bool = False,
        limit: int | None = None,
    ) -> ModelCallResult | None:
        started = 0
        for model in chain:
            if model.id in attempted:
                continue
            if len(attempted) >= self._max_attempts:
                break
            if limit is not None and started >= limit:
                break
            started += 1
            call = await self._complete(role, model, messages, gen, paid=False)
            attempted.append(model.id)
            if call is None:
                continue
            call.attempted_models = list(attempted)
            call.fallback_used = len(attempted) > 1 or budget_limited
            call.budget_limited = budget_limited
            return call
        return None

    async def _complete(
        self,
        role: str,
        model: CatalogModel,
        messages: list[dict[str, Any]],
        gen: dict[str, Any],
        *,
        paid: bool,
    ) -> ModelCallResult | None:
        last_error: str | None = None
        for _try in range(self._per_model_retries + 1):
            started = time.monotonic()
            reservation = _ZERO
            if paid:
                ok, reservation = await self._reserve_paid(model, messages, gen)
                if not ok:
                    return None
            try:
                response = await self._client.post(
                    CHAT_URL,
                    headers=self._headers(),
                    json={"model": model.id, "messages": messages, **gen},
                )
            except httpx.TimeoutException:
                last_error = "timeout"
                self._note_failure(model.id)
                if paid:
                    await self._release(reservation)
                log.info("[model-router] %s timeout → trying next model", model.id)
                break
            except httpx.HTTPError:
                last_error = "http"
                self._note_failure(model.id)
                if paid:
                    await self._release(reservation)
                break
            latency = time.monotonic() - started
            if response.status_code in {401, 403}:
                if paid:
                    await self._release(reservation)
                raise ModelRouterAuthError("OpenRouter rejected OPENROUTER_API_KEY")
            if response.status_code == 429:
                if paid:
                    await self._release(reservation)
                self._note_failure(model.id)
                log.info("[model-router] %s rate limited → trying next model", model.id)
                break
            if response.status_code >= 500:
                if paid:
                    await self._release(reservation)
                self._note_failure(model.id)
                log.info("[model-router] %s HTTP %s → trying next model", model.id, response.status_code)
                if _try < self._per_model_retries:
                    await asyncio.sleep(0.2)
                    continue
                break
            if response.status_code >= 400:
                if paid:
                    await self._release(reservation)
                log.info("[model-router] %s HTTP %s (non-retryable)", model.id, response.status_code)
                break
            try:
                body = response.json()
            except ValueError:
                if paid:
                    await self._release(reservation)
                break
            content, usage, finish = _parse_completion(body)
            served = body.get("model") if isinstance(body.get("model"), str) else model.id
            cost = self._cost_for_response(model, usage, gen, messages, paid=paid)
            if paid:
                await self._commit_paid(model.id, cost, reservation)
            else:
                if reservation:
                    await self._release(reservation)
            self._note_success(model.id)
            tier = "PAID" if paid else "FREE"
            log.info(
                "[model-router] served by %s role=%s tier=%s estimated_cost=$%s latency=%.2fs",
                served,
                role,
                tier,
                cost,
                latency,
            )
            if paid:
                self._maybe_budget_warning()
            await self._note_recent_call(
                role=role,
                model=served,
                latency_s=latency,
                usage=usage,
                cost=cost if paid else _ZERO,
                paid=paid,
            )
            return ModelCallResult(
                content=content,
                model=served,
                role=role,
                usage=usage,
                estimated_cost_usd=cost if paid else _ZERO,
                paid=paid,
                latency_s=latency,
                finish_reason=finish,
                message=None if isinstance(content, str) else None,
            )
        if last_error:
            log.debug("[model-router] %s failed (%s)", model.id, last_error)
        return None

    def _cost_for_response(
        self,
        model: CatalogModel,
        usage: dict[str, Any] | None,
        gen: dict[str, Any],
        messages: list[dict[str, Any]],
        *,
        paid: bool,
    ) -> Decimal:
        if not paid:
            return _ZERO
        if usage is None:
            log.warning("[model-router] paid response missing usage; charging conservative preflight estimate")
            return self._project_cost(model, messages, gen)
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        if not isinstance(prompt_tokens, int) or not isinstance(completion_tokens, int):
            log.warning("[model-router] paid usage incomplete; charging conservative estimate")
            return self._project_cost(model, messages, gen)
        prompt_price = model.prompt_price or _ZERO
        completion_price = model.completion_price or _ZERO
        return (Decimal(prompt_tokens) * prompt_price) + (Decimal(completion_tokens) * completion_price)

    def _project_cost(self, model: CatalogModel, messages: list[dict[str, Any]], gen: dict[str, Any]) -> Decimal:
        prompt_tokens = Decimal(_estimate_prompt_tokens(messages))
        max_tokens = Decimal(int(gen.get("max_tokens") or _DEFAULT_MAX_TOKENS[ROLE_FAST]))
        return (prompt_tokens * (model.prompt_price or _ZERO)) + (max_tokens * (model.completion_price or _ZERO))

    async def _preflight_paid(
        self, model: CatalogModel, messages: list[dict[str, Any]], gen: dict[str, Any]
    ) -> tuple[bool, Decimal]:
        projected = self._project_cost(model, messages, gen)
        async with self._ledger_lock:
            if self._budget_ceiling is None or self._ledger_corrupt:
                return False, _ZERO
            if self._cumulative + self._reserved + projected > self._budget_ceiling:
                return False, projected
        return True, projected

    async def _reserve_paid(
        self, model: CatalogModel, messages: list[dict[str, Any]], gen: dict[str, Any]
    ) -> tuple[bool, Decimal]:
        projected = self._project_cost(model, messages, gen)
        async with self._ledger_lock:
            if self._budget_ceiling is None or self._ledger_corrupt:
                return False, _ZERO
            if self._cumulative + self._reserved + projected > self._budget_ceiling:
                return False, _ZERO
            self._reserved += projected
            return True, projected

    async def _release(self, reservation: Decimal) -> None:
        async with self._ledger_lock:
            self._reserved = max(_ZERO, self._reserved - reservation)

    async def _commit_paid(self, model_id: str, actual: Decimal, reservation: Decimal) -> None:
        async with self._ledger_lock:
            self._reserved = max(_ZERO, self._reserved - reservation)
            self._cumulative += actual
            self._ledger["request_count"] = int(self._ledger.get("request_count") or 0) + 1
            self._ledger["paid_call_count"] = int(self._ledger.get("paid_call_count") or 0) + 1
            per = dict(self._ledger.get("per_model_spend_usd") or {})
            per[model_id] = str(Decimal(str(per.get(model_id, "0"))) + actual)
            self._ledger["per_model_spend_usd"] = per
            prices = dict(self._ledger.get("price_snapshots") or {})
            model = self._catalog.get(model_id)
            if model is not None:
                prices[model_id] = {
                    "prompt": str(model.prompt_price),
                    "completion": str(model.completion_price),
                    "unit": "usd_per_token",
                }
            self._ledger["price_snapshots"] = prices
            self._persist_ledger()
            log.info(
                "[model-router] estimated_cost=$%s cumulative=$%s/%s",
                actual,
                self._cumulative,
                self._budget_ceiling,
            )

    async def _note_recent_call(
        self,
        *,
        role: str,
        model: str | None,
        latency_s: float,
        usage: dict[str, Any] | None,
        cost: Decimal,
        paid: bool,
    ) -> None:
        usage_safe = {
            "prompt_tokens": (usage or {}).get("prompt_tokens"),
            "completion_tokens": (usage or {}).get("completion_tokens"),
            "total_tokens": (usage or {}).get("total_tokens"),
        }
        entry = {
            "timestamp": _now_iso(),
            "model": model,
            "model_role": role,
            "latency_s": round(float(latency_s), 3),
            "token_usage": usage_safe,
            "cost_usd": str(cost),
            "paid": paid,
            "tier": "PAID" if paid else "FREE",
        }
        async with self._ledger_lock:
            calls = list(self._ledger.get("recent_calls") or [])
            calls.append(entry)
            self._ledger["recent_calls"] = calls[-_RECENT_CALLS_MAX:]
            if not paid:
                self._ledger["request_count"] = int(self._ledger.get("request_count") or 0) + 1
            self._persist_ledger()

    def _maybe_budget_warning(self) -> None:
        if self._budget_ceiling in {None, _ZERO}:
            return
        ratio = self._cumulative / self._budget_ceiling
        for band, threshold in (("90", Decimal("0.90")), ("75", Decimal("0.75"))):
            if ratio >= threshold and band not in _WARNED_BUDGET_BANDS:
                _WARNED_BUDGET_BANDS.add(band)
                log.warning("[model-router] warning: %s%% of OpenRouter paid budget consumed", band)
                break


def _parse_completion(body: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None, str | None]:
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else None
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None, usage, None
    choice: dict[str, Any] = choices[0] if isinstance(choices[0], dict) else {}
    finish = choice.get("finish_reason") if isinstance(choice.get("finish_reason"), str) else None
    message_raw = choice.get("message")
    message: dict[str, Any] = message_raw if isinstance(message_raw, dict) else {}
    content = message.get("content")
    if content is None:
        parsed = message.get("parsed")
        if parsed is not None:
            content = json.dumps(parsed) if not isinstance(parsed, str) else parsed
    if content is not None and not isinstance(content, str):
        content = json.dumps(content)
    return content, usage, finish


_default_router: ModelRouter | None = None
_default_lock = asyncio.Lock()


async def get_router() -> ModelRouter:
    global _default_router
    async with _default_lock:
        if _default_router is None:
            _default_router = ModelRouter.from_project()
            await _default_router.ensure_catalog()
        return _default_router


def reset_router() -> None:
    global _default_router
    _default_router = None
    _WARNED_BUDGET_BANDS.clear()


async def call_model(role: str, messages: list, **kwargs: Any) -> ModelCallResult:
    """Public SentinelLoop model gateway. Role selects the model; agents do not."""
    router = kwargs.pop("_router", None)
    if router is None:
        router = await get_router()
    return await router.call_model(role, messages, **kwargs)
