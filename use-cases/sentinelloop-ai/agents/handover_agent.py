"""AI safety shift handover agent.

Collects previous-shift incident facts, calls ``role_fast`` once to phrase them,
persists the briefing, and posts it to the Slack Safety Channel. The model may
only rewrite structured counts — it must not invent incidents, risks, or facts.

Not part of the WhatsApp six-agent pipeline.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from tools.lifecycle import STATUS_AWAITING_VERIFICATION, STATUS_CLOSED, to_display_status
from tools.model_router import ModelCallResult, call_model

log = logging.getLogger("sentinelloop.handover")

ROLE_FAST = "role_fast"
GENERATED_BY_AGENT = "handover_agent"
SAFETY_TEAM = "Safety Supervisor"
CRITICAL_NOTICE = "🚨 Critical items require attention before shift start."

HANDOVER_SYSTEM_PROMPT = """You convert a workplace safety HANDOVER JSON object into a short operational briefing.

Rules:
- Use only numbers, locations, categories, and risks present in the JSON.
- Do not invent incidents, risks, people, or new facts.
- Do not include phone numbers, reporter names, or evidence.
- Output short bullets that a incoming shift can scan in seconds.
- End with one Priority line using the first top_risks item if present.

Format exactly like:
{shift} Safety Handover

