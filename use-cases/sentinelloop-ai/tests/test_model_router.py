"""Unit tests for the SentinelLoop OpenRouter model router. No live API by default."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from tools.model_router import (
    CHAT_URL,
    MODELS_URL,
    CatalogModel,
    ModelRouter,
    ModelRouterAuthError,
    ModelRouterConfigError,
    ModelRouterError,
    call_model,
    catalog_model_from_api,
    parse_price,
    reset_router,
)

ROLES = {
    "role_fast": {
        "preferred_family_order": ["qwen", "gemini", "deepseek"],
        "paid_fallbacks": ["mistralai/mistral-nemo", "inclusionai/ling-3.0-flash"],
        "temperature": 0.3,
        "max_tokens": 64,
    },
    "role_reasoning": {
        "preferred_family_order": ["qwen", "gemini", "deepseek"],
        "paid_fallbacks": ["openai/gpt-oss-20b", "qwen/qwen3.7-flash"],
        "temperature": 0.1,
        "max_tokens": 128,
    },
    "role_guidance": {
        "preferred_family_order": ["qwen", "gemini", "deepseek"],
        "paid_fallbacks": ["qwen/qwen3.7-flash", "mistralai/mistral-nemo"],
        "temperature": 0.2,
        "max_tokens": 96,
    },
    "role_vision": {
        "preferred_family_order": ["qwen", "gemini", "deepseek"],
        "paid_fallbacks": ["google/gemini-flash-vision-paid", "mistralai/mistral-nemo"],
        "temperature": 0.1,
        "max_tokens": 384,
    },
}

PAID_NEMO = "mistralai/mistral-nemo"
PAID_LING = "inclusionai/ling-3.0-flash"
FREE_QWEN = "qwen/qwen3-free-test"
FREE_GEMINI = "google/gemini-flash-test"
FREE_DEEPSEEK = "deepseek/deepseek-chat-test"
FREE_OTHER_SMALL = "acme/tiny-free"
FREE_OTHER_LARGE = "acme/huge-free"


def api_model(
    model_id: str,
    prompt: str,
    completion: str,
    ctx: int | None = 8192,
    name: str | None = None,
    created: int = 1,
    input_mod: list[str] | None = None,
    output_mod: list[str] | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": model_id,
        "name": name or model_id,
        "created": created,
        "pricing": {"prompt": prompt, "completion": completion},
        "architecture": {
            "input_modalities": input_mod or ["text"],
            "output_modalities": output_mod or ["text"],
        },
    }
    if ctx is not None:
        entry["context_length"] = ctx
    return entry


def default_catalog() -> list[dict[str, Any]]:
    return [
        api_model(FREE_QWEN, "0", "0", 32768, name="Qwen Free"),
        api_model(FREE_GEMINI, "0", "0", 1000000, name="Gemini Free"),
        api_model(FREE_DEEPSEEK, "0", "0", 64000, name="DeepSeek Free"),
        api_model(FREE_OTHER_SMALL, "0", "0", 4096, name="Tiny"),
        api_model(FREE_OTHER_LARGE, "0", "0", 200000, name="Huge"),
        api_model(PAID_NEMO, "0.000000019", "0.00000003", 131072, name="Mistral Nemo"),
        api_model(PAID_LING, "0.000000021", "0.000000063", 262144, name="Ling Flash"),
        api_model("openai/gpt-oss-20b", "0.00000003", "0.00000012", 131072),
        api_model("qwen/qwen3.7-flash", "0.00000003", "0.00000013", 1000000),
        api_model("google/gemma-4-31b-it:free", "0", "0", 262144, name="Gemma"),
        api_model("broken/no-price", "not-a-number", "0", 8000),
        api_model("google/lyria-free", "0", "0", 8000, output_mod=["audio"]),
    ]


class FakeOpenRouter:
    def __init__(self, catalog: list[dict[str, Any]] | None = None) -> None:
        self.catalog = list(catalog if catalog is not None else default_catalog())
        self.models_calls = 0
        self.chat_calls: list[dict[str, Any]] = []
        self.chat_status: dict[str, int] = {}
        self.chat_body: dict[str, Any] = {}
        self.fail_models = False
        self.models_status = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith(MODELS_URL) and request.method == "GET":
            self.models_calls += 1
            if self.fail_models:
                return httpx.Response(503, json={"error": {"message": "unavailable"}})
            if self.models_status in {401, 403}:
                return httpx.Response(self.models_status, json={"error": {"message": "auth"}})
            return httpx.Response(self.models_status, json={"data": self.catalog})
        if url.startswith(CHAT_URL) and request.method == "POST":
            payload = json.loads(request.content.decode("utf-8"))
            self.chat_calls.append(payload)
            model_id = payload["model"]
            status = self.chat_status.get(model_id, 200)
            if status != 200:
                return httpx.Response(status, json={"error": {"message": f"status {status}"}})
            body = self.chat_body.get(
                model_id,
                {
                    "id": "gen-1",
                    "model": model_id,
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": f"ok:{model_id}"},
                        }
                    ],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25},
                },
            )
            return httpx.Response(200, json=body)
        return httpx.Response(404, json={"error": {"message": "not found"}})


def make_router(
    tmp_path: Path,
    fake: FakeOpenRouter,
    *,
    budget: str | Decimal | None = Decimal("3"),
    catalog_preload: dict[str, CatalogModel] | None = None,
) -> ModelRouter:
    client = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    router = ModelRouter(
        api_key="sk-or-test",
        budget_ceiling=None if budget is None else Decimal(str(budget)),
        roles_config=ROLES,
        runtime_dir=tmp_path,
        client=client,
        timeout_seconds=5,
        max_attempts=6,
        max_free_attempts=3,
        per_model_retries=0,
        circuit_failures=3,
        circuit_cooldown_s=30,
    )
    if catalog_preload is not None:
        router._catalog = catalog_preload
        router._catalog_loaded = True
        router._catalog_source = "test"
    return router


def run(coro):
    return asyncio.run(coro)


MESSAGES = [{"role": "user", "content": "hello"}]


def test_parse_price_numeric_not_lexicographic():
    assert parse_price("0") == Decimal("0")
    assert parse_price("0.0") == Decimal("0")
    assert parse_price("1e-8") == Decimal("1e-8")
    assert parse_price("not-a-number") is None
    assert parse_price("-1") is None


def test_free_status_requires_both_prices_zero():
    free = catalog_model_from_api(api_model("a/b", "0", "0"))
    paid_prompt = catalog_model_from_api(api_model("a/c", "0.0001", "0"))
    paid_out = catalog_model_from_api(api_model("a/d", "0", "0.0001"))
    assert free is not None and free.is_free
    assert paid_prompt is not None and not paid_prompt.is_free and paid_prompt.is_paid
    assert paid_out is not None and not paid_out.is_free and paid_out.is_paid


def test_malformed_pricing_is_ineligible_not_free():
    model = catalog_model_from_api(api_model("broken/x", "abc", "0"))
    assert model is not None
    assert not model.is_free
    assert not model.is_paid


def test_colon_free_suffix_is_not_authoritative():
    model = catalog_model_from_api(api_model("vendor/model:free", "0.0000001", "0"))
    assert model is not None
    assert not model.is_free


def _ids(router: ModelRouter, role: str = "role_fast") -> list[str]:
    return [m.id for m in router._free_chain(role)]


def test_qwen_preferred_over_gemini_and_deepseek(tmp_path: Path):
    fake = FakeOpenRouter()
    router = make_router(tmp_path, fake)
    run(router.ensure_catalog())
    assert _ids(router)[0] == FREE_QWEN
    run(router.aclose())


def test_gemini_when_no_free_qwen(tmp_path: Path):
    fake = FakeOpenRouter([m for m in default_catalog() if m["id"] != FREE_QWEN])
    router = make_router(tmp_path, fake)
    run(router.ensure_catalog())
    assert _ids(router)[0] == FREE_GEMINI
    run(router.aclose())


def test_deepseek_when_no_qwen_or_gemini(tmp_path: Path):
    drop = {FREE_QWEN, FREE_GEMINI}
    fake = FakeOpenRouter([m for m in default_catalog() if m["id"] not in drop])
    router = make_router(tmp_path, fake)
    run(router.ensure_catalog())
    assert _ids(router)[0] == FREE_DEEPSEEK
    run(router.aclose())


def test_generic_free_prefers_largest_context(tmp_path: Path):
    catalog = [
        api_model(FREE_OTHER_SMALL, "0", "0", 4096),
        api_model(FREE_OTHER_LARGE, "0", "0", 200000),
        api_model("google/gemma-4-31b-it:free", "0", "0", 26214),
        api_model(PAID_NEMO, "0.000000019", "0.00000003", 131072),
    ]
    fake = FakeOpenRouter(catalog)
    router = make_router(tmp_path, fake)
    run(router.ensure_catalog())
    assert _ids(router)[0] == FREE_OTHER_LARGE
    run(router.aclose())


def test_gemma_is_not_gemini_family(tmp_path: Path):
    fake = FakeOpenRouter(
        [
            api_model("google/gemma-4-31b-it:free", "0", "0", 8000, name="Gemma 4"),
            api_model(FREE_OTHER_LARGE, "0", "0", 200000),
        ]
    )
    router = make_router(tmp_path, fake)
    run(router.ensure_catalog())
    chain = router._free_chain("role_fast")
    assert chain[0].id == FREE_OTHER_LARGE
    run(router.aclose())


def test_lyria_audio_not_in_free_text_pool(tmp_path: Path):
    fake = FakeOpenRouter([api_model("google/lyria-free", "0", "0", 8000, output_mod=["audio"])])
    router = make_router(tmp_path, fake)
    run(router.ensure_catalog())
    assert _ids(router) == []
    run(router.aclose())


def test_live_catalog_wins_over_stale_free_cache(tmp_path: Path):
    stale = CatalogModel(
        id=FREE_QWEN,
        name="was free",
        context_length=8000,
        prompt_price=Decimal("0"),
        completion_price=Decimal("0"),
    )
    cache = {
        "version": 1,
        "models": [stale.model_dump(mode="json")],
        "free_ids": [FREE_QWEN],
        "role_picks": {},
    }
    (tmp_path / "models_cache.json").write_text(json.dumps(cache), encoding="utf-8")
    live = default_catalog()
    for entry in live:
        if entry["id"] == FREE_QWEN:
            entry["pricing"] = {"prompt": "0.0000001", "completion": "0.0000001"}
    fake = FakeOpenRouter(live)
    router = make_router(tmp_path, fake)
    run(router.ensure_catalog())
    assert FREE_QWEN not in _ids(router)
    assert router._catalog[FREE_QWEN].is_paid
    run(router.aclose())


def test_discovery_writes_cache_once_per_run(tmp_path: Path):
    fake = FakeOpenRouter()
    router = make_router(tmp_path, fake)
    result = run(router.call_model("role_fast", MESSAGES))
    result2 = run(router.call_model("role_guidance", MESSAGES))
    assert fake.models_calls == 1
    assert router.cache_path.exists()
    assert result.model == FREE_QWEN
    assert result2.model == FREE_QWEN
    assert not (tmp_path / "models_cache.json.tmp").exists()
    run(router.aclose())


def test_discovery_failure_uses_valid_cache(tmp_path: Path):
    fake_ok = FakeOpenRouter()
    router = make_router(tmp_path, fake_ok)
    run(router.ensure_catalog())
    run(router.aclose())

    fake_down = FakeOpenRouter()
    fake_down.fail_models = True
    router2 = make_router(tmp_path, fake_down)
    run(router2.ensure_catalog())
    assert router2._catalog_source == "cache"
    assert FREE_QWEN in router2._catalog
    run(router2.aclose())


def test_corrupt_cache_is_ignored(tmp_path: Path):
    (tmp_path / "models_cache.json").write_text("{not-json", encoding="utf-8")
    fake = FakeOpenRouter()
    fake.fail_models = True
    router = make_router(tmp_path, fake)
    run(router.ensure_catalog())
    assert router._catalog == {}
    run(router.aclose())


def test_free_429_falls_back_to_next_free(tmp_path: Path, caplog):
    fake = FakeOpenRouter()
    fake.chat_status[FREE_QWEN] = 429
    router = make_router(tmp_path, fake)
    with caplog.at_level(logging.INFO, logger="sentinelloop.model_router"):
        result = run(router.call_model("role_fast", MESSAGES))
    assert result.model == FREE_GEMINI
    assert result.paid is False
    assert result.fallback_used is True
    assert FREE_QWEN in result.attempted_models
    assert "rate limited" in caplog.text
    run(router.aclose())


def test_all_free_fail_uses_cheapest_paid(tmp_path: Path):
    fake = FakeOpenRouter()
    for model_id in (
        FREE_QWEN,
        FREE_GEMINI,
        FREE_DEEPSEEK,
        FREE_OTHER_SMALL,
        FREE_OTHER_LARGE,
        "google/gemma-4-31b-it:free",
    ):
        fake.chat_status[model_id] = 503
    router = make_router(tmp_path, fake, budget=Decimal("3"))
    result = run(router.call_model("role_fast", MESSAGES))
    assert result.paid is True
    assert result.model == PAID_NEMO
    assert result.estimated_cost_usd > 0
    run(router.aclose())


def test_paid_below_budget_allowed(tmp_path: Path):
    fake = FakeOpenRouter([api_model(PAID_NEMO, "0.000000019", "0.00000003", 131072)])
    router = make_router(tmp_path, fake, budget=Decimal("1"))
    result = run(router.call_model("role_fast", MESSAGES))
    assert result.paid is True
    assert result.budget_limited is False
    run(router.aclose())


def test_would_exceed_budget_sets_budget_limited(tmp_path: Path):
    fake = FakeOpenRouter(
        [
            api_model("free/a", "0", "0", 4000),
            api_model("free/b", "0", "0", 3000),
            api_model("free/c", "0", "0", 2000),
            api_model("free/d", "0", "0", 1000),
            api_model(PAID_NEMO, "0.000000019", "0.00000003", 131072),
        ]
    )
    fake.chat_status["free/a"] = 429
    fake.chat_status["free/b"] = 429
    fake.chat_status["free/c"] = 429
    router = make_router(tmp_path, fake, budget=Decimal("0"))
    result = run(router.call_model("role_fast", MESSAGES))
    assert result.budget_limited is True
    assert result.paid is False
    assert result.model == "free/d"
    assert all(call["model"] != PAID_NEMO for call in fake.chat_calls)
    run(router.aclose())


def test_exact_budget_boundary_allowed_if_not_exceeding(tmp_path: Path):
    # Preflight: max(16, chars/4) prompt tokens + max_tokens completion tokens.
    # 16 * 0.001 + 1 * 0.001 = 0.017 — allowed when it does not exceed the ceiling.
    fake = FakeOpenRouter([api_model(PAID_NEMO, "0.001", "0.001", 8000)])
    fake.chat_body[PAID_NEMO] = {
        "id": "gen-1",
        "model": PAID_NEMO,
        "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}],
        "usage": {"prompt_tokens": 16, "completion_tokens": 1, "total_tokens": 17},
    }
    router = make_router(tmp_path, fake, budget=Decimal("0.017"))
    result = run(router.call_model("role_fast", MESSAGES, max_tokens=1))
    assert result.paid is True
    assert result.estimated_cost_usd == Decimal("0.017")
    run(router.aclose())


def test_budget_already_exhausted_skips_paid(tmp_path: Path):
    fake = FakeOpenRouter(
        [
            api_model(FREE_QWEN, "0", "0", 8000),
            api_model(PAID_NEMO, "0.000000019", "0.00000003", 131072),
        ]
    )
    fake.chat_status[FREE_QWEN] = 500
    router = make_router(tmp_path, fake, budget=Decimal("0.01"))
    run(router.ensure_catalog())
    router._cumulative = Decimal("0.01")
    result = run(router.call_model("role_fast", MESSAGES))
    assert all(call["model"] != PAID_NEMO for call in fake.chat_calls)
    assert result.budget_limited is True
    run(router.aclose())


def test_missing_budget_disables_paid_not_unlimited(tmp_path: Path):
    fake = FakeOpenRouter(
        [
            api_model(FREE_QWEN, "0", "0", 8000),
            api_model(PAID_NEMO, "0.000000019", "0.00000003", 131072),
        ]
    )
    fake.chat_status[FREE_QWEN] = 429
    router = make_router(tmp_path, fake, budget=None)
    result = run(router.call_model("role_fast", MESSAGES))
    assert all(call["model"] != PAID_NEMO for call in fake.chat_calls)
    assert result.paid is False
    run(router.aclose())


def test_invalid_budget_env_is_config_error(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_BUDGET_CEILING_USD", "not-a-number")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    fake = FakeOpenRouter()
    client = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    with pytest.raises(ModelRouterConfigError):
        ModelRouter.from_project(runtime_dir=tmp_path, client=client)
    run(client.aclose())


def test_cost_calculation_uses_per_token_prices(tmp_path: Path):
    fake = FakeOpenRouter([api_model(PAID_NEMO, "0.000000019", "0.00000003", 131072)])
    fake.chat_body[PAID_NEMO] = {
        "id": "gen-1",
        "model": PAID_NEMO,
        "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
    }
    router = make_router(tmp_path, fake, budget=Decimal("1"))
    result = run(router.call_model("role_fast", MESSAGES))
    expected = Decimal("100") * Decimal("0.000000019") + Decimal("10") * Decimal("0.00000003")
    assert result.estimated_cost_usd == expected
    run(router.aclose())


def test_ledger_starts_zero_paid_increments_free_does_not(tmp_path: Path):
    fake = FakeOpenRouter()
    router = make_router(tmp_path, fake, budget=Decimal("3"))
    free_result = run(router.call_model("role_fast", MESSAGES))
    assert free_result.estimated_cost_usd == Decimal("0")
    assert router._cumulative == Decimal("0")
    fake.chat_status[FREE_QWEN] = 429
    fake.chat_status[FREE_GEMINI] = 429
    fake.chat_status[FREE_DEEPSEEK] = 429
    fake.chat_status[FREE_OTHER_SMALL] = 429
    fake.chat_status[FREE_OTHER_LARGE] = 429
    fake.chat_status["google/gemma-4-31b-it:free"] = 429
    paid = run(router.call_model("role_fast", MESSAGES))
    assert paid.paid is True
    assert router._cumulative > 0
    persisted = json.loads(router.ledger_path.read_text(encoding="utf-8"))
    assert Decimal(persisted["cumulative_spend_usd"]) == router._cumulative
    run(router.aclose())

    fake2 = FakeOpenRouter()
    router2 = make_router(tmp_path, fake2, budget=Decimal("3"))
    assert router2._cumulative == router._cumulative
    run(router2.aclose())


def test_corrupt_ledger_blocks_paid(tmp_path: Path):
    (tmp_path / "spend_ledger.json").write_text("{bad", encoding="utf-8")
    fake = FakeOpenRouter(
        [
            api_model(FREE_QWEN, "0", "0", 8000),
            api_model(PAID_NEMO, "0.000000019", "0.00000003", 131072),
        ]
    )
    fake.chat_status[FREE_QWEN] = 429
    router = make_router(tmp_path, fake, budget=Decimal("3"))
    result = run(router.call_model("role_fast", MESSAGES))
    assert all(call["model"] != PAID_NEMO for call in fake.chat_calls)
    assert result.budget_limited is True
    run(router.aclose())


def test_unknown_role_fails(tmp_path: Path):
    fake = FakeOpenRouter()
    router = make_router(tmp_path, fake)
    with pytest.raises(ModelRouterConfigError):
        run(router.call_model("role_super_magic", MESSAGES))
    run(router.aclose())


def test_all_three_roles_accepted(tmp_path: Path):
    fake = FakeOpenRouter()
    router = make_router(tmp_path, fake)
    for role in ("role_fast", "role_reasoning", "role_guidance"):
        result = run(router.call_model(role, MESSAGES))
        assert result.role == role
        assert result.model == FREE_QWEN
    run(router.aclose())


def test_kwargs_cannot_override_model_or_budget(tmp_path: Path):
    fake = FakeOpenRouter()
    router = make_router(tmp_path, fake)
    result = run(
        call_model(
            "role_fast",
            MESSAGES,
            _router=router,
            model="openai/gpt-4o",
            api_key="sk-evil",
            base_url="https://evil.example",
            temperature=0.9,
        )
    )
    assert fake.chat_calls[0]["model"] == FREE_QWEN
    assert fake.chat_calls[0]["temperature"] == 0.9
    assert "api_key" not in fake.chat_calls[0]
    assert result.model == FREE_QWEN
    run(router.aclose())
    reset_router()


def test_successful_call_logs_role_model_tier(tmp_path: Path, caplog):
    fake = FakeOpenRouter()
    router = make_router(tmp_path, fake)
    with caplog.at_level(logging.INFO, logger="sentinelloop.model_router"):
        run(router.call_model("role_fast", MESSAGES))
    assert "role=role_fast" in caplog.text
    assert FREE_QWEN in caplog.text
    assert "tier=FREE" in caplog.text
    assert "sk-or-test" not in caplog.text
    assert "hello" not in caplog.text
    run(router.aclose())


def test_auth_failure_does_not_cycle_models(tmp_path: Path):
    fake = FakeOpenRouter()
    fake.chat_status[FREE_QWEN] = 401
    router = make_router(tmp_path, fake)
    with pytest.raises(ModelRouterAuthError):
        run(router.call_model("role_fast", MESSAGES))
    assert len(fake.chat_calls) == 1
    run(router.aclose())


def test_paid_missing_usage_is_conservative(tmp_path: Path):
    fake = FakeOpenRouter([api_model(PAID_NEMO, "0.000000019", "0.00000003", 131072)])
    fake.chat_body[PAID_NEMO] = {
        "id": "gen-1",
        "model": PAID_NEMO,
        "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}],
    }
    router = make_router(tmp_path, fake, budget=Decimal("1"))
    result = run(router.call_model("role_fast", MESSAGES, max_tokens=10))
    assert result.paid is True
    assert result.estimated_cost_usd > Decimal("0")
    run(router.aclose())


def test_free_missing_usage_still_succeeds_zero_cost(tmp_path: Path):
    fake = FakeOpenRouter()
    fake.chat_body[FREE_QWEN] = {
        "id": "gen-1",
        "model": FREE_QWEN,
        "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}],
    }
    router = make_router(tmp_path, fake)
    result = run(router.call_model("role_fast", MESSAGES))
    assert result.content == "ok"
    assert result.estimated_cost_usd == Decimal("0")
    run(router.aclose())


def test_configured_missing_paid_fallback_is_skipped(tmp_path: Path, caplog):
    fake = FakeOpenRouter([api_model(FREE_QWEN, "0", "0", 8000)])
    router = make_router(tmp_path, fake)
    with caplog.at_level(logging.WARNING, logger="sentinelloop.model_router"):
        run(router.ensure_catalog())
        assert router._paid_chain("role_fast", {"text"}) == []
    assert "not present in current OpenRouter catalog" in caplog.text
    run(router.aclose())


def test_diagnostics_has_no_secrets(tmp_path: Path):
    fake = FakeOpenRouter()
    router = make_router(tmp_path, fake)
    run(router.ensure_catalog())
    diag = router.diagnostics()
    blob = json.dumps(diag)
    assert "sk-or" not in blob
    assert diag["catalog_loaded"] is True
    run(router.aclose())


def test_invalid_messages(tmp_path: Path):
    fake = FakeOpenRouter()
    router = make_router(tmp_path, fake)
    with pytest.raises(ModelRouterConfigError):
        run(router.call_model("role_fast", []))
    run(router.aclose())


def test_image_content_without_compatible_model_errors(tmp_path: Path):
    fake = FakeOpenRouter([api_model(FREE_QWEN, "0", "0", 8000, input_mod=["text"], output_mod=["text"])])
    router = make_router(tmp_path, fake)
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "see photo"},
                {"type": "image_url", "image_url": {"url": "https://example.com/x.png"}},
            ],
        }
    ]
    with pytest.raises(ModelRouterError):
        run(router.call_model("role_fast", messages))
    run(router.aclose())


def test_successful_call_appends_recent_calls(tmp_path: Path):
    fake = FakeOpenRouter()
    router = make_router(tmp_path, fake)
    run(router.call_model("role_fast", MESSAGES))
    ledger = json.loads((tmp_path / "spend_ledger.json").read_text(encoding="utf-8"))
    assert ledger["recent_calls"]
    entry = ledger["recent_calls"][-1]
    assert entry["model_role"] == "role_fast"
    assert entry["model"]
    assert "api_key" not in entry
    run(router.aclose())


def test_openrouter_budget_ceiling_blocks_paid_when_ledger_exceeds_limit(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_BUDGET_CEILING_USD", "0.01")
    fake = FakeOpenRouter(
        [
            api_model(FREE_QWEN, "0", "0", 8000),
            api_model(PAID_NEMO, "0.000000019", "0.00000003", 131072),
        ]
    )
    fake.chat_status[FREE_QWEN] = 500
    router = make_router(tmp_path, fake, budget=Decimal("0.01"))
    run(router.ensure_catalog())
    router._cumulative = Decimal("0.02")
    result = run(router.call_model("role_fast", MESSAGES))
    assert result.paid is False
    assert result.budget_limited is True
    assert all(call["model"] != PAID_NEMO for call in fake.chat_calls)
    run(router.aclose())


def test_budget_fallback_returns_clean_response_when_paid_blocked(tmp_path: Path):
    fake = FakeOpenRouter(
        [
            api_model(FREE_QWEN, "0", "0", 8000),
            api_model(PAID_NEMO, "0.000000019", "0.00000003", 131072),
        ]
    )
    fake.chat_body[FREE_QWEN] = {
        "id": "gen-fallback",
        "model": FREE_QWEN,
        "choices": [
            {"finish_reason": "stop", "message": {"role": "assistant", "content": "Stay clear of the hazard."}}
        ],
        "usage": {"prompt_tokens": 8, "completion_tokens": 6, "total_tokens": 14},
    }
    router = make_router(tmp_path, fake, budget=Decimal("0"))
    result = run(router.call_model("role_fast", MESSAGES))
    assert result.paid is False
    assert result.content
    assert "Stay clear of the hazard." in result.content
    assert result.error is None or result.budget_limited is True
    run(router.aclose())


FREE_VISION = "qwen/qwen-vl-free-test"
PAID_VISION = "google/gemini-flash-vision-paid"
VISION_MESSAGES = [
    {"role": "system", "content": "Analyze this workplace safety image."},
    {
        "role": "user",
        "content": [
            {"type": "text", "text": "analyze"},
            {"type": "image_url", "image_url": {"url": "https://example.com/panel.jpg"}},
        ],
    },
]


def test_architecture_input_modalities_marks_vision():
    model = catalog_model_from_api(
        api_model("vl/free", "0", "0", 4096, input_mod=["text", "image"], output_mod=["text"])
    )
    assert model is not None
    assert model.supports_vision()


def test_architecture_modality_string_text_plus_image():
    model = catalog_model_from_api(
        {
            "id": "vl/string",
            "pricing": {"prompt": "0", "completion": "0"},
            "architecture": {"modality": "text+image->text"},
        }
    )
    assert model is not None
    assert "image" in {item.lower() for item in model.input_modalities}
    assert model.supports_vision()


def test_role_fast_still_prefers_qwen_when_vision_model_present(tmp_path: Path):
    fake = FakeOpenRouter(
        default_catalog() + [api_model(FREE_VISION, "0", "0", 8192, name="Qwen VL", input_mod=["text", "image"])]
    )
    router = make_router(tmp_path, fake)
    result = run(router.call_model("role_fast", MESSAGES))
    assert result.model == FREE_QWEN
    run(router.aclose())


def test_vision_prefers_free_vision_model(tmp_path: Path, caplog):
    caplog.set_level(logging.INFO)
    fake = FakeOpenRouter(
        default_catalog()
        + [
            api_model(FREE_VISION, "0", "0", 8192, name="Qwen VL Free", input_mod=["text", "image"]),
            api_model(
                PAID_VISION, "0.00000002", "0.00000004", 8192, name="Gemini VL Paid", input_mod=["text", "image"]
            ),
        ]
    )
    router = make_router(tmp_path, fake)
    result = run(router.call_model("role_vision", VISION_MESSAGES))
    assert result.model == FREE_VISION
    assert result.paid is False
    assert "vision_model_selected" in caplog.text
    assert "sk-or-test" not in caplog.text
    run(router.aclose())


def test_vision_paid_fallback_respects_budget_ceiling(tmp_path: Path, caplog):
    caplog.set_level(logging.INFO)
    fake = FakeOpenRouter(
        [
            api_model(
                PAID_VISION, "0.00000002", "0.00000004", 8192, name="Gemini VL Paid", input_mod=["text", "image"]
            ),
        ]
    )
    router = make_router(tmp_path, fake, budget=Decimal("0"))
    result = run(router.call_model("role_vision", VISION_MESSAGES))
    assert result.paid is False
    assert result.budget_limited is True
    assert all(call["model"] != PAID_VISION for call in fake.chat_calls)
    assert "vision_budget_blocked" in caplog.text
    run(router.aclose())


def test_vision_uses_cheapest_paid_when_no_free_vision(tmp_path: Path, caplog):
    caplog.set_level(logging.INFO)
    dear = "meta/llama-vision-paid"
    fake = FakeOpenRouter(
        [
            api_model(FREE_QWEN, "0", "0", 32768),
            api_model(PAID_VISION, "0.00000001", "0.00000002", 8192, input_mod=["text", "image"]),
            api_model(dear, "0.00000009", "0.00000009", 8192, input_mod=["text", "image"]),
        ]
    )
    router = make_router(tmp_path, fake, budget=Decimal("3"))
    result = run(router.call_model("role_vision", VISION_MESSAGES))
    assert result.paid is True
    assert result.model == PAID_VISION
    assert "vision_model_selected" in caplog.text or "vision_model_fallback" in caplog.text
    run(router.aclose())


@pytest.mark.skipif(os.environ.get("SENTINELLOOP_LIVE_OPENROUTER") != "1", reason="opt-in live OpenRouter smoke test")
def test_live_openrouter_smoke():
    """Opt-in: SENTINELLOOP_LIVE_OPENROUTER=1. May call a free model."""
    reset_router()
    router = ModelRouter.from_project()
    try:
        result = run(router.call_model("role_fast", [{"role": "user", "content": "Reply with the single word: ok"}]))
        print("live smoke", result.model, result.paid, result.content)
        assert result.error is None or result.content
    finally:
        run(router.aclose())
        reset_router()
