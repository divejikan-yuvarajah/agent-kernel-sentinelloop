"""Helpers that keep sandbox demo incidents out of production analytics."""

from __future__ import annotations

from typing import Any


def incident_is_sandbox(row: Any) -> bool:
    """True when an incident row belongs to the Try It Live sandbox."""
    if row is None:
        return False
    if getattr(row, "is_sandbox", False) is True:
        return True
    channel = (getattr(row, "source_channel", None) or "").strip().lower()
    if channel == "sandbox":
        return True
    meta = getattr(row, "source_metadata", None)
    if isinstance(meta, dict) and bool(meta.get("is_sandbox")):
        return True
    if isinstance(row, dict):
        if row.get("is_sandbox") is True:
            return True
        if (row.get("source_channel") or "").strip().lower() == "sandbox":
            return True
        nested = row.get("source_metadata")
        if isinstance(nested, dict) and bool(nested.get("is_sandbox")):
            return True
    return False


def filter_production_incidents(rows: list[Any] | None) -> list[Any]:
    """Drop sandbox incidents from production dashboards and forecasts."""
    return [row for row in (rows or []) if not incident_is_sandbox(row)]