• N new incidents reported
• N incidents remain open
• ...
Priority:
Inspect {location} {category} issue before next shift.
"""

_RISK_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
_PII_KEYS = frozenset(
    {"reporter_id", "worker_phone", "phone", "original_message_text", "original_message_id", "session_id"}
)
_MEMORY: list[dict[str, Any]] = []
_NOTIFICATIONS: list[dict[str, Any]] = []
_ACKS: dict[str, dict[str, Any]] = {}

_STATS = {"handover_generated": 0, "handover_model_calls": 0, "handover_fallback": 0, "handover_slack_posted": 0}


def reset_handover_stats() -> None:
    _STATS.update(
        {"handover_generated": 0, "handover_model_calls": 0, "handover_fallback": 0, "handover_slack_posted": 0}
    )
    _MEMORY.clear()
    _NOTIFICATIONS.clear()
    _ACKS.clear()


def handover_notifications() -> list[dict[str, Any]]:
    return list(_NOTIFICATIONS)


def load_handover_config() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "config.yaml"
    data: dict[str, Any] = {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            data = loaded.get("handover") or {}
    except OSError:
        data = {}
    timeout = data.get("verification_timeout_hours", 24)
    try:
        timeout_hours = max(1, int(timeout))
    except (TypeError, ValueError):
        timeout_hours = 24
    return {
        "morning_shift_end": str(data.get("morning_shift_end") or "14:00"),
        "evening_shift_end": str(data.get("evening_shift_end") or "22:00"),
        "verification_timeout_hours": timeout_hours,
    }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get(obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(obj, dict) and obj.get(name) is not None:
            return obj[name]
        if hasattr(obj, name):
            value = getattr(obj, name)
            if value is not None:
                return value
    return default


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _risk_key(value: Any) -> str:
    return str(value or "").strip().upper()


def _risk_label(value: Any) -> str:
    key = _risk_key(value)
    return key.title() if key else "Unknown"


def _is_closed(status: Any) -> bool:
    display = to_display_status(status) or str(status or "")
    return display.replace("_", " ").strip().lower() == STATUS_CLOSED.lower()


def _is_awaiting_verification(status: Any) -> bool:
    display = to_display_status(status) or str(status or "")
    return display.replace("_", " ").strip().lower() == STATUS_AWAITING_VERIFICATION.lower()


def _incident_id(row: Any) -> str:
    return str(_get(row, "incident_ref", "incident_id", "id") or "unknown")


def _category(row: Any) -> str:
    return str(_get(row, "hazard_category", "category") or "unspecified")


def _location(row: Any) -> str:
    return str(_get(row, "location") or "Unknown")


def _status_label(row: Any) -> str:
    return to_display_status(_get(row, "status")) or str(_get(row, "status") or "Unknown")


def _reviewed(row: Any, updates: list[Any] | None, assignment: Any) -> bool:
    if bool(_get(row, "reviewed_by_human", default=False)):
        return True
    if assignment is not None and _get(assignment, "acknowledged_at"):
        return True
    for update in updates or []:
        if bool(_get(update, "reviewed_by_human", default=False)):
            return True
        meta = _get(update, "metadata") or {}
        if isinstance(meta, dict) and meta.get("reviewed_by_human") is True:
            return True
        actor = str(_get(update, "actor_type") or "").lower()
        kind = str(_get(update, "update_type") or "").lower()
        if actor in {"safety_officer", "officer"} and kind in {
            "human_review",
            "closed",
            "slack_closed",
            "acknowledged",
            "review_completed",
        }:
            return True
    return False


def _strip_pii(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        if key in _PII_KEYS:
            continue
        if isinstance(value, dict):
            cleaned[key] = _strip_pii(value)
        elif isinstance(value, list):
            cleaned[key] = [_strip_pii(item) if isinstance(item, dict) else item for item in value]
        else:
            cleaned[key] = value
    return cleaned


def collect_handover_snapshot(
    incidents: list[Any],
    *,
    shift_label: str,
    now: datetime | None = None,
    previous_generated_at: datetime | None = None,
    verification_timeout_hours: int = 24,
    updates_by_id: dict[str, list[Any]] | None = None,
    assignments_by_id: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pure incident analysis used before the single LLM phrasing call."""
    clock = now or _utcnow()
    cutoff = previous_generated_at or (clock - timedelta(hours=8))
    timeout = timedelta(hours=max(1, int(verification_timeout_hours)))
    updates_by_id = updates_by_id or {}
    assignments_by_id = assignments_by_id or {}

    new_incidents: list[dict[str, Any]] = []
    open_incidents: list[dict[str, Any]] = []
    review_needed: list[dict[str, Any]] = []
    overdue: list[dict[str, Any]] = []

    for row in incidents:
        ident = _incident_id(row)
        created = _parse_dt(_get(row, "created_at", "reported_date")) or clock
        status = _get(row, "status")
        risk = _risk_label(_get(row, "current_risk_level", "risk_level"))
        item = {
            "incident_id": ident,
            "category": _category(row),
            "location": _location(row),
            "risk_level": risk,
            "timestamp": created.isoformat(),
            "status": _status_label(row),
            "assigned_team": str(
                _get(assignments_by_id.get(ident), "team", "assigned_to")
                or _get(row, "assigned_team", "assigned_officer")
                or "Unassigned"
            ),
        }
        if created >= cutoff:
            new_incidents.append(item)
        if not _is_closed(status):
            open_incidents.append(item)
            if _risk_key(risk) in {"HIGH", "CRITICAL"} and not _reviewed(
                row, updates_by_id.get(ident) or updates_by_id.get(str(_get(row, "id"))), assignments_by_id.get(ident)
            ):
                review_needed.append(item)
        if _is_awaiting_verification(status):
            stamp = _parse_dt(_get(row, "updated_at", "created_at", "reported_date")) or created
            if clock - stamp >= timeout:
                overdue.append(item)

    critical_open = [item for item in open_incidents if _risk_key(item["risk_level"]) == "CRITICAL"]
    ranked = sorted(open_incidents, key=lambda item: _RISK_RANK.get(_risk_key(item["risk_level"]), 0), reverse=True)
    top_risks = [
        {
            "location": item["location"],
            "category": item["category"],
            "risk": item["risk_level"],
            "incident_id": item["incident_id"],
        }
        for item in ranked[:5]
        if _RISK_RANK.get(_risk_key(item["risk_level"]), 0) >= 3
    ] or [
        {
            "location": item["location"],
            "category": item["category"],
            "risk": item["risk_level"],
            "incident_id": item["incident_id"],
        }
        for item in ranked[:3]
    ]

    snapshot = {
        "shift": shift_label,
        "new_incidents": len(new_incidents),
        "open_incidents": len(open_incidents),
        "critical_open_incidents": len(critical_open),
        "human_review_required": len(review_needed),
        "awaiting_verification_overdue": len(overdue),
        "top_risks": top_risks,
        "new_incident_rows": new_incidents[:20],
        "open_incident_rows": open_incidents[:40],
        "review_rows": review_needed[:20],
        "overdue_rows": overdue[:20],
        "critical_rows": critical_open[:20],
    }
    return _strip_pii(snapshot)


