"""Judge/demo flags. Never reads secrets; only checks DEMO_MODE."""

from __future__ import annotations

import os

PIPELINE_VERSION = "sentinelloop-pipeline-v1"

HAZARD_CATEGORIES = (
    "Electrical",
    "Fire/Smoke",
    "Chemical",
    "Machine",
    "Slip/Trip",
    "Missing PPE",
    "Structural",
    "Unsafe Behaviour",
    "Other",
)

ALLOWED_PHOTO_TYPES = frozenset({"image/jpeg", "image/jpg", "image/png", "image/webp"})
ALLOWED_PHOTO_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp"})


def demo_mode_enabled() -> bool:
    return os.getenv("DEMO_MODE", "").strip().lower() in {"1", "true", "yes", "on"}
