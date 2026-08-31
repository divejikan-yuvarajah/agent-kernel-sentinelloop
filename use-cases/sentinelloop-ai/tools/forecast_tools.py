"""Deterministic workplace risk-pattern detection.

Groups incidents by (category, location) over a rolling window and scores
recurrence. No LLM, no I/O, no invented incidents. The prevention agent may
only turn these patterns into human-readable recommendations.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

log = logging.getLogger("sentinelloop.forecast")

WINDOW_DAYS = 30
MIN_GROUP_SIZE = 2
DEFAULT_FREQUENCY_THRESHOLD = 0.15
THRESHOLD_ENV = "PREDICTION_FREQUENCY_THRESHOLD"

TREND_INCREASING = "increasing"
TREND_STABLE = "stable"

_SEVERITY_WEIGHT = {
    "CRITICAL": 1.8,
    "HIGH": 1.4,
    "MEDIUM": 1.15,
    "LOW": 1.0,
}

_STATS = {
    "prediction_generated": 0,
    "risk_zone_detected": 0,
}


def forecast_stats() -> dict[str, int]:
    return dict(_STATS)


def reset_forecast_stats() -> None:
    for key in _STATS:
        _STATS[key] = 0


def frequency_threshold(raw: str | None = None) -> float:
    """Read PREDICTION_FREQUENCY_THRESHOLD. Default 0.15. Never hardcoded at call sites."""
    text = raw if raw is not None else os.environ.get(THRESHOLD_ENV, "")
    try:
        value = float(str(text).strip() or DEFAULT_FREQUENCY_THRESHOLD)
    except (TypeError, ValueError):
        return DEFAULT_FREQUENCY_THRESHOLD
    if value < 0:
        return DEFAULT_FREQUENCY_THRESHOLD
    return value


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_mapping(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    dump = getattr(row, "model_dump", None)
    if callable(dump):
        data = dump()
        if isinstance(data, dict):
            return data
    return {key: getattr(row, key) for key in dir(row) if not key.startswith("_")}


def _as_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _field(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def normalize_group_category(value: Any) -> str:
    raw = " ".join(str(value or "").strip().lower().replace("_", "/").replace("-", "/").split())
    if not raw:
        return "uncategorized"
    aliases = {
        "slip/trip/fall": "slip/trip",
        "slip trip fall": "slip/trip",
        "machinery": "machine",
        "fire": "fire/smoke",
        "fire/smoke": "fire/smoke",
        "missing ppe": "ppe",
        "missing/ppe": "ppe",
        "electrical": "electrical",
        "chemical": "chemical",
    }
    return aliases.get(raw, raw)


def normalize_group_location(value: Any) -> str:
    raw = " ".join(str(value or "").strip().split())
    return raw.lower() if raw else "unknown location"


def _status_token(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "_")


def _is_open(mapping: dict[str, Any]) -> bool:
    token = _status_token(_field(mapping, "status"))
    if token in {"CLOSED", "RESOLVED", "CANCELLED", "CANCELED", "DUPLICATE"}:
        return False
    return True


def _risk_token(mapping: dict[str, Any]) -> str:
    raw = str(_field(mapping, "current_risk_level", "risk_level") or "").strip().upper()
    if raw in _SEVERITY_WEIGHT:
        return raw
    return "MEDIUM"


def _duplicate_count(mapping: dict[str, Any]) -> int:
    try:
        return max(0, int(_field(mapping, "duplicate_count") or 0))
    except (TypeError, ValueError):
        return 0


def _active_hazard(mapping: dict[str, Any]) -> bool:
    flag = _field(mapping, "hazard_currently_active", "is_active")
    if flag is True:
        return True
    if isinstance(flag, str) and flag.strip().lower() in {"true", "yes", "1"}:
        return True
    return _is_open(mapping)


def days_since(when: datetime, now: datetime) -> int:
    delta = now - when
    return max(0, int(delta.total_seconds() // 86400))


def frequency_score_for(timestamps: list[datetime], now: datetime) -> float:
    """sum(1 / (days_since_each_incident + 1)). Recent rows weigh more. Deterministic."""
    if not timestamps:
        return 0.0
    total = 0.0
    for stamp in timestamps:
        total += 1.0 / (days_since(stamp, now) + 1)
    return round(total, 6)


def detect_trend(timestamps: list[datetime]) -> str:
    """Increasing when the most recent gap is shorter than the average historical gap."""
    ordered = sorted(timestamps)
    if len(ordered) < 3:
        return TREND_STABLE
    gaps = [(later - earlier).total_seconds() / 86400.0 for earlier, later in zip(ordered, ordered[1:])]
    if not gaps:
        return TREND_STABLE
    latest = gaps[-1]
    average = sum(gaps) / len(gaps)
    if latest < average:
        return TREND_INCREASING
    return TREND_STABLE


def _weekly_counts(timestamps: list[datetime], now: datetime, *, weeks: int = 4) -> list[int]:
    counts = [0] * weeks
    for stamp in timestamps:
        idx = min(weeks - 1, days_since(stamp, now) // 7)
        counts[weeks - 1 - idx] += 1
    return counts


def _span_days(timestamps: list[datetime], now: datetime) -> int:
    if not timestamps:
        return 0
    first = min(timestamps)
    return max(1, days_since(first, now))


def _reason_factors(
    *,
    count: int,
    span_days: int,
    trend: str,
    active: bool,
    duplicates: int,
    hotspot: bool,
    top_risk: str,
) -> list[str]:
    factors = [f"{count} reports in {span_days} days", "same location"]
    if trend == TREND_INCREASING:
        factors.append("shortening incident intervals")
        factors.append("increasing frequency")
    else:
        factors.append("stable reporting interval")
    if active:
        factors.append("active hazard exists")
        factors.append("recent active report")
    if duplicates >= 2:
        factors.append("duplicate reports increasing")
    if hotspot:
        factors.append("multiple hazard categories at this location")
    if top_risk in {"HIGH", "CRITICAL"}:
        factors.append(f"{top_risk.lower()} severity reports present")
    return factors


def _pattern_risk_level(*, trend: str, top_risk: str, active: bool, frequency: float, hotspot: bool) -> str:
    if top_risk == "CRITICAL" or (trend == TREND_INCREASING and active and frequency >= 0.3):
        return "High"
    if hotspot and top_risk in {"HIGH", "CRITICAL"}:
        return "High"
    if frequency >= 0.3 or trend == TREND_INCREASING or top_risk == "HIGH":
        return "High"
    return "Medium"


def _attention_score(
    *,
    frequency: float,
    top_risk: str,
    active: bool,
    duplicates: int,
    hotspot: bool,
) -> float:
    score = frequency * _SEVERITY_WEIGHT.get(top_risk, 1.0)
    if active:
        score *= 1.2
    if duplicates >= 3:
        score *= 1.25
    elif duplicates >= 2:
        score *= 1.15
    if hotspot:
        score *= 1.1
    return round(score, 4)


def detect_location_hotspots(
    incidents: list[Any], *, now: datetime | None = None, window_days: int = WINDOW_DAYS
) -> list[dict[str, Any]]:
    """Locations with two or more distinct hazard categories in the window."""
    now = now or _utcnow()
    start = now - timedelta(days=window_days)
    categories: dict[str, set[str]] = {}
    display: dict[str, str] = {}
    for row in incidents:
        mapping = _as_mapping(row)
        stamp = _as_dt(_field(mapping, "created_at", "reported_date")) or now
        if stamp < start:
            continue
        location_key = normalize_group_location(_field(mapping, "location"))
        category_key = normalize_group_category(_field(mapping, "hazard_category", "category"))
        loc_display = str(_field(mapping, "location") or "Unknown location")
        display[location_key] = loc_display
        categories.setdefault(location_key, set()).add(category_key)
    hotspots = []
    for key, cats in sorted(categories.items(), key=lambda item: (-len(item[1]), item[0])):
        if len(cats) < 2:
            continue
        hotspots.append(
            {
                "location": display[key],
                "location_key": key,
                "categories": sorted(cats),
                "category_count": len(cats),
                "high_attention_location": True,
            }
        )
    return hotspots


def detect_risk_patterns(
    incidents: list,
    *,
    now: datetime | None = None,
    window_days: int = WINDOW_DAYS,
    threshold: float | None = None,
) -> list[dict]:
    """Group by (category, location). Include open and closed. Require 2+ in 30 days."""
    now = now or _utcnow()
    cutoff = now - timedelta(days=window_days)
    zone_threshold = frequency_threshold() if threshold is None else threshold
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    display_cat: dict[tuple[str, str], str] = {}
    display_loc: dict[tuple[str, str], str] = {}
    for row in incidents:
        mapping = _as_mapping(row)
        stamp = _as_dt(_field(mapping, "created_at", "reported_date")) or now
        if stamp < cutoff:
            continue
        mapping["_created_at"] = stamp
        cat_key = normalize_group_category(_field(mapping, "hazard_category", "category"))
        loc_key = normalize_group_location(_field(mapping, "location"))
        key = (cat_key, loc_key)
        grouped.setdefault(key, []).append(mapping)
        display_cat[key] = str(_field(mapping, "hazard_category", "category") or cat_key)
        display_loc[key] = str(_field(mapping, "location") or "Unknown location")

    hotspots = detect_location_hotspots(incidents, now=now, window_days=window_days)
    hotspot_keys = {item["location_key"] for item in hotspots}

    patterns: list[dict[str, Any]] = []
    for key, rows in grouped.items():
        if len(rows) < MIN_GROUP_SIZE:
            continue
        stamps = [row["_created_at"] for row in rows]
        score = frequency_score_for(stamps, now)
        trend = detect_trend(stamps)
        last = max(stamps)
        first = min(stamps)
        top_risk = max((_risk_token(row) for row in rows), key=lambda level: _SEVERITY_WEIGHT.get(level, 1.0))
        active = any(_active_hazard(row) for row in rows)
        dup_max = max((_duplicate_count(row) for row in rows), default=0)
        hotspot = key[1] in hotspot_keys
        span = _span_days(stamps, now)
        zone = score > zone_threshold
        count = len(rows)
        reasons = _reason_factors(
            count=count,
            span_days=span,
            trend=trend,
            active=active,
            duplicates=dup_max,
            hotspot=hotspot,
            top_risk=top_risk,
        )
        risk_level = _pattern_risk_level(
            trend=trend, top_risk=top_risk, active=active, frequency=score, hotspot=hotspot
        )
        attention = _attention_score(
            frequency=score, top_risk=top_risk, active=active, duplicates=dup_max, hotspot=hotspot
        )
        pattern = {
            "category": display_cat[key],
            "location": display_loc[key],
            "category_key": key[0],
            "location_key": key[1],
            "incident_count": count,
            "days_since_last": days_since(last, now),
            "frequency_score": score,
            "trend": trend,
            "predicted_risk_zone": zone,
            "risk_level": risk_level,
            "reason_factors": reasons,
            "attention_score": attention,
            "active_hazard": active,
            "duplicate_signal": dup_max,
            "location_hotspot": hotspot,
            "weekly_counts": _weekly_counts(stamps, now),
            "first_seen": first.isoformat(),
            "last_seen": last.isoformat(),
            "span_days": span,
            "open_count": sum(1 for row in rows if _is_open(row)),
            "prediction_id": f"{key[1]}__{key[0]}".replace(" ", "-"),
        }
        patterns.append(pattern)
        if zone:
            _STATS["risk_zone_detected"] += 1
            log.info(
                "risk_zone_detected location=%s category=%s count=%s score=%s",
                pattern["location"],
                pattern["category"],
                count,
                score,
            )

    patterns.sort(key=lambda item: (-item["attention_score"], -item["incident_count"], item["location"]))
    _STATS["prediction_generated"] += 1
    log.info(
        "prediction_generated groups=%s zones=%s",
        len(patterns),
        sum(1 for item in patterns if item["predicted_risk_zone"]),
    )
    return patterns
