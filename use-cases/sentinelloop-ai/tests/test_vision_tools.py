"""Vision tool tests. Model router is mocked. No live OpenRouter or image APIs."""

from __future__ import annotations

import asyncio
import json

from tools.model_router import ModelCallResult
from tools.vision_tools import (
    classify_hazard_image,
    reset_vision_stats,
    should_run_vision,
    validate_image_input,
    validate_vision_output,
    vision_stats,
)

IMAGE_URL = "https://cdn.example.com/workshop/panel.jpg"


def run(coro):
    return asyncio.run(coro)


class FakeVisionRouter:
    def __init__(
        self, payload: dict | None = None, *, error: Exception | None = None, result: ModelCallResult | None = None
    ) -> None:
        self.payload = payload
        self.error = error
        self.result = result
        self.calls: list[tuple] = []

    async def __call__(self, role: str = "", messages: list | None = None, **kwargs):
        self.calls.append((role, messages or [], kwargs))
        assert role == "role_vision"
        if self.error:
            raise self.error
        if self.result is not None:
            return self.result
        return ModelCallResult(
            content=json.dumps(self.payload or {}),
            model="mock/vision-free",
            role="role_vision",
            paid=False,
        )


def setup_function():
    reset_vision_stats()


def _valid_payload(**overrides) -> dict:
    data = {
        "hazard_category": "electrical",
        "confidence": 0.82,
        "observations": ["exposed wire visible", "damaged cable insulation", "worker near electrical panel"],
    }
    data.update(overrides)
    return data


def test_valid_response_returns_suggestion_only():
    router = FakeVisionRouter(_valid_payload())
    result = run(classify_hazard_image(IMAGE_URL, call_model_fn=router))
    assert result["rejected"] is False
    assert result["suggestion_only"] is True
    assert result["hazard_category"] == "electrical"
    assert result["confidence"] == 0.82
    assert len(result["observations"]) == 3
    assert result["model_used"] == "mock/vision-free"
    assert result["timestamp"]
    assert router.calls[0][0] == "role_vision"


def test_invalid_category_is_rejected():
    checked = validate_vision_output({"hazard_category": "laser", "confidence": 0.9, "observations": ["glow"]})
    assert checked.rejected is True
    assert checked.reject_reason == "invalid category"


def test_confidence_out_of_range_is_rejected():
    high = validate_vision_output(_valid_payload(confidence=1.5))
    low = validate_vision_output(_valid_payload(confidence=-0.2))
    assert high.rejected is True
    assert high.reject_reason == "confidence out of range"
    assert low.rejected is True
    assert low.reject_reason == "confidence out of range"


def test_missing_observations_are_rejected():
    checked = validate_vision_output({"hazard_category": "chemical", "confidence": 0.7, "observations": []})
    assert checked.rejected is True
    assert checked.reject_reason == "missing observations"


def test_observation_count_is_capped_at_three():
    checked = validate_vision_output(_valid_payload(observations=["a", "b", "c", "d"]))
    assert checked.rejected is False
    assert checked.observations == ["a", "b", "c"]


def test_unsafe_repair_advice_is_rejected():
    checked = validate_vision_output(_valid_payload(observations=["exposed wire", "repair it yourself"]))
    assert checked.rejected is True
    assert checked.reject_reason == "unsafe instructions"


def test_model_failure_falls_back_without_category():
    router = FakeVisionRouter(error=RuntimeError("model unavailable"))
    result = run(classify_hazard_image(IMAGE_URL, call_model_fn=router))
    assert result["rejected"] is True
    assert result["reject_reason"] == "model failure"
    assert result["hazard_category"] is None


def test_degraded_router_result_is_model_failure():
    router = FakeVisionRouter(
        result=ModelCallResult(
            content=None,
            model=None,
            role="role_vision",
            degraded=True,
            error="no_capacity",
        )
    )
    result = run(classify_hazard_image(IMAGE_URL, call_model_fn=router))
    assert result["rejected"] is True
    assert result["reject_reason"] == "no_capacity"


def test_cache_key_is_image_hash():
    router = FakeVisionRouter(_valid_payload())
    first = run(classify_hazard_image(IMAGE_URL, call_model_fn=router))
    second = run(classify_hazard_image(IMAGE_URL, call_model_fn=router))
    assert first["hazard_category"] == second["hazard_category"]
    assert len(router.calls) == 1
    assert vision_stats()["cache_hits"] == 1


def test_executables_and_unknown_types_are_rejected():
    ok, reason = validate_image_input("https://cdn.example.com/payload.exe", filename="payload.exe")
    assert ok is False
    assert reason

    ok, reason = validate_image_input("javascript:alert(1)")
    assert ok is False

    ok, reason = validate_image_input("data:application/octet-stream;base64,AAAA")
    assert ok is False
    assert "unsupported" in (reason or "")

    ok, reason = validate_image_input(IMAGE_URL, filename="panel.jpg", mime_type="image/jpeg")
    assert ok is True


def test_should_run_vision_skips_when_not_required():
    assert (
        should_run_vision(
            has_image=True,
            hazard_category=None,
            text_confidence=0.0,
            explicit_text_category=None,
            image_payload=IMAGE_URL,
        )
        is True
    )
    assert (
        should_run_vision(
            has_image=True,
            hazard_category="electrical",
            text_confidence=0.9,
            explicit_text_category="electrical",
            image_payload=IMAGE_URL,
        )
        is False
    )
    assert (
        should_run_vision(
            has_image=True,
            hazard_category="electrical",
            text_confidence=0.9,
            explicit_text_category=None,
            image_payload=IMAGE_URL,
        )
        is False
    )
    assert (
        should_run_vision(
            has_image=False,
            hazard_category=None,
            text_confidence=0.0,
            explicit_text_category=None,
            image_payload=IMAGE_URL,
        )
        is False
    )