def _fallback_summary(snapshot: dict[str, Any]) -> str:
    shift = snapshot.get("shift") or "Shift"
    top = (snapshot.get("top_risks") or [{}])[0]
    location = top.get("location") or "priority locations"
    category = top.get("category") or "open hazards"
    risk = top.get("risk") or "Critical"
    lines = [
        f"{shift} Safety Handover",
        "",
        f"• {snapshot.get('new_incidents', 0)} new incidents reported",
        f"• {snapshot.get('open_incidents', 0)} incidents remain open",
        f"• {snapshot.get('critical_open_incidents', 0)} Critical incident(s) still open",
        f"• {snapshot.get('human_review_required', 0)} High/Critical incidents awaiting human review",
        f"• {snapshot.get('awaiting_verification_overdue', 0)} verification request overdue",
        "",
        "Priority:",
        f"Inspect {location} {category} ({risk}) before next shift.",
    ]
    return "\n".join(lines)


def _extract_text(content: str | None) -> str:
    raw = (content or "").strip()
    if not raw:
        return ""
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            for key in ("summary_text", "summary", "text"):
                if parsed.get(key):
                    return str(parsed[key]).strip()
    return raw


def _looks_invented(summary: str, snapshot: dict[str, Any]) -> bool:
    allowed_ids = {str(item.get("incident_id")) for item in snapshot.get("open_incident_rows") or []}
    allowed_ids.update(str(item.get("incident_id")) for item in snapshot.get("new_incident_rows") or [])
    for match in re.findall(r"\bINC-[A-Z0-9-]+\b", summary, flags=re.I):
        if match not in allowed_ids and allowed_ids:
            return True
    return False


def _model_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "shift": snapshot.get("shift"),
        "new_incidents": snapshot.get("new_incidents"),
        "open_incidents": snapshot.get("open_incidents"),
        "critical_open_incidents": snapshot.get("critical_open_incidents"),
        "human_review_required": snapshot.get("human_review_required"),
        "awaiting_verification_overdue": snapshot.get("awaiting_verification_overdue"),
        "top_risks": snapshot.get("top_risks") or [],
    }


def _timeline(now: datetime, slack_posted: bool) -> list[dict[str, str]]:
    t0 = now.replace(second=0, microsecond=0)
    t1 = t0 + timedelta(minutes=1)
    t2 = t1
    t3 = t0 + timedelta(minutes=2)
    events = [
        {"time": t0.strftime("%H:%M"), "event": "Previous shift ended"},
        {"time": t1.strftime("%H:%M"), "event": "Incidents collected"},
        {"time": t2.strftime("%H:%M"), "event": "AI summary generated"},
    ]
    if slack_posted:
        events.append({"time": t3.strftime("%H:%M"), "event": "Slack posted"})
    return events


def _explain(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "open_incidents": int(snapshot.get("open_incidents") or 0),
        "critical_incidents": int(snapshot.get("critical_open_incidents") or 0),
        "pending_reviews": int(snapshot.get("human_review_required") or 0),
        "overdue_verification": int(snapshot.get("awaiting_verification_overdue") or 0),
        "new_incidents": int(snapshot.get("new_incidents") or 0),
        "ai_role": ROLE_FAST,
        "ai_calls": 1,
        "note": "The model only rewrote structured counts. It did not add incidents or risks.",
    }


def _public_record(row: dict[str, Any]) -> dict[str, Any]:
    generated = row.get("generated_at")
    if isinstance(generated, datetime):
        generated_at = generated.isoformat()
    else:
        generated_at = generated
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    return {
        "handover_id": str(row.get("handover_id")),
        "shift_label": row.get("shift_label"),
        "summary_text": row.get("summary_text"),
        "open_incident_count": int(row.get("open_incident_count") or 0),
        "critical_open_count": int(row.get("critical_open_count") or 0),
        "generated_at": generated_at,
        "generated_by": row.get("generated_by") or GENERATED_BY_AGENT,
        "new_incidents": payload.get("new_incidents", 0),
        "human_review_required": payload.get("human_review_required", 0),
        "awaiting_verification_overdue": payload.get("awaiting_verification_overdue", 0),
        "top_risks": payload.get("top_risks") or [],
        "timeline": payload.get("timeline") or [],
        "explainability": payload.get("explainability") or {},
        "slack_posted": bool(row.get("slack_posted")),
        "structured": _model_payload(payload) if payload else {},
        "incident_ids": [
            item.get("incident_id")
            for item in (payload.get("open_incident_rows") or []) + (payload.get("new_incident_rows") or [])
            if item.get("incident_id")
        ],
        "acknowledged": _ACKS.get(str(row.get("handover_id"))),
    }


