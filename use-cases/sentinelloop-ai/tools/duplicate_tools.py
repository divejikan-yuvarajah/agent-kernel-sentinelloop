"""Intelligent duplicate-hazard detection.

Local-first: same open category + location within 24 hours, then
``difflib.SequenceMatcher`` (and a token Dice score of the same strings) on
translated English text. A fast model is used at most once, only for a
borderline band when two or more candidates exist.

Does not create incidents. The orchestrator still owns persistence.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tools.lifecycle import STATUS_CLOSED, STATUS_RESOLVED, to_display_status

log = logging.getLogger("sentinelloop.duplicate")

DecisionStatus = Literal["none", "possible", "confirmed"]
DecisionAction = Literal["create_new", "reuse", "reopen"]
DecisionSource = Literal["LOCAL_SIMILARITY", "AI_VERIFICATION"]

DEFAULT_WINDOW_HOURS = 24
LOCAL_MATCH_THRESHOLD = 0.6
BORDERLINE_LOW = 0.4
BORDERLINE_HIGH = 0.6
LLM_TIMEOUT_S = 4.0
ROLE_FAST = "role_fast"
DUPLICATE_ESCALATION_COUNT = 3

SOURCE_LOCAL: DecisionSource = "LOCAL_SIMILARITY"
SOURCE_AI: DecisionSource = "AI_VERIFICATION"

RISK_STEPS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

CLOSED_DISPLAY = {STATUS_CLOSED, STATUS_RESOLVED}
CLOSED_REPO = {"CLOSED", "RESOLVED"}

_STOP = frozenset(
    {
        "a",
        "an",
        "and",
        "at",
        "for",
        "from",
        "has",
        "have",
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
_STEM_SUFFIXES = ("ing", "age", "ed", "es", "s")

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

LLM_PROMPT = """Are these two workplace hazard reports describing the same hazard?

Report A:
{description_a}

Report B:
{description_b}

