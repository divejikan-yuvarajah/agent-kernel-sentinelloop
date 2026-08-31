"""Prevention agent: turn detected risk patterns into inspection recommendations.

The LLM may only rewrite a deterministic pattern into a short safety-team
note. It must not calculate risk, change scores, invent incidents, or
override forecast_tools. One ``role_reasoning`` call per flagged group.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tools.forecast_tools import TREND_INCREASING, detect_risk_patterns
from tools.model_router import ModelCallResult, call_model

log = logging.getLogger("sentinelloop.prevention")

ROLE_REASONING = "role_reasoning"
GENERATED_BY = "prevention_agent"

CallModelFn = Callable[..., Awaitable[ModelCallResult]]

_STATS = {
    "prevention_recommendation_created": 0,
    "prevention_model_calls": 0,
    "prevention_fallback": 0,
}

_UNSAFE = (
    "bypass",
    "disable the guard",
    "remove the guard",
    "repair it yourself",
    "fix it yourself",
    "worker should repair",
    "self-maintenance",
    "ignore lockout",
    "skip the procedure",
    "do not follow",
    "don't follow",
    "hot work without",
)

PREVENTION_SYSTEM_PROMPT = """You turn a workplace hazard PATTERN into one short prevention recommendation.

You do NOT calculate risk. You do NOT invent incidents. You do NOT change scores.
You do NOT recommend dangerous repairs, worker self-maintenance, or bypassing safety procedures.

Write for a safety supervisor. Allowed actions only:
- inspection
- training
- supervisor review
- maintenance checks scheduled by qualified staff

Return JSON only:
{
  "recommendation": "one or two sentences",
  "reason": "short reason using the supplied counts only",
  "confidence": 0.0
}

