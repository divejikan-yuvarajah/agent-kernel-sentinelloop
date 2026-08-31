"""Compatibility re-export. Detection lives in guardrails.emergency_bypass."""

from guardrails.emergency_bypass import detect_emergency, is_emergency_trigger

__all__ = ["detect_emergency", "is_emergency_trigger"]
