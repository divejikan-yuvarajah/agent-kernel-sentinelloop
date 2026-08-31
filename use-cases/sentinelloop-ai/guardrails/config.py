"""Load guardrail limits from config.yaml. Validators must not hard-code thresholds."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parents[1]
_CONFIG_PATH = _ROOT / "config.yaml"

_DEFAULT_MEDIA = (
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/heic",
    "image/heif",
)
_DEFAULT_FORBIDDEN = (".exe", ".bat", ".cmd", ".com", ".msi", ".js", ".vbs", ".ps1", ".scr", ".dll")


@lru_cache(maxsize=1)
def load_guardrail_config(path: str | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else _CONFIG_PATH
    raw: dict[str, Any] = {}
    if config_path.is_file():
        with config_path.open(encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        if isinstance(loaded, dict):
            raw = loaded
    intake = raw.get("intake") if isinstance(raw.get("intake"), dict) else {}
    guardrails = raw.get("guardrails") if isinstance(raw.get("guardrails"), dict) else {}
    media = guardrails.get("allowed_media_types") or list(_DEFAULT_MEDIA)
    suffixes = guardrails.get("forbidden_media_suffixes") or list(_DEFAULT_FORBIDDEN)
    max_text = guardrails.get("max_text_length")
    if max_text is None:
        max_text = intake.get("max_text_length")
    return {
        "max_text_length": int(max_text or 4000),
        "max_metadata_bytes": int(guardrails.get("max_metadata_bytes") or 16384),
        "max_attachment_bytes": int(guardrails.get("max_attachment_bytes") or 10485760),
        "guidance_similarity_min": float(guardrails.get("guidance_similarity_min") or 0.52),
        "guidance_jaccard_min": float(guardrails.get("guidance_jaccard_min") or 0.45),
        "budget_warning_ratio": float(guardrails.get("budget_warning_ratio") or 0.8),
        "event_buffer_size": int(guardrails.get("event_buffer_size") or 500),
        "allowed_media_types": tuple(str(item).lower() for item in media),
        "forbidden_media_suffixes": tuple(str(item).lower() for item in suffixes),
        "anonymous_data_policy": "strip_personal_identifiers",
        "closure_rules": "high_critical_require_slack_closed",
        "guidance_validation_strictness": "knowledge_base_grounded",
    }


def reset_guardrail_config_cache() -> None:
    load_guardrail_config.cache_clear()