Do not add extra hazards, people, or places.
"""


class PreventionRecommendation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    location: str
    category: str = ""
    recommendation: str
    reason: str
    generated_by: str = GENERATED_BY
    confidence: float = 0.7
    trend: str = "stable"
    incident_count: int = 0
    risk_level: str | None = None
    reason_factors: list[str] = Field(default_factory=list)
    prediction_id: str | None = None

    @field_validator("confidence", mode="before")
    @classmethod
    def _validate_confidence(cls, value: object) -> float:
        return _clamp_confidence(value)


def _clamp_confidence(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.7
    return max(0.0, min(1.0, number))


def prevention_stats() -> dict[str, int]:
    return dict(_STATS)


def reset_prevention_stats() -> None:
    for key in _STATS:
        _STATS[key] = 0


def _unsafe(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in _UNSAFE)


def fallback_recommendation(pattern: dict[str, Any]) -> str:
    location = str(pattern.get("location") or "This location")
    category = str(pattern.get("category") or "hazard")
    count = int(pattern.get("incident_count") or 0)
    span = int(pattern.get("span_days") or 0) or 30
    trend = str(pattern.get("trend") or "stable")
    sentence = f"{location} has generated {count} {category} reports in {span} days"
    if trend == TREND_INCREASING:
        sentence += " with a shortening gap between incidents"
    sentence += ". Recommend inspection before the next shift."
    return sentence


def fallback_reason(pattern: dict[str, Any]) -> str:
    count = int(pattern.get("incident_count") or 0)
    return f"{count} related incidents detected"


def _confidence_from_pattern(pattern: dict[str, Any]) -> float:
    frequency = float(pattern.get("frequency_score") or 0)
    boost = 0.12 if pattern.get("trend") == TREND_INCREASING else 0.0
    if pattern.get("active_hazard"):
        boost += 0.06
    return round(min(0.99, 0.55 + min(frequency, 0.4) + boost), 2)


def _extract_json(text: str | None) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}


def _pattern_payload(pattern: dict[str, Any]) -> dict[str, Any]:
    return {
        "location": pattern.get("location"),
        "category": pattern.get("category"),
        "incident_count": pattern.get("incident_count"),
        "span_days": pattern.get("span_days"),
        "days_since_last": pattern.get("days_since_last"),
        "frequency_score": pattern.get("frequency_score"),
        "trend": pattern.get("trend"),
        "risk_level": pattern.get("risk_level"),
        "reason_factors": pattern.get("reason_factors") or [],
        "active_hazard": pattern.get("active_hazard"),
        "location_hotspot": pattern.get("location_hotspot"),
    }


async def recommend_for_pattern(
    pattern: dict[str, Any],
    *,
    call_model_fn: CallModelFn | None = None,
) -> PreventionRecommendation:
    """One reasoning call for this group. Never one call per incident."""
    router = call_model_fn or call_model
    location = str(pattern.get("location") or "Unknown location")
    category = str(pattern.get("category") or "uncategorized")
    fallback_text = fallback_recommendation(pattern)
    fallback_why = fallback_reason(pattern)
    confidence = _confidence_from_pattern(pattern)
    recommendation = fallback_text
    reason = fallback_why
    used_model = False
    try:
        _STATS["prevention_model_calls"] += 1
        result = await router(
            role=ROLE_REASONING,
            messages=[
                {"role": "system", "content": PREVENTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(_pattern_payload(pattern), ensure_ascii=True),
                },
            ],
        )
        parsed = _extract_json(getattr(result, "content", None))
        rec = str(parsed.get("recommendation") or "").strip()
        why = str(parsed.get("reason") or "").strip()
        if rec and not _unsafe(rec):
            recommendation = rec
            used_model = True
        if why and not _unsafe(why):
            reason = why
        if "confidence" in parsed:
            confidence = _clamp_confidence(parsed.get("confidence"))
        if getattr(result, "degraded", False) or getattr(result, "error", None):
            used_model = False
            recommendation = fallback_text
            reason = fallback_why
    except Exception:
        log.warning("prevention_model_failed location=%s category=%s", location, category)
        _STATS["prevention_fallback"] += 1
        recommendation = fallback_text
        reason = fallback_why
        used_model = False

    if not used_model:
        _STATS["prevention_fallback"] += 1

    if _unsafe(recommendation):
        recommendation = fallback_text
        reason = fallback_why

    item = PreventionRecommendation(
        location=location,
        category=category,
        recommendation=recommendation,
        reason=reason,
        generated_by=GENERATED_BY,
        confidence=confidence,
        trend=str(pattern.get("trend") or "stable"),
        incident_count=int(pattern.get("incident_count") or 0),
        risk_level=pattern.get("risk_level"),
        reason_factors=list(pattern.get("reason_factors") or []),
        prediction_id=pattern.get("prediction_id"),
    )
    _STATS["prevention_recommendation_created"] += 1
    log.info("prevention_recommendation_created location=%s category=%s", location, category)
    return item


async def generate_prevention_recommendations(
    patterns: list[dict[str, Any]],
    *,
    call_model_fn: CallModelFn | None = None,
    flagged_only: bool = True,
) -> list[PreventionRecommendation]:
    """Call the model once per flagged group, never once per incident."""
    selected = [row for row in patterns if (not flagged_only) or row.get("predicted_risk_zone")]
    results: list[PreventionRecommendation] = []
    for pattern in selected:
        results.append(await recommend_for_pattern(pattern, call_model_fn=call_model_fn))
    return results


async def prevent_from_incidents(
    incidents: list[Any],
    *,
    call_model_fn: CallModelFn | None = None,
) -> list[PreventionRecommendation]:
    patterns = detect_risk_patterns(incidents)
    return await generate_prevention_recommendations(patterns, call_model_fn=call_model_fn)


async def recommend_prevention_json(pattern_json: str) -> str:
    """Tool entry: one pattern in, one recommendation out."""
    try:
        pattern = json.loads(pattern_json) if pattern_json else {}
    except json.JSONDecodeError:
        pattern = {"location": "Unknown location", "incident_count": 0}
    if not isinstance(pattern, dict):
        pattern = {"location": "Unknown location", "incident_count": 0}
    result = await recommend_for_pattern(pattern)
    return result.model_dump_json()


def create_prevention_agent(*, model: Any = None, handoffs: list[Any] | None = None) -> Any:
    """Optional SDK wrapper. Not part of the WhatsApp six-agent handoff chain."""
    from agentkernel.openai import OpenAIToolBuilder

    from ak_bootstrap import pin_openai_agents_sdk

    pin_openai_agents_sdk()
    from agents import Agent  # type: ignore[attr-defined]

    tools = OpenAIToolBuilder.bind([recommend_prevention_json])
    kwargs: dict[str, Any] = {}
    if model is not None:
        kwargs["model"] = model
    if handoffs:
        kwargs["handoffs"] = handoffs
    return Agent(
        name="prevention_agent",
        handoff_description="Turns recurring hazard patterns into inspection recommendations.",
        instructions=(
            "You are prevention_agent. Call recommend_prevention_json with the pattern JSON. "
            "Return that JSON. Do not calculate risk or invent incidents. "
            "Never recommend worker self-repair or bypassing safety procedures."
        ),
        tools=tools,
        **kwargs,
    )
