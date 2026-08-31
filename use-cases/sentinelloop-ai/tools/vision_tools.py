"""Workplace image suggestions. Never official classification or risk.

Vision output is a suggestion only. Worker text, extracted fields, and
deterministic rules remain higher priority. No LLM usage except through
``model_router.call_model(role="role_vision")``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from guardrails.input_validation import validate_media_input
from tools.model_router import ROLE_VISION, ModelCallResult, call_model

log = logging.getLogger("sentinelloop.vision")

CallModelFn = Callable[..., Awaitable[ModelCallResult]]

HAZARD_CATEGORIES = (
    "electrical",
    "fire/smoke",
    "chemical",
    "machine",
    "slip/trip",
    "missing PPE",
    "structural",
    "unsafe behaviour",
    "other",
)
CATEGORY_ALIASES = {
    "electric": "electrical",
    "electrical": "electrical",
    "electricity": "electrical",
    "fire": "fire/smoke",
    "smoke": "fire/smoke",
    "fire/smoke": "fire/smoke",
    "chemical": "chemical",
    "machine": "machine",
    "machinery": "machine",
    "slip": "slip/trip",
    "trip": "slip/trip",
    "slip/trip": "slip/trip",
    "ppe": "missing PPE",
    "missing ppe": "missing PPE",
    "missing PPE": "missing PPE",
    "structural": "structural",
    "unsafe behaviour": "unsafe behaviour",
    "unsafe behavior": "unsafe behaviour",
    "other": "other",
}

SUPPORTED_MIME = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
TEXT_CONFIDENCE_LOW = 0.6
MAX_OBSERVATIONS = 3
_CACHE_TTL_S = 600.0
_MAX_CACHE = 64

_UNSAFE = (
    "repair it yourself",
    "fix it yourself",
    "bypass",
    "disable the guard",
    "turn off the supply yourself",
    "worker should repair",
    "self-maintenance",
    "ignore lockout",
    "skip the procedure",
    "evacuate immediately and fight",
    "touch the wire",
)

VISION_SYSTEM_PROMPT = """Analyze this workplace safety image.

Return JSON only. This is a SUGGESTION, not a final classification, emergency
decision, or risk level.

Do not give repair advice, worker self-maintenance steps, or instructions to
bypass safety procedures. Do not invent people, locations, or incidents that
are not visible.