def _persist(repository: Any, row: dict[str, Any]) -> dict[str, Any]:
    stored = dict(row)
    if repository is not None and hasattr(repository, "create_handover_summary"):
        try:
            created = repository.create_handover_summary(row)
            if isinstance(created, dict):
                stored.update(created)
            elif created is not None:
                stored["handover_id"] = _get(created, "handover_id", "id") or stored["handover_id"]
        except Exception:
            log.warning("handover_persist_failed")
            _MEMORY.append(stored)
            return stored
    else:
        _MEMORY.append(stored)
    return stored


def list_stored_handovers(repository: Any | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if repository is not None and hasattr(repository, "list_handover_summaries"):
        try:
            raw = repository.list_handover_summaries() or []
            for item in raw:
                if isinstance(item, dict):
                    rows.append(item)
                else:
                    rows.append(
                        {
                            "handover_id": _get(item, "handover_id", "id"),
                            "shift_label": _get(item, "shift_label"),
                            "generated_at": _get(item, "generated_at"),
                            "summary_text": _get(item, "summary_text"),
                            "open_incident_count": _get(item, "open_incident_count", default=0),
                            "critical_open_count": _get(item, "critical_open_count", default=0),
                            "generated_by": _get(item, "generated_by"),
                            "slack_posted": _get(item, "slack_posted", default=False),
                            "payload": _get(item, "payload") or {},
                        }
                    )
        except Exception:
            log.warning("handover_list_failed")
    if not rows:
        rows = list(_MEMORY)
    rows.sort(key=lambda item: str(item.get("generated_at") or ""), reverse=True)
    return rows


def get_latest_handover(repository: Any | None = None) -> dict[str, Any] | None:
    if repository is not None and hasattr(repository, "get_latest_handover"):
        try:
            latest = repository.get_latest_handover()
            if isinstance(latest, dict) and latest.get("handover_id"):
                return _public_record(latest)
            if latest is not None and _get(latest, "handover_id"):
                return _public_record(
                    {
                        "handover_id": _get(latest, "handover_id"),
                        "shift_label": _get(latest, "shift_label"),
                        "generated_at": _get(latest, "generated_at"),
                        "summary_text": _get(latest, "summary_text"),
                        "open_incident_count": _get(latest, "open_incident_count", default=0),
                        "critical_open_count": _get(latest, "critical_open_count", default=0),
                        "generated_by": _get(latest, "generated_by"),
                        "slack_posted": _get(latest, "slack_posted", default=False),
                        "payload": _get(latest, "payload") or {},
                    }
                )
        except Exception:
            log.warning("handover_latest_failed")
    rows = list_stored_handovers(repository)
    return _public_record(rows[0]) if rows else None


def mentions_for_incident(incident_id: str, repository: Any | None = None) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for row in list_stored_handovers(repository):
        public = _public_record(row)
        ids = {str(item) for item in public.get("incident_ids") or []}
        top = {str(item.get("incident_id")) for item in public.get("top_risks") or []}
        if incident_id in ids or incident_id in top:
            found.append(
                {
                    "handover_id": public["handover_id"],
                    "shift_label": public["shift_label"],
                    "generated_at": public["generated_at"],
                    "critical_open_count": public["critical_open_count"],
                }
            )
    return found


def handover_analytics(repository: Any | None = None) -> dict[str, Any]:
    rows = [_public_record(item) for item in list_stored_handovers(repository)]
    total = len(rows)
    avg_open = round(sum(item["open_incident_count"] for item in rows) / total, 1) if total else 0.0
    avg_critical = round(sum(item["critical_open_count"] for item in rows) / total, 1) if total else 0.0
    risk_counts: dict[str, int] = {}
    for item in rows:
        for risk in item.get("top_risks") or []:
            label = f"{risk.get('location') or 'Unknown'} / {risk.get('category') or 'unspecified'}"
            risk_counts[label] = risk_counts.get(label, 0) + 1
    common = sorted(risk_counts.items(), key=lambda pair: pair[1], reverse=True)[:5]
    morning = [item for item in rows if "morning" in str(item.get("shift_label") or "").lower()]
    evening = [item for item in rows if "evening" in str(item.get("shift_label") or "").lower()]
    return {
        "total_handovers": total,
        "average_open_incidents": avg_open,
        "average_critical_alerts": avg_critical,
        "most_common_shift_risks": [{"label": label, "count": count} for label, count in common],
        "compare": {
            "morning": {
                "shift": "Morning Shift",
                "count": len(morning),
                "critical": morning[0]["critical_open_count"] if morning else 0,
                "open": morning[0]["open_incident_count"] if morning else 0,
            },
            "evening": {
                "shift": "Evening Shift",
                "count": len(evening),
                "critical": evening[0]["critical_open_count"] if evening else 0,
                "open": evening[0]["open_incident_count"] if evening else 0,
            },
        },
        "items": rows,
    }


def handover_pdf_bytes(record: dict[str, Any]) -> bytes:
    lines = [
        "SentinelLoop Safety Shift Handover",
        str(record.get("shift_label") or "Shift"),
        f"Generated: {record.get('generated_at') or ''}",
        f"Generated by: {record.get('generated_by') or GENERATED_BY_AGENT}",
        "",
        str(record.get("summary_text") or ""),
        "",
        f"Open: {record.get('open_incident_count', 0)}  Critical: {record.get('critical_open_count', 0)}",
        "",
        "How this handover was generated:",
        json.dumps(record.get("explainability") or {}, indent=2),
    ]
    body = "\n".join(lines)
    escaped_lines = []
    for line in body.splitlines()[:70]:
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")[:110]
        escaped_lines.append(f"({safe}) Tj 0 -14 Td")
    stream = ("BT /F1 11 Tf 48 760 Td\n" + "\n".join(escaped_lines) + "\nET").encode("latin-1", "replace")
    objs = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n",
        b"4 0 obj << /Length " + str(len(stream)).encode("ascii") + b" >> stream\n" + stream + b"\nendstream endobj\n",
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
    ]
    header = b"%PDF-1.4\n"
    offsets = [0]
    cursor = len(header)
    out = header
    for obj in objs:
        offsets.append(cursor)
        out += obj
        cursor += len(obj)
    xref = f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii")
    for offset in offsets[1:]:
        xref += f"{offset:010d} 00000 n \n".encode("ascii")
    trailer = f"trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{cursor}\n%%EOF\n".encode("ascii")
    return out + xref + trailer


