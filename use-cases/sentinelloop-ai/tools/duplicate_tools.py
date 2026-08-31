"""Semantic duplicate-incident detection (Prompt 14).

Webhook retries are handled by ``tools.idempotency``. This module only
answers whether a *new worker report* matches an existing canonical incident.

Uncertain matches are never silently merged.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from tools.lifecycle import STATUS_CLOSED, to_display_status

log = logging.getLogger("sentinelloop.duplicate")

DecisionStatus = Literal["none", "possible", "confirmed"]
DecisionAction = Literal["create_new", "reuse", "reopen"]

DEFAULT_WINDOW_HOURS = 24
CONFIRMED_WITH_LOCATION = 0.45
CONFIRMED_WITHOUT_LOCATION = 0.72
POSSIBLE_THRESHOLD = 0.30

_STOP = frozenset(
    {
        "a",
        "an",
        "and",
        "at",
        "for",
        "here",
        "in",
        "is",
        "near",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    }
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STILL_ACTIVE_RE = re.compile(
    r"\b(still|again|now|ongoing|happening|leaking|sparking|smoking|on fire)\b",
    re.IGNORECASE,
)

PRESERVED_STATUSES = frozenset(
    {
        "Assigned",
        "Accepted",
        "In Progress",
        "Awaiting Verification",
        "Resolved",
        "Assessed",
        "Validating",
    }
)


class DuplicateQuery(BaseModel):
    """Fields supported by this detector. Unknown extras are ignored."""

    model_config = ConfigDict(extra="ignore")

    translated_text: str | None = None
    raw_text: str | None = None
    hazard_category: str | None = None
    location: str | None = None
    qr_location: str | None = None
    qr_equipment: str | None = None
    equipment_involved: str | None = None
    worker_id: str | None = None
    reporter_id: str | None = None
    timestamp: datetime | None = None
    has_image: bool = False
    is_active: bool | None = None


class DuplicateResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: DecisionStatus = "none"
    action: DecisionAction = "create_new"
    canonical_incident_id: str | None = None
    canonical_uuid: UUID | None = None
    candidate_incident_id: str | None = None
    duplicate_count: int = 0
    canonical_status: str | None = None
    similarity: float = 0.0
    reason: str | None = None
    preserve_status: bool = False


def normalize_location(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def tokenize(text: str | None) -> set[str]:
    if not text:
        return set()
    return {token for token in _TOKEN_RE.findall(text.lower()) if token not in _STOP and len(token) > 1}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    if union == 0:
        return 0.0
    return inter / union


def _incident_mapping(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    dump = getattr(row, "model_dump", None)
    if callable(dump):
        data = dump()
        if isinstance(data, dict):
            return data
    return {}


def _incident_id(mapping: dict[str, Any]) -> str | None:
    for key in ("incident_ref", "incident_id"):
        value = mapping.get(key)
        if value:
            return str(value)
    ident = mapping.get("id")
    return str(ident) if ident else None


def _uuid(mapping: dict[str, Any]) -> UUID | None:
    value = mapping.get("id")
    if isinstance(value, UUID):
        return value
    if value:
        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            return None
    return None


def _created_at(mapping: dict[str, Any]) -> datetime | None:
    value = mapping.get("created_at")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


def _hazard_currently_exists(query: DuplicateQuery) -> bool:
    if query.is_active is True:
        return True
    blob = " ".join(part for part in (query.translated_text, query.raw_text) if part)
    return bool(_STILL_ACTIVE_RE.search(blob))


def score_candidate(query: DuplicateQuery, mapping: dict[str, Any]) -> tuple[DecisionStatus, float, str]:
    query_location = normalize_location(query.qr_location or query.location)
    row_location = normalize_location(mapping.get("location") or mapping.get("qr_location"))
    location_match = bool(query_location and row_location and query_location == row_location)

    query_category = (query.hazard_category or "").strip().lower()
    row_category = str(mapping.get("hazard_category") or "").strip().lower()
    category_match = bool(query_category and row_category and query_category == row_category)

    query_tokens = tokenize(query.translated_text) | tokenize(query.raw_text)
    row_tokens = tokenize(mapping.get("hazard_description")) | tokenize(mapping.get("translated_text"))
    similarity = jaccard(query_tokens, row_tokens)

    equipment_q = normalize_location(query.qr_equipment or query.equipment_involved)
    equipment_r = normalize_location(str(mapping.get("equipment_involved") or mapping.get("qr_equipment") or ""))
    equipment_match = bool(equipment_q and equipment_r and equipment_q == equipment_r)

    if location_match and category_match:
        return "confirmed", max(similarity, 0.5), "location_and_category"
    if (
        location_match
        and (category_match or not query_category or not row_category)
        and similarity >= CONFIRMED_WITH_LOCATION
    ):
        return "confirmed", similarity, "location_and_description"
    if location_match and equipment_match and similarity >= POSSIBLE_THRESHOLD:
        return "confirmed", similarity, "location_and_equipment"
    if not query_location and similarity >= CONFIRMED_WITHOUT_LOCATION and (category_match or equipment_match):
        return "confirmed", similarity, "high_text_similarity"
    if location_match or (category_match and similarity >= POSSIBLE_THRESHOLD) or similarity >= POSSIBLE_THRESHOLD:
        return "possible", similarity, "partial_overlap"
    return "none", similarity, "no_overlap"


def _within_window(mapping: dict[str, Any], now: datetime, hours: int) -> bool:
    created = _created_at(mapping)
    if created is None:
        return True
    return created >= now - timedelta(hours=hours)


def find_duplicate_incident(
    query: DuplicateQuery | dict[str, Any] | Any,
    *,
    repository: Any,
    now: datetime | None = None,
    window_hours: int = DEFAULT_WINDOW_HOURS,
) -> DuplicateResult:
    """Return none / possible / confirmed. Never silently merge ``possible``."""
    if isinstance(query, DuplicateQuery):
        payload = query
    elif isinstance(query, dict):
        payload = DuplicateQuery.model_validate(query)
    else:
        mapping = _incident_mapping(query)
        payload = DuplicateQuery.model_validate(mapping)

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    list_fn = getattr(repository, "list_incidents", None)
    if list_fn is None:
        log.warning("duplicate_check_failed reason=no_list_incidents")
        return DuplicateResult(status="none", action="create_new", reason="repository_unavailable")

    try:
        rows = list_fn()
    except TypeError:
        rows = list_fn(None)
    except Exception:
        log.warning("duplicate_check_failed reason=list_incidents")
        return DuplicateResult(status="none", action="create_new", reason="duplicate_tool_failure")

    best: DuplicateResult | None = None
    for row in rows or []:
        mapping = _incident_mapping(row)
        if not _within_window(mapping, now, window_hours):
            continue
        status, similarity, reason = score_candidate(payload, mapping)
        if status == "none":
            continue
        ident = _incident_id(mapping)
        display = to_display_status(mapping.get("status"))
        candidate = DuplicateResult(
            status=status,
            action="create_new",
            canonical_incident_id=ident if status == "confirmed" else None,
            canonical_uuid=_uuid(mapping) if status == "confirmed" else None,
            candidate_incident_id=ident,
            duplicate_count=int(mapping.get("duplicate_count") or 0),
            canonical_status=display,
            similarity=similarity,
            reason=reason,
            preserve_status=display in PRESERVED_STATUSES if display else False,
        )
        if best is None or (status == "confirmed" and best.status != "confirmed") or similarity > best.similarity:
            best = candidate

    if best is None:
        log.info("duplicate_check_completed status=none")
        return DuplicateResult(status="none", action="create_new", reason="no_match")

    if best.status == "possible":
        best.canonical_incident_id = None
        best.canonical_uuid = None
        best.action = "create_new"
        best.reason = best.reason or "uncertain_match"
        log.info("duplicate_check_completed status=possible candidate=%s", best.candidate_incident_id)
        return best

    display = best.canonical_status
    if display == STATUS_CLOSED:
        if _hazard_currently_exists(payload):
            best.action = "reopen"
            best.preserve_status = False
            best.reason = "closed_hazard_still_present"
        else:
            best.action = "create_new"
            best.canonical_incident_id = None
            best.canonical_uuid = None
            best.reason = "closed_without_recurrence_signal"
            log.info("duplicate_check_completed status=confirmed action=create_new reason=closed")
            return best
    else:
        best.action = "reuse"
        best.preserve_status = True

    log.info(
        "duplicate_check_completed status=%s action=%s incident=%s",
        best.status,
        best.action,
        best.canonical_incident_id,
    )
    return best


def check_for_duplicate(
    query: DuplicateQuery | dict[str, Any] | Any,
    *,
    repository: Any,
    **kwargs: Any,
) -> DuplicateResult:
    """Public Prompt 14 entry point used by the orchestrator."""
    return find_duplicate_incident(query, repository=repository, **kwargs)