Answer only:
YES or NO"""

_STATS = {
    "total_checks": 0,
    "local_matches": 0,
    "llm_checks": 0,
    "avoided_duplicates": 0,
}


class DuplicateQuery(BaseModel):
    """Fields supported by this detector. Unknown extras are ignored."""

    model_config = ConfigDict(extra="ignore")

    translated_text: str | None = None
    translated_description: str | None = None
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


class DuplicateCandidate(BaseModel):
    mapping: dict[str, Any]
    similarity: float
    matching_fields: list[str] = Field(default_factory=list)


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
    similarity_score: float | None = None
    reason: str | None = None
    preserve_status: bool = False
    decision_source: DecisionSource | None = None
    matching_fields: list[str] = Field(default_factory=list)
    explanation: dict[str, Any] = Field(default_factory=dict)
    escalated: bool = False
    previous_risk_level: str | None = None
    new_risk_level: str | None = None
    duplicate_of: str | None = None


def duplicate_detection_stats() -> dict[str, int]:
    """In-process cost-control counters for the duplicate detector."""
    return dict(_STATS)


def reset_duplicate_detection_stats() -> None:
    for key in _STATS:
        _STATS[key] = 0


def normalize_location(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def tokenize(text: str | None) -> set[str]:
    if not text:
        return set()
    return {_stem(token) for token in _TOKEN_RE.findall(text.lower()) if token not in _STOP and len(token) > 1}


def _stem(token: str) -> str:
    for suffix in _STEM_SUFFIXES:
        if token.endswith(suffix) and len(token) > len(suffix) + 2:
            return token[: -len(suffix)]
    return token


def calculate_similarity(left: str | None, right: str | None) -> float:
    """Local similarity of two translated descriptions.

    Uses SequenceMatcher on the full strings and on sorted content tokens, plus
    Dice overlap of stemmed tokens so paraphrases (the oil-leak example) score
    in the documented 0.6+ band without embeddings.
    """
    a = re.sub(r"\s+", " ", (left or "").strip().lower())
    b = re.sub(r"\s+", " ", (right or "").strip().lower())
    if not a or not b:
        return 0.0
    raw = SequenceMatcher(None, a, b).ratio()
    tokens_a = sorted(tokenize(a))
    tokens_b = sorted(tokenize(b))
    sorted_ratio = (
        SequenceMatcher(None, " ".join(tokens_a), " ".join(tokens_b)).ratio() if tokens_a and tokens_b else 0.0
    )
    set_a, set_b = set(tokens_a), set(tokens_b)
    dice = (2 * len(set_a & set_b)) / (len(tokens_a) + len(tokens_b)) if tokens_a and tokens_b else 0.0
    return round(max(raw, sorted_ratio, dice), 4)


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


def _translated_query(query: DuplicateQuery) -> str:
    return (query.translated_text or query.translated_description or "").strip()


def _translated_row(mapping: dict[str, Any]) -> str:
    return str(mapping.get("translated_text") or mapping.get("hazard_description") or "").strip()


def _query_location(query: DuplicateQuery) -> str:
    return normalize_location(query.qr_location or query.location)


def _row_location(mapping: dict[str, Any]) -> str:
    return normalize_location(str(mapping.get("location") or mapping.get("qr_location") or ""))


def _query_category(query: DuplicateQuery) -> str:
    return (query.hazard_category or "").strip().lower()


def _row_category(mapping: dict[str, Any]) -> str:
    return str(mapping.get("hazard_category") or "").strip().lower()


def _display_status(mapping: dict[str, Any]) -> str | None:
    return to_display_status(mapping.get("status"))


def _is_closed(mapping: dict[str, Any]) -> bool:
    display = _display_status(mapping)
    if display in CLOSED_DISPLAY:
        return True
    raw = str(mapping.get("status") or "").strip().upper().replace(" ", "_")
    return raw in CLOSED_REPO


def _is_open_incident(mapping: dict[str, Any]) -> bool:
    return not _is_closed(mapping)


def _hazard_currently_exists(query: DuplicateQuery) -> bool:
    if query.is_active is True:
        return True
    blob = " ".join(part for part in (_translated_query(query), query.raw_text) if part)
    return bool(_STILL_ACTIVE_RE.search(blob))


def _within_window(mapping: dict[str, Any], now: datetime, hours: int) -> bool:
    created = _created_at(mapping)
    if created is None:
        return True
    return created >= now - timedelta(hours=hours)


def _as_query(query: DuplicateQuery | dict[str, Any] | Any) -> DuplicateQuery:
    if isinstance(query, DuplicateQuery):
        return query
    if isinstance(query, dict):
        return DuplicateQuery.model_validate(query)
    return DuplicateQuery.model_validate(_incident_mapping(query))


def _load_incidents(repository: Any, *, cutoff: datetime | None = None) -> list[Any]:
    list_all = getattr(repository, "list_all_incidents", None)
    if callable(list_all):
        try:
            return list(list_all() or [])
        except Exception:
            log.warning("duplicate_check_failed reason=list_all_incidents")
    list_fn = getattr(repository, "list_incidents", None)
    if list_fn is None:
        return []
    try:
        from database.schemas import IncidentFilters

        filters = IncidentFilters(created_after=cutoff, limit=100) if cutoff is not None else None
        return list(list_fn(filters) or [])
    except TypeError:
        try:
            return list(list_fn() or [])
        except Exception:
            log.warning("duplicate_check_failed reason=list_incidents")
            return []
    except Exception:
        log.warning("duplicate_check_failed reason=list_incidents")
        return []


def find_candidate_incidents(
    query: DuplicateQuery | dict[str, Any] | Any,
    *,
    repository: Any,
    now: datetime | None = None,
    window_hours: int = DEFAULT_WINDOW_HOURS,
    include_closed: bool = False,
) -> list[DuplicateCandidate]:
    """Open (or optionally closed) incidents sharing category, location, and window."""
    payload = _as_query(query)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    location = _query_location(payload)
    category = _query_category(payload)
    description = _translated_query(payload)
    if not location or not category:
        return []
    cutoff = now - timedelta(hours=window_hours)
    rows = _load_incidents(repository, cutoff=cutoff)
    candidates: list[DuplicateCandidate] = []
    for row in rows:
        mapping = _incident_mapping(row)
        if not _within_window(mapping, now, window_hours):
            continue
        closed = _is_closed(mapping)
        if closed and not include_closed:
            continue
        if not closed and not _is_open_incident(mapping):
            continue
        if _row_location(mapping) != location:
            continue
        if _row_category(mapping) != category:
            continue
        similarity = calculate_similarity(description, _translated_row(mapping))
        fields = ["category", "location"]
        if description and _translated_row(mapping):
            fields.append("description")
        candidates.append(DuplicateCandidate(mapping=mapping, similarity=similarity, matching_fields=fields))
    candidates.sort(key=lambda item: item.similarity, reverse=True)
    return candidates


def score_candidate(query: DuplicateQuery, mapping: dict[str, Any]) -> tuple[DecisionStatus, float, str]:
    """Score one stored incident against a new report (local rules only)."""
    if _query_location(query) != _row_location(mapping) or not _query_location(query):
        return "none", calculate_similarity(_translated_query(query), _translated_row(mapping)), "different_location"
    if _query_category(query) != _row_category(mapping) or not _query_category(query):
        return "none", calculate_similarity(_translated_query(query), _translated_row(mapping)), "different_hazard"
    similarity = calculate_similarity(_translated_query(query), _translated_row(mapping))
    if similarity >= LOCAL_MATCH_THRESHOLD:
        return "confirmed", similarity, "location_category_description"
    if similarity >= BORDERLINE_LOW:
        return "possible", similarity, "borderline_description"
    return "none", similarity, "weak_description"


def _result_from_candidate(
    candidate: DuplicateCandidate,
    *,
    status: DecisionStatus,
    source: DecisionSource | None,
    action: DecisionAction = "create_new",
    reason: str | None = None,
) -> DuplicateResult:
    mapping = candidate.mapping
    ident = _incident_id(mapping)
    display = _display_status(mapping)
    confirmed = status == "confirmed"
    similarity = candidate.similarity
    explanation = {
        "decision": "duplicate" if confirmed else status,
        "confidence": similarity,
        "source": source,
        "similarity_score": similarity,
        "matching_fields": candidate.matching_fields,
    }
    return DuplicateResult(
        status=status,
        action=action,
        canonical_incident_id=ident if confirmed else None,
        canonical_uuid=_uuid(mapping) if confirmed else None,
        candidate_incident_id=ident,
        duplicate_count=int(mapping.get("duplicate_count") or 0),
        canonical_status=display,
        similarity=similarity,
        similarity_score=similarity,
        reason=reason,
        preserve_status=display in PRESERVED_STATUSES if display else False,
        decision_source=source if confirmed else None,
        matching_fields=list(candidate.matching_fields),
        explanation=explanation,
        duplicate_of=str(_uuid(mapping) or ident) if confirmed else None,
    )


def find_duplicate_incident(
    query: DuplicateQuery | dict[str, Any] | Any,
    *,
    repository: Any,
    now: datetime | None = None,
    window_hours: int = DEFAULT_WINDOW_HOURS,
) -> DuplicateResult:
    """Local-only decision. Never calls a model. Never silently merges ``possible``."""
    _STATS["total_checks"] += 1
    payload = _as_query(query)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if getattr(repository, "list_incidents", None) is None and getattr(repository, "list_all_incidents", None) is None:
        log.warning("duplicate_check_failed reason=no_list_incidents")
        return DuplicateResult(status="none", action="create_new", reason="repository_unavailable")

    description = _translated_query(payload)
    if not description:
        log.info("duplicate_check_completed status=none reason=missing_description")
        return DuplicateResult(status="none", action="create_new", reason="missing_description")
    if not _query_location(payload) or not _query_category(payload):
        log.info("duplicate_check_completed status=none reason=missing_location_or_category")
        return DuplicateResult(status="none", action="create_new", reason="missing_location_or_category")

    try:
        open_candidates = find_candidate_incidents(
            payload, repository=repository, now=now, window_hours=window_hours, include_closed=False
        )
    except Exception:
        log.warning("duplicate_check_failed reason=candidate_scan")
        return DuplicateResult(status="none", action="create_new", reason="duplicate_tool_failure")

    strong = [item for item in open_candidates if item.similarity >= LOCAL_MATCH_THRESHOLD]
    if strong:
        best = strong[0]
        result = _result_from_candidate(
            best,
            status="confirmed",
            source=SOURCE_LOCAL,
            action="reuse",
            reason="location_category_description",
        )
        result.preserve_status = True
        _STATS["local_matches"] += 1
        _STATS["avoided_duplicates"] += 1
        log.info(
            "duplicate_check_completed status=confirmed action=reuse incident=%s source=LOCAL_SIMILARITY",
            result.canonical_incident_id,
        )
        return result

    if _hazard_currently_exists(payload):
        closed_candidates = find_candidate_incidents(
            payload, repository=repository, now=now, window_hours=window_hours, include_closed=True
        )
        closed_strong = [
            item
            for item in closed_candidates
            if (
                _display_status(item.mapping) == STATUS_CLOSED
                or str(item.mapping.get("status") or "").upper() == "CLOSED"
            )
            and item.similarity >= LOCAL_MATCH_THRESHOLD
        ]
        if closed_strong:
            best = closed_strong[0]
            result = _result_from_candidate(
                best,
                status="confirmed",
                source=SOURCE_LOCAL,
                action="reopen",
                reason="closed_hazard_still_present",
            )
            result.preserve_status = False
            _STATS["local_matches"] += 1
            _STATS["avoided_duplicates"] += 1
            log.info(
                "duplicate_check_completed status=confirmed action=reopen incident=%s", result.canonical_incident_id
            )
            return result

    if open_candidates:
        best = open_candidates[0]
        if BORDERLINE_LOW <= best.similarity < LOCAL_MATCH_THRESHOLD:
            result = _result_from_candidate(
                best,
                status="possible",
                source=None,
                action="create_new",
                reason="uncertain_match",
            )
            result.canonical_incident_id = None
            result.canonical_uuid = None
            log.info("duplicate_check_completed status=possible candidate=%s", result.candidate_incident_id)
            return result

    log.info("duplicate_check_completed status=none")
    return DuplicateResult(status="none", action="create_new", reason="no_match")


def check_for_duplicate(
    query: DuplicateQuery | dict[str, Any] | Any,
    *,
    repository: Any,
    **kwargs: Any,
) -> DuplicateResult:
    """Sync local entry point (no LLM). Used by tests and as a safe fallback."""
    return find_duplicate_incident(query, repository=repository, **kwargs)


async def verify_with_fast_model(
    description_a: str,
    description_b: str,
    *,
    call_model_fn: Any | None = None,
) -> bool | None:
    """Ask role_fast once. Returns True/False, or None when the model is unusable."""
    from tools.model_router import call_model

    router = call_model_fn or call_model
    prompt = LLM_PROMPT.format(description_a=description_a.strip(), description_b=description_b.strip())
    messages = [{"role": "user", "content": prompt}]
    try:
        routed = await asyncio.wait_for(
            router(ROLE_FAST, messages, temperature=0.0, max_tokens=8),
            timeout=LLM_TIMEOUT_S,
        )
    except Exception:
        log.warning("duplicate_llm_verification_failed")
        return None
    content = str(getattr(routed, "content", None) or "").strip().upper()
    if getattr(routed, "degraded", False) or getattr(routed, "error", None) or not content:
        log.warning("duplicate_llm_verification_failed")
        return None
    token = re.split(r"[^A-Z]+", content, maxsplit=1)[0]
    if token == "YES":
        return True
    if token == "NO":
        return False
    if content.startswith("YES"):
        return True
    if content.startswith("NO"):
        return False
    log.info("duplicate_llm_verification_unparsed")
    return None


async def check_duplicate_incident(
    query: DuplicateQuery | dict[str, Any] | Any,
    *,
    repository: Any,
    call_model_fn: Any | None = None,
    now: datetime | None = None,
    window_hours: int = DEFAULT_WINDOW_HOURS,
) -> DuplicateResult:
    """Full detector: local first, optional single role_fast check on a borderline band."""
    local = find_duplicate_incident(query, repository=repository, now=now, window_hours=window_hours)
    if local.status == "confirmed":
        return local
    payload = _as_query(query)
    description = _translated_query(payload)
    if not description:
        return local
    try:
        candidates = find_candidate_incidents(
            payload, repository=repository, now=now, window_hours=window_hours, include_closed=False
        )
    except Exception:
        return local
    borderline = [item for item in candidates if BORDERLINE_LOW <= item.similarity < BORDERLINE_HIGH]
    if len(candidates) < 2 or not borderline:
        return local
    best = borderline[0]
    _STATS["llm_checks"] += 1
    verified = await verify_with_fast_model(
        description,
        _translated_row(best.mapping),
        call_model_fn=call_model_fn,
    )
    if verified is True:
        result = _result_from_candidate(
            best,
            status="confirmed",
            source=SOURCE_AI,
            action="reuse",
            reason="ai_verification",
        )
        result.preserve_status = True
        _STATS["avoided_duplicates"] += 1
        log.info(
            "duplicate_check_completed status=confirmed action=reuse incident=%s source=AI_VERIFICATION",
            result.canonical_incident_id,
        )
        return result
    log.info("duplicate_llm_fallback source=LOCAL_SIMILARITY")
    return local


def next_risk_level(current: str | None) -> str:
    key = (current or "LOW").strip().upper()
    if key not in RISK_STEPS:
        key = "LOW"
    index = RISK_STEPS.index(key)
    return RISK_STEPS[min(index + 1, len(RISK_STEPS) - 1)]


def escalate_duplicate_risk(repository: Any, incident_id: UUID, *, current_risk: str | None, count: int) -> str | None:
    """Raise risk one step when the third independent report lands. Never above CRITICAL."""
    nxt = next_risk_level(current_risk)
    if nxt == (current_risk or "").strip().upper() and nxt == "CRITICAL":
        return "CRITICAL"
    updater = getattr(repository, "update_incident_fields", None)
    if callable(updater):
        updater(incident_id, {"current_risk_level": nxt})
    _add_update(
        repository,
        incident_id,
        update_type="duplicate_threshold_reached",
        message="Priority increased — reported by multiple workers.",
        metadata={
            "event": "duplicate_threshold_reached",
            "count": count,
            "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "reason": "Multiple workers reporting same hazard",
            "previous_risk_level": current_risk,
            "new_risk_level": nxt,
        },
    )
    log.info("duplicate_risk_escalated incident=%s level=%s count=%s", incident_id, nxt, count)
    return nxt


def handle_duplicate_match(
    repository: Any,
    incident_id: UUID,
    *,
    result: DuplicateResult,
    current_risk_level: str | None = None,
) -> DuplicateResult:
    """Increment the canonical incident, write timeline events, escalate at 3 reports."""
    count = int(result.duplicate_count or 0)
    increment = getattr(repository, "increment_duplicate_count", None)
    if callable(increment):
        try:
            if count == 0:
                updated = increment(incident_id)
                count = int(getattr(updated, "duplicate_count", 1) or 1)
            updated = increment(incident_id)
            count = int(getattr(updated, "duplicate_count", count + 1) or count + 1)
            current_risk_level = getattr(updated, "current_risk_level", None) or current_risk_level
        except Exception:
            log.warning("duplicate_count_increment_failed")
    result.duplicate_count = count
    _add_update(
        repository,
        incident_id,
        update_type="duplicate_report_linked",
        message="Duplicate hazard detected from another worker report.",
        metadata={
            "similarity": result.similarity,
            "similarity_score": result.similarity,
            "matching_fields": result.matching_fields,
            "decision_source": result.decision_source,
            "decision": "duplicate",
            "confidence": result.similarity,
            "source": result.decision_source,
            "duplicate_of": str(incident_id),
        },
    )
    if count == DUPLICATE_ESCALATION_COUNT:
        nxt = escalate_duplicate_risk(repository, incident_id, current_risk=current_risk_level, count=count)
        if nxt:
            result.escalated = True
            result.previous_risk_level = current_risk_level
            result.new_risk_level = nxt
    result.duplicate_of = str(incident_id)
    return result


def _add_update(
    repository: Any, incident_id: UUID, *, update_type: str, message: str, metadata: dict[str, Any]
) -> None:
    add_update = getattr(repository, "add_update", None)
    if not callable(add_update):
        return
    try:
        from database.schemas import IncidentUpdateCreate

        add_update(
            IncidentUpdateCreate(
                incident_id=incident_id,
                update_type=update_type,
                actor_type="agent",
                actor_reference="duplicate_tools",
                message=message,
                metadata=metadata,
            )
        )
    except Exception:
        log.warning("duplicate_update_failed type=%s", update_type)