def _safety_channel(slack: Any | None) -> str | None:
    env = (os.environ.get("SLACK_CHANNEL_SAFETY_SUPERVISOR") or "").strip()
    if slack is not None and hasattr(slack, "channel_for_team"):
        return slack.channel_for_team(SAFETY_TEAM) or env or None
    return env or None


async def _post_slack(slack: Any | None, record: dict[str, Any], snapshot: dict[str, Any]) -> bool:
    if slack is None:
        return False
    channel = _safety_channel(slack)
    if not channel:
        log.warning("handover_slack_channel_missing")
        return False
    from integrations.slack_handler import build_handover_blocks, handover_fallback_text

    blocks = build_handover_blocks(record=record, snapshot=snapshot)
    text = handover_fallback_text(record=record, snapshot=snapshot)
    try:
        posted = await slack.post_incident_message(channel=channel, blocks=blocks, text=text)
        _STATS["handover_slack_posted"] += 1
        return bool(posted)
    except Exception:
        log.warning("handover_slack_post_failed")
        return False


def _push_critical_notification(record: dict[str, Any]) -> None:
    if int(record.get("critical_open_count") or 0) <= 0:
        return
    _NOTIFICATIONS.insert(
        0,
        {
            "id": f"handover-{record['handover_id']}",
            "title": "Critical handover items",
            "body": CRITICAL_NOTICE,
            "time": "just now",
            "severity": "CRITICAL",
            "handover_id": str(record["handover_id"]),
            "shift_label": record.get("shift_label"),
        },
    )