Return:
{
  "hazard_category": "electrical|fire/smoke|chemical|machine|slip/trip|missing PPE|structural|unsafe behaviour|other",
  "confidence": 0.0,
  "observations": ["up to 3 short visual observations"]
}
"""

_STATS: dict[str, Any] = {
    "images_analyzed": 0,
    "high_confidence": 0,
    "medium_confidence": 0,
    "low_confidence": 0,
    "overrides": 0,
    "confidence_sum": 0.0,
    "free_calls": 0,
    "paid_calls": 0,
    "cost_sum": Decimal("0"),
    "by_category": {},
    "cache_hits": 0,
}

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


class VisionSuggestion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    hazard_category: str | None = None
    confidence: float = 0.0
    observations: list[str] = Field(default_factory=list)
    model_used: str | None = None
    timestamp: str
    rejected: bool = False
    reject_reason: str | None = None
    suggestion_only: bool = True
    paid: bool = False
    estimated_cost_usd: float = 0.0

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, number))


def reset_vision_stats() -> None:
    _STATS.update(
        {
            "images_analyzed": 0,
            "high_confidence": 0,
            "medium_confidence": 0,
            "low_confidence": 0,
            "overrides": 0,
            "confidence_sum": 0.0,
            "free_calls": 0,
            "paid_calls": 0,
            "cost_sum": Decimal("0"),
            "by_category": {},
            "cache_hits": 0,
        }
    )
    _CACHE.clear()


def vision_stats() -> dict[str, Any]:
    analyzed = int(_STATS["images_analyzed"]) or 0
    conf_sum = float(_STATS["confidence_sum"])
    paid = int(_STATS["paid_calls"])
    free = int(_STATS["free_calls"])
    total_calls = paid + free
    avg_cost = float(_STATS["cost_sum"]) / paid if paid else 0.0
    return {
        "images_analyzed": analyzed,
        "high_confidence_detections": int(_STATS["high_confidence"]),
        "human_overrides": int(_STATS["overrides"]),
        "average_confidence": round(conf_sum / analyzed, 2) if analyzed else 0.0,
        "confidence_distribution": {
            "high": int(_STATS["high_confidence"]),
            "medium": int(_STATS["medium_confidence"]),
            "low": int(_STATS["low_confidence"]),
        },
        "by_category": dict(_STATS["by_category"]),
        "model_usage": {
            "free_percent": round(100.0 * free / total_calls, 1) if total_calls else 0.0,
            "paid_percent": round(100.0 * paid / total_calls, 1) if total_calls else 0.0,
            "average_cost_usd": round(avg_cost, 6),
        },
        "cache_hits": int(_STATS["cache_hits"]),
    }


def image_hash(image_url_or_base64: str | bytes) -> str:
    if isinstance(image_url_or_base64, bytes):
        payload = image_url_or_base64
    else:
        payload = str(image_url_or_base64).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def confidence_band(confidence: float) -> str:
    pct = confidence * 100
    if pct >= 90:
        return "high"
    if pct >= 60:
        return "medium"
    return "low"


def normalize_vision_category(value: Any) -> str | None:
    if value is None or value == "":
        return None
    raw = str(value).strip().lower()
    mapped = CATEGORY_ALIASES.get(raw, raw)
    if mapped in HAZARD_CATEGORIES:
        return mapped
    return None


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_json(content: str | None) -> dict[str, Any]:
    if not content or not str(content).strip():
        raise ValueError("empty vision content")
    text = str(content).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("vision content is not JSON")
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("vision JSON must be an object")
    return data


def _contains_unsafe(text: str) -> bool:
    blob = text.lower()
    return any(token in blob for token in _UNSAFE)


def validate_vision_output(data: dict[str, Any] | None, *, model_used: str | None = None) -> VisionSuggestion:
    """Reject repair advice, worker instructions, and unsupported conclusions."""
    stamp = _utcnow()
    if not isinstance(data, dict):
        return VisionSuggestion(
            timestamp=stamp,
            model_used=model_used,
            rejected=True,
            reject_reason="missing observations",
        )
    category = normalize_vision_category(data.get("hazard_category") or data.get("category"))
    try:
        confidence = float(data.get("confidence") if data.get("confidence") is not None else 0)
    except (TypeError, ValueError):
        confidence = -1.0
    raw_obs = data.get("observations") or data.get("visual_observations") or []
    if isinstance(raw_obs, str):
        raw_obs = [raw_obs]
    if not isinstance(raw_obs, list):
        raw_obs = []
    observations = [str(item).strip() for item in raw_obs if str(item).strip()][:MAX_OBSERVATIONS]
    blob = " ".join([str(data.get("hazard_category") or ""), *observations])
    if confidence < 0 or confidence > 1:
        return VisionSuggestion(
            timestamp=stamp,
            model_used=model_used,
            rejected=True,
            reject_reason="confidence out of range",
        )
    if category is None:
        return VisionSuggestion(
            timestamp=stamp,
            model_used=model_used,
            rejected=True,
            reject_reason="invalid category",
        )
    if len(raw_obs) > MAX_OBSERVATIONS:
        observations = observations[:MAX_OBSERVATIONS]
    if not observations:
        return VisionSuggestion(
            timestamp=stamp,
            model_used=model_used,
            hazard_category=category,
            confidence=max(0.0, min(1.0, confidence)),
            rejected=True,
            reject_reason="missing observations",
        )
    if _contains_unsafe(blob):
        return VisionSuggestion(
            timestamp=stamp,
            model_used=model_used,
            hazard_category=category,
            confidence=max(0.0, min(1.0, confidence)),
            observations=observations,
            rejected=True,
            reject_reason="unsafe instructions",
        )
    return VisionSuggestion(
        hazard_category=category,
        confidence=max(0.0, min(1.0, confidence)),
        observations=observations,
        model_used=model_used,
        timestamp=stamp,
        rejected=False,
        suggestion_only=True,
    )


def validate_image_input(
    image_url_or_base64: str,
    *,
    mime_type: str | None = None,
    size_bytes: int | None = None,
    filename: str | None = None,
) -> tuple[bool, str | None]:
    raw = (image_url_or_base64 or "").strip()
    if not raw:
        return False, "empty image"
    lowered = raw.lower()
    name = (filename or "").lower()
    if any(name.endswith(suffix) for suffix in (".exe", ".bat", ".cmd", ".com", ".msi", ".js", ".dll", ".scr")):
        return False, "executable rejected"
    if lowered.startswith(("javascript:", "file:", "vbscript:")):
        return False, "unsafe url"
    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        suffix = ""
        if parsed.path:
            suffix = "." + parsed.path.rsplit(".", 1)[-1].lower() if "." in parsed.path.rsplit("/", 1)[-1] else ""
        if suffix and suffix not in SUPPORTED_SUFFIXES and suffix not in {".gif", ""}:
            if suffix in {".exe", ".bin", ".pdf"}:
                return False, "unsupported file type"
        check = validate_media_input(mime_type=mime_type, filename=filename, size_bytes=size_bytes, url=raw)
        if not check.approved:
            return False, check.violations[0] if check.violations else "invalid image url"
        return True, None
    mime = (mime_type or "").split(";")[0].strip().lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    if raw.startswith("data:"):
        header, _, rest = raw.partition(",")
        mime_match = re.match(r"data:([^;,]+)", header, re.I)
        declared = (mime_match.group(1).lower() if mime_match else mime).split(";")[0].strip()
        if declared == "image/jpg":
            declared = "image/jpeg"
        if declared not in SUPPORTED_MIME:
            return False, "unsupported image type"
        mime = declared
        try:
            payload = base64.b64decode(rest, validate=False)
        except Exception:
            return False, "malicious payload"
        if size_bytes is None:
            size_bytes = len(payload)
    else:
        try:
            payload = base64.b64decode(raw, validate=False)
        except Exception:
            return False, "malicious payload"
        if size_bytes is None:
            size_bytes = len(payload)
        if mime and mime not in SUPPORTED_MIME:
            return False, "unsupported image type"
    check = validate_media_input(
        mime_type=mime or "image/jpeg",
        filename=filename or "upload.jpg",
        size_bytes=size_bytes,
    )
    if not check.approved:
        return False, check.violations[0] if check.violations else "invalid image"
    return True, None


def _as_data_url(image_url_or_base64: str, mime_type: str | None) -> str:
    raw = image_url_or_base64.strip()
    if raw.startswith("http://") or raw.startswith("https://") or raw.startswith("data:"):
        return raw
    mime = (mime_type or "image/jpeg").split(";")[0].strip() or "image/jpeg"
    return f"data:{mime};base64,{raw}"


def _note_result(suggestion: VisionSuggestion, *, paid: bool, cost: Decimal) -> None:
    if suggestion.rejected:
        return
    _STATS["images_analyzed"] = int(_STATS["images_analyzed"]) + 1
    _STATS["confidence_sum"] = float(_STATS["confidence_sum"]) + float(suggestion.confidence)
    band = confidence_band(suggestion.confidence)
    _STATS[f"{band}_confidence"] = int(_STATS[f"{band}_confidence"]) + 1
    if paid:
        _STATS["paid_calls"] = int(_STATS["paid_calls"]) + 1
        _STATS["cost_sum"] = Decimal(str(_STATS["cost_sum"])) + cost
    else:
        _STATS["free_calls"] = int(_STATS["free_calls"]) + 1
    category = suggestion.hazard_category or "other"
    by_cat = dict(_STATS["by_category"])
    by_cat[category] = int(by_cat.get(category) or 0) + 1
    _STATS["by_category"] = by_cat


def vision_override_record(
    *,
    vision_category: str | None,
    final_category: str | None,
    reason: str | None = None,
    changed_by: str | None = None,
) -> dict[str, Any]:
    """Metadata for incident_updates. No new table."""
    overridden = bool(vision_category and final_category and vision_category != final_category)
    if overridden:
        _STATS["overrides"] = int(_STATS["overrides"]) + 1
    return {
        "vision_override": overridden,
        "override_reason": reason or ("Human changed vision suggestion" if overridden else None),
        "changed_by": changed_by or "safety_officer",
        "timestamp": _utcnow(),
        "vision_hazard_category": vision_category,
        "final_category": final_category,
    }


def empty_vision_result(*, reason: str, model_used: str | None = None) -> dict[str, Any]:
    return VisionSuggestion(
        timestamp=_utcnow(),
        model_used=model_used,
        rejected=True,
        reject_reason=reason,
    ).model_dump()


async def classify_hazard_image(
    image_url_or_base64: str,
    *,
    mime_type: str | None = None,
    filename: str | None = None,
    size_bytes: int | None = None,
    call_model_fn: CallModelFn | None = None,
) -> dict[str, Any]:
    """Suggest a hazard category from a workplace image. Suggestion only."""
    ok, error = validate_image_input(image_url_or_base64, mime_type=mime_type, filename=filename, size_bytes=size_bytes)
    if not ok:
        log.info("vision_image_rejected reason=%s", error)
        return empty_vision_result(reason=error or "invalid image")

    cache_key = image_hash(image_url_or_base64)
    hit = _CACHE.get(cache_key)
    now = time.monotonic()
    if hit is not None and now - hit[0] < _CACHE_TTL_S:
        _STATS["cache_hits"] = int(_STATS["cache_hits"]) + 1
        log.info("vision_cache_hit")
        return dict(hit[1])

    router = call_model_fn or call_model
    image_url = _as_data_url(image_url_or_base64, mime_type)
    messages = [
        {"role": "system", "content": VISION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Analyze this workplace safety image. Return possible hazard_category, confidence 0-1, and up to 3 short visual observations.",
                },
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        },
    ]
    try:
        routed = await router(role=ROLE_VISION, messages=messages, temperature=0.1, max_tokens=384)
    except Exception:
        log.warning("vision_model_failed")
        return empty_vision_result(reason="model failure")
    if routed.degraded or routed.error or not routed.content:
        log.info("vision_model_fallback reason=%s", routed.error or "empty")
        return empty_vision_result(reason=routed.error or "model failure", model_used=routed.model)
    try:
        parsed = _parse_json(routed.content)
    except Exception:
        log.warning("vision_model_parse_failed")
        return empty_vision_result(reason="model failure", model_used=routed.model)
    suggestion = validate_vision_output(parsed, model_used=routed.model)
    suggestion.paid = bool(routed.paid)
    try:
        suggestion.estimated_cost_usd = float(routed.estimated_cost_usd or 0)
    except (TypeError, ValueError):
        suggestion.estimated_cost_usd = 0.0
    payload = suggestion.model_dump()
    if not suggestion.rejected:
        _note_result(suggestion, paid=bool(routed.paid), cost=Decimal(str(routed.estimated_cost_usd or 0)))
        _CACHE[cache_key] = (now, payload)
        if len(_CACHE) > _MAX_CACHE:
            oldest = min(_CACHE, key=lambda key: _CACHE[key][0])
            _CACHE.pop(oldest, None)
        log.info(
            "vision_suggestion_created category=%s confidence=%s model=%s",
            suggestion.hazard_category,
            suggestion.confidence,
            suggestion.model_used,
        )
    else:
        log.info("vision_suggestion_rejected reason=%s", suggestion.reject_reason)
    return payload


def should_run_vision(
    *,
    has_image: bool,
    hazard_category: str | None,
    text_confidence: float,
    explicit_text_category: str | None,
    image_payload: str | None,
) -> bool:
    if not has_image or not image_payload:
        return False
    if explicit_text_category:
        return False
    if hazard_category and text_confidence >= TEXT_CONFIDENCE_LOW:
        return False
    return True
