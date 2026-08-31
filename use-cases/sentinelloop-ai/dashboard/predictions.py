"""Assemble predictive safety views from existing incidents.

No prediction table. One incident list read, then deterministic patterns
plus at most one reasoning call per flagged group. Cached by the API layer.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from dashboard.schemas import HeatmapCell, PredictionItem, PredictionsResponse, PreventionAnalytics
from tools.forecast_tools import detect_location_hotspots, detect_risk_patterns

log = logging.getLogger("sentinelloop.dashboard.predictions")

_INSPECTIONS_TRIGGERED = 0

_MARKERS = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}


def inspections_triggered() -> int:
    return _INSPECTIONS_TRIGGERED


def record_inspection_triggered() -> int:
    global _INSPECTIONS_TRIGGERED
    _INSPECTIONS_TRIGGERED += 1
    return _INSPECTIONS_TRIGGERED


def reset_inspection_triggered() -> None:
    global _INSPECTIONS_TRIGGERED
    _INSPECTIONS_TRIGGERED = 0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _timeline(pattern: dict[str, Any], *, generated_at: datetime) -> list[dict[str, str]]:
    events = [
        {"date": str(pattern.get("first_seen") or "")[:10], "label": "Incident reported"},
    ]
    if int(pattern.get("duplicate_signal") or 0) >= 2:
        events.append({"date": str(pattern.get("last_seen") or "")[:10], "label": "Duplicate detected"})
    events.append({"date": str(pattern.get("last_seen") or "")[:10], "label": "Pattern identified"})
    events.append({"date": generated_at.date().isoformat(), "label": "Inspection recommended"})
    if int(pattern.get("open_count") or 0) == 0:
        events.append({"date": str(pattern.get("last_seen") or "")[:10], "label": "Risk reduced"})
    return events


def _heatmap(incidents: list[Any], flagged: list[dict[str, Any]], *, now: datetime) -> list[HeatmapCell]:
    by_location: dict[str, dict[str, Any]] = {}
    for pattern in flagged:
        loc = str(pattern.get("location") or "Unknown")
        cell = by_location.setdefault(
            loc,
            {"active": 0, "risk": "LOW", "predicted": False, "electrical": 0, "machine": 0, "chemical": 0, "other": 0},
        )
        cell["predicted"] = True
        cell["active"] = max(cell["active"], int(pattern.get("open_count") or 0))
        level = str(pattern.get("risk_level") or "Medium").upper()
        rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        if rank.get(level, 0) > rank.get(cell["risk"], 0):
            cell["risk"] = level if level in rank else "HIGH"
        cat = str(pattern.get("category") or "").lower()
        count = int(pattern.get("incident_count") or 0)
        if "electrical" in cat:
            cell["electrical"] += count
        elif "machine" in cat:
            cell["machine"] += count
        elif "chemical" in cat:
            cell["chemical"] += count
        else:
            cell["other"] += count
    hotspots = detect_location_hotspots(incidents, now=now)
    for item in hotspots:
        loc = item["location"]
        cell = by_location.setdefault(
            loc,
            {
                "active": 0,
                "risk": "MEDIUM",
                "predicted": False,
                "electrical": 0,
                "machine": 0,
                "chemical": 0,
                "other": 0,
            },
        )
        if cell["risk"] == "LOW":
            cell["risk"] = "MEDIUM"
    rows = []
    for location, cell in sorted(by_location.items(), key=lambda item: item[0]):
        risk = cell["risk"]
        rows.append(
            HeatmapCell(
                location=location,
                risk=risk,
                marker=_MARKERS.get(risk, "🟢"),
                active=int(cell["active"] or 0),
                predicted=bool(cell["predicted"]),
                electrical_images=int(cell.get("electrical") or 0),
                machine_images=int(cell.get("machine") or 0),
                chemical_images=int(cell.get("chemical") or 0),
                other_images=int(cell.get("other") or 0),
            )
        )
    return rows


def _weekly_rollup(flagged: list[dict[str, Any]]) -> list[int]:
    totals = [0, 0, 0, 0]
    for pattern in flagged:
        counts = pattern.get("weekly_counts") or []
        for index, value in enumerate(counts[:4]):
            totals[index] += int(value)
    return totals


async def build_predictions(
    repository: Any,
    *,
    call_model_fn: Any | None = None,
    now: datetime | None = None,
) -> PredictionsResponse:
    from agents.prevention_agent import generate_prevention_recommendations

    generated_at = now or _utcnow()
    incidents = repository.list_all_incidents()
    patterns = detect_risk_patterns(incidents, now=generated_at)
    flagged = [row for row in patterns if row.get("predicted_risk_zone")]
    recs = await generate_prevention_recommendations(flagged, call_model_fn=call_model_fn)
    rec_map = {(item.location.lower(), item.category.lower()): item for item in recs}
    items: list[PredictionItem] = []
    resolved_zones = 0
    for pattern in flagged:
        rec = rec_map.get((str(pattern["location"]).lower(), str(pattern["category"]).lower()))
        reason = rec.reason if rec else f"{pattern['incident_count']} related incidents detected"
        recommendation = rec.recommendation if rec else "Recommend inspection before the next shift."
        if int(pattern.get("open_count") or 0) == 0:
            resolved_zones += 1
        items.append(
            PredictionItem(
                location=pattern["location"],
                category=pattern["category"],
                reason=reason,
                recommendation=recommendation,
                trend=pattern["trend"],
                incident_count=pattern["incident_count"],
                frequency_score=pattern["frequency_score"],
                risk_level=pattern.get("risk_level"),
                reason_factors=list(pattern.get("reason_factors") or []),
                weekly_counts=list(pattern.get("weekly_counts") or []),
                generated_by=rec.generated_by if rec else "prevention_agent",
                confidence=rec.confidence if rec else None,
                prediction_id=pattern.get("prediction_id"),
                location_hotspot=bool(pattern.get("location_hotspot")),
                days_since_last=int(pattern.get("days_since_last") or 0),
                span_days=int(pattern.get("span_days") or 0),
                timeline=_timeline(pattern, generated_at=generated_at),
            )
        )
    analytics = PreventionAnalytics(
        predicted_risk_zones=len(flagged),
        resolved_future_risks=resolved_zones,
        inspections_triggered=inspections_triggered(),
        prevented_recurrences=max(resolved_zones, 0),
    )
    return PredictionsResponse(
        generated_at=generated_at,
        last_updated=generated_at,
        prediction_count=len(items),
        predictions=items,
        heatmap=_heatmap(incidents, flagged, now=generated_at),
        analytics=analytics,
        weekly_counts=_weekly_rollup(flagged),
    )