async def generate_handover_summary(
    shift_label: str,
    *,
    repository: Any | None = None,
    call_model_fn: Any | None = None,
    slack: Any | None = None,
    now: datetime | None = None,
    generated_by: str = GENERATED_BY_AGENT,
) -> dict[str, Any]:
    """Collect facts, phrase them with one role_fast call, persist, and notify Slack."""
    clock = now or _utcnow()
    config = load_handover_config()
    repo = repository
    if repo is None:
        try:
            from database.repository import IncidentRepository

            repo = IncidentRepository()
        except Exception:
            repo = None

    incidents: list[Any] = []
    if repo is not None and hasattr(repo, "list_incidents"):
        incidents = list(repo.list_incidents() or [])
        if hasattr(repo, "list_all_incidents") and len(incidents) >= 50:
            incidents = list(repo.list_all_incidents() or incidents)

    previous = None
    latest = get_latest_handover(repo)
    if latest and latest.get("generated_at"):
        previous = _parse_dt(latest.get("generated_at"))

    updates_by_id: dict[str, list[Any]] = {}
    assignments_by_id: dict[str, Any] = {}
    if repo is not None:
        for row in incidents:
            ident = _incident_id(row)
            pk = _get(row, "id", "incident_ref")
            if hasattr(repo, "list_updates_for_incident") and pk is not None:
                try:
                    updates_by_id[ident] = list(repo.list_updates_for_incident(pk) or [])
                except Exception:
                    updates_by_id[ident] = []
            if hasattr(repo, "get_assignment_for_incident") and pk is not None:
                try:
                    assignments_by_id[ident] = repo.get_assignment_for_incident(pk)
                except Exception:
                    assignments_by_id[ident] = None

    snapshot = collect_handover_snapshot(
        incidents,
        shift_label=shift_label,
        now=clock,
        previous_generated_at=previous,
        verification_timeout_hours=int(config["verification_timeout_hours"]),
        updates_by_id=updates_by_id,
        assignments_by_id=assignments_by_id,
    )

    summary = _fallback_summary(snapshot)
    used_model = False
    caller = call_model_fn or call_model
    messages = [
        {"role": "system", "content": HANDOVER_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(_model_payload(snapshot), ensure_ascii=True)},
    ]
    try:
        result = await caller(role=ROLE_FAST, messages=messages)
        _STATS["handover_model_calls"] += 1
        used_model = True
        content = result.content if isinstance(result, ModelCallResult) else getattr(result, "content", str(result))
        phrased = _extract_text(content)
        if phrased and not _looks_invented(phrased, snapshot):
            summary = phrased
        else:
            used_model = False
    except Exception:
        log.warning("handover_model_failed")
        used_model = False

    if not used_model:
        _STATS["handover_fallback"] += 1

    handover_id = uuid4()
    snapshot["explainability"] = _explain(snapshot)
    snapshot["explainability"]["ai_calls"] = 1 if used_model else 0
    snapshot["timeline"] = _timeline(clock, slack_posted=False)
    row = {
        "handover_id": handover_id,
        "shift_label": shift_label,
        "generated_at": clock,
        "summary_text": summary,
        "open_incident_count": int(snapshot.get("open_incidents") or 0),
        "critical_open_count": int(snapshot.get("critical_open_incidents") or 0),
        "generated_by": generated_by,
        "slack_posted": False,
        "payload": snapshot,
    }
    public = _public_record(row)
    slack_ok = await _post_slack(slack, public, snapshot)
    row["slack_posted"] = slack_ok
    snapshot["timeline"] = _timeline(clock, slack_posted=slack_ok)
    row["payload"] = snapshot
    stored = _persist(repo, row)
    _STATS["handover_generated"] += 1
    record = _public_record(stored)
    _push_critical_notification(record)
    log.info("handover_generated shift=%s critical=%s", shift_label, record["critical_open_count"])
    return record


def acknowledge_handover(handover_id: str, *, actor: str | None = None) -> dict[str, Any]:
    _ACKS[str(handover_id)] = {
        "actor": actor or "safety_officer",
        "at": _utcnow().isoformat(),
        "status": "acknowledged",
    }
    return {"success": True, "handover_id": str(handover_id), "status": "acknowledged"}


async def handle_handover_thread_command(event: dict[str, Any], command: dict[str, str]) -> dict[str, Any]:
    handover_id = str(event.get("thread_ts") or event.get("ts") or "")
    kind = command.get("command")
    if kind in {"handover_ack"}:
        return acknowledge_handover(handover_id, actor=event.get("user"))
    if kind in {"handover_assign", "handover_escalate"}:
        return {"success": True, "handover_id": handover_id, "status": kind.replace("handover_", "")}
    return {"success": False, "handover_id": handover_id}


async def handle_handover_action(action_id: str, handover_id: str, *, actor: str | None = None) -> dict[str, Any]:
    if action_id.endswith("acknowledge"):
        return acknowledge_handover(handover_id, actor=actor)
    return {"success": True, "handover_id": handover_id, "action": action_id}


def shift_label_for_now(now: datetime | None = None) -> str:
    clock = now or _utcnow()
    config = load_handover_config()
    stamp = clock.strftime("%H:%M")
    evening_end = str(config.get("evening_shift_end") or "22:00")
    morning_end = str(config.get("morning_shift_end") or "14:00")
    if stamp >= evening_end or stamp < "06:00":
        return "Evening Shift"
    if stamp >= morning_end:
        return "Evening Shift"
    return "Morning Shift"
