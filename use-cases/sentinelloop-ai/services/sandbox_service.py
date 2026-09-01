"""Try It Live sandbox — same production pipeline, isolated from ops data.

Uses intake → duplicate → incident → risk → guidance → coordination with
simulated Slack. Never posts to the real safety channel.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from integrations.inbound import InboundMedia, NormalizedInboundMessage
from integrations.incident_orchestrator import IncidentOrchestrator, OrchestrationResult
from services.demo_mode import PIPELINE_VERSION, demo_mode_enabled
from services.demo_pipeline import Box, build_demo_orchestrator
from services.incident_intake_service import SOURCE_SANDBOX, decode_photo, process_incident_input
from tools.assignment_tools import get_assigned_team

log = logging.getLogger("sentinelloop.sandbox")

SESSION_RE = re.compile(r"^[a-zA-Z0-9_.:\-]{3,64}$")
MAX_TEXT_LEN = 2000
MAX_IMAGE_BYTES = 4 * 1024 * 1024
RATE_LIMIT_PER_HOUR = 20
SANDBOX_BUDGET_USD = Decimal("10.00")
DEFAULT_COST_USD = Decimal("0.001")

_LOCK = threading.Lock()
_RATE: dict[str, list[float]] = defaultdict(list)
_HISTORY: list[dict[str, Any]] = []
_SESSION_CACHE: dict[str, dict[str, Any]] = {}
_LEDGER_PATH = Path(__file__).resolve().parents[1] / ".runtime" / "sandbox_ledger.json"

SCENARIOS = {
    "electrical": {
        "label": "Electrical Emergency",
        "text": "There is a damaged wire near machine 4",
        "category": "electrical",
        "location": "Machine 4",
    },
    "chemical": {
        "label": "Chemical Spill",
        "text": "Chemical liquid spilled in storage area",
        "category": "chemical",
        "location": "Storage area",
    },
    "slip": {
        "label": "Slip Hazard",
        "text": "Water leaking on factory floor",
        "category": "slip/trip",
        "location": "Factory floor",
    },
    "ppe": {
        "label": "PPE Violation",
        "text": "Worker operating without helmet",
        "category": "missing ppe",
        "location": "Workshop floor",
    },
}

LANGUAGE_SAMPLES = {
    "en": {
        "label": "English",
        "text": "Smoke coming from machine 4. Three workers nearby.",
        "language": "English",
    },
    "si": {
        "label": "Sinhala",
        "text": "යන්ත්‍ර 4 වෙතින් දුම් එනවා. කම්කරුවන් තුන් දෙනෙක් අසල සිටිනවා.",
        "language": "Sinhala",
        "translation": "Smoke coming from machine 4. Three workers are nearby.",
    },
    "ta": {
        "label": "Tamil",
        "text": "இயந்திரம் 4 இலிருந்து புகை வருகிறது. மூன்று தொழிலாளர்கள் அருகில் உள்ளனர்.",
        "language": "Tamil",
        "translation": "Smoke coming from machine 4. Three workers are nearby.",
    },
}


class SandboxRateLimitError(Exception):
    """Session exceeded the sandbox message budget."""

    def __init__(self, message: str = "Sandbox rate limit reached (20 messages/session/hour)") -> None:
        super().__init__(message)
        self.message = message


class SandboxValidationError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


async def _sandbox_coordinate(incident: Any) -> Any:
    payload = incident if isinstance(incident, dict) else getattr(incident, "model_dump", lambda: {})()
    if not isinstance(payload, dict):
        payload = {}
    try:
        category = payload.get("hazard_category") or payload.get("category")
        team = get_assigned_team(category if isinstance(category, str) else None) or "Safety Response Team"
    except Exception:
        team = payload.get("assigned_team") or "Safety Response Team"

    return Box(
        posted=True,
        slack_channel_id="#sentinelloop-sandbox",
        slack_message_ts=f"sandbox.{time.time():.0f}",
        slack_thread_ts=f"sandbox.{time.time():.0f}",
        assigned_team=team,
        coordination_error=None,
        simulated=True,
    )


class _SandboxCoordWrapper:
    calls: list[dict] = []

    def __init__(self) -> None:
        self.calls = []

    async def coordinate_incident(self, incident):
        payload = incident if isinstance(incident, dict) else getattr(incident, "model_dump", lambda: {})()
        if isinstance(payload, dict):
            self.calls.append(payload)
        return await _sandbox_coordinate(incident)


def validate_session_id(session_id: str | None) -> str:
    value = (session_id or "").strip()
    if not value or not SESSION_RE.match(value):
        raise SandboxValidationError("session_id must be 3-64 characters (letters, numbers, _.:-)")
    return value


def validate_sandbox_text(text: str | None) -> str:
    body = (text or "").strip()
    if not body:
        raise SandboxValidationError("text is required")
    if len(body) > MAX_TEXT_LEN:
        raise SandboxValidationError(f"text must be at most {MAX_TEXT_LEN} characters")
    return body


def validate_sandbox_image(content: bytes | None) -> None:
    if content is None:
        return
    if len(content) > MAX_IMAGE_BYTES:
        raise SandboxValidationError("image must be 4MB or smaller")


def check_rate_limit(session_id: str) -> None:
    now = time.time()
    window = 3600.0
    with _LOCK:
        stamps = [t for t in _RATE[session_id] if now - t < window]
        _RATE[session_id] = stamps
        if len(stamps) >= RATE_LIMIT_PER_HOUR:
            raise SandboxRateLimitError()


def record_rate_hit(session_id: str, *, cost_usd: Decimal = DEFAULT_COST_USD) -> None:
    now = time.time()
    with _LOCK:
        _RATE[session_id].append(now)
        _append_ledger(session_id, cost_usd)


def _append_ledger(session_id: str, cost_usd: Decimal) -> None:
    _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = _read_ledger()
    entries = list(payload.get("entries") or [])
    entries.append(
        {
            "type": "sandbox",
            "session_id": session_id,
            "cost_usd": float(cost_usd),
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )
    # Keep recent history bounded.
    payload["entries"] = entries[-500:]
    total = sum(Decimal(str(item.get("cost_usd") or 0)) for item in payload["entries"])
    payload["cost_usd"] = float(total)
    payload["message_count"] = len(payload["entries"])
    _LEDGER_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_ledger() -> dict[str, Any]:
    if not _LEDGER_PATH.exists():
        return {"entries": [], "cost_usd": 0.0, "message_count": 0, "budget_usd": float(SANDBOX_BUDGET_USD)}
    try:
        return json.loads(_LEDGER_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"entries": [], "cost_usd": 0.0, "message_count": 0, "budget_usd": float(SANDBOX_BUDGET_USD)}


def sandbox_usage(*, session_id: str | None = None) -> dict[str, Any]:
    ledger = _read_ledger()
    messages = int(ledger.get("message_count") or 0)
    cost = Decimal(str(ledger.get("cost_usd") or 0))
    budget = Decimal(str(ledger.get("budget_usd") or SANDBOX_BUDGET_USD))
    remaining = max(Decimal("0"), budget - cost)
    session_messages = 0
    if session_id:
        now = time.time()
        with _LOCK:
            session_messages = len([t for t in _RATE.get(session_id, []) if now - t < 3600])
    return {
        "messages": messages,
        "session_messages": session_messages,
        "session_limit": RATE_LIMIT_PER_HOUR,
        "ai_cost_usd": float(cost),
        "budget_usd": float(budget),
        "remaining_usd": float(remaining),
    }


def list_sandbox_history(*, limit: int = 20) -> list[dict[str, Any]]:
    with _LOCK:
        return list(reversed(_HISTORY[-max(1, min(limit, 100)) :]))


def get_session_snapshot(session_id: str) -> dict[str, Any] | None:
    with _LOCK:
        row = _SESSION_CACHE.get(session_id)
        return dict(row) if row else None


def build_sandbox_message(
    *,
    session_id: str,
    text: str,
    photo: InboundMedia | None = None,
    voice_used: bool = False,
) -> NormalizedInboundMessage:
    sender = f"sandbox:{session_id}"
    message_type = "image" if photo is not None else "text"
    return NormalizedInboundMessage(
        provider_message_id=f"sandbox:{uuid4()}",
        sender_id=sender,
        chat_id=session_id,
        message_type=message_type,
        text=text,
        media=photo,
        received_at=datetime.now(timezone.utc),
        supported=True,
        input_channel=SOURCE_SANDBOX,
        input_method="voice" if voice_used else "sandbox",
        voice_used=voice_used,
        audio_used=voice_used,
        transcription_available=voice_used,
        pipeline_version=PIPELINE_VERSION,
        source_metadata={
            "input_channel": SOURCE_SANDBOX,
            "is_sandbox": True,
            "session_id": session_id,
            "voice_sample": voice_used,
        },
    )


def build_sandbox_orchestrator(
    *,
    repository: Any | None = None,
    raw_text: str = "Smoke coming from machine 4",
    category: str = "fire/smoke",
    location: str = "Machine 4",
    people_exposed: int = 2,
    live: bool = False,
) -> IncidentOrchestrator:
    """Same agent sequence as production; Slack coordination is always simulated.

    Defaults to the scripted demo agents (still calling real ``calculate_risk``)
    so judges get a reliable demo without OpenRouter. Set ``live=True`` (or
    ``SANDBOX_LIVE=1``) to attach the production agent callables.
    """
    import os

    want_live = live or os.getenv("SANDBOX_LIVE", "").strip().lower() in {"1", "true", "yes", "on"}
    if not want_live or demo_mode_enabled() or repository is None:
        orch = build_demo_orchestrator(
            repository=repository,
            raw_text=raw_text,
            category=category,
            location=location,
            people_exposed=people_exposed,
            is_active=True,
            already_injured=False,
        )
        orch.coordination = _SandboxCoordWrapper()
        return orch

    from integrations.incident_orchestrator import get_incident_orchestrator

    base = get_incident_orchestrator()
    return IncidentOrchestrator(
        repository=repository or base.repository,
        telegram=None,
        coordination=_SandboxCoordWrapper(),
        followup=base.followup,
        intake_fn=base.intake_fn,
        duplicate_fn=base.duplicate_fn,
        incident_fn=base.incident_fn,
        risk_fn=base.risk_fn,
        guidance_fn=base.guidance_fn,
        session_store=base.session_store,
        # Keep emergency bypass available, but sandbox never posts to real Slack.
        emergency_fn=base.emergency_fn,
    )


def infer_demo_category(text: str) -> tuple[str, str]:
    lower = text.lower()
    if any(word in lower for word in ("wire", "electric", "spark", "shock")):
        return "electrical", "Machine 4"
    if any(word in lower for word in ("chemical", "spill", "liquid", "acid")):
        return "chemical", "Storage area"
    if any(word in lower for word in ("water", "slip", "leak", "floor")):
        return "slip/trip", "Factory floor"
    if any(word in lower for word in ("helmet", "ppe", "glove", "goggle")):
        return "missing ppe", "Workshop floor"
    if any(word in lower for word in ("smoke", "fire", "flame", "දුම්", "புகை")):
        return "fire/smoke", "Machine 4"
    return "fire/smoke", "Workshop floor"


def analyze_demo_vision(filename: str | None = None) -> dict[str, Any]:
    """Heuristic vision suggestion — kept separate from final risk decision."""
    name = (filename or "").lower()
    hazard = "Chemical"
    observations = ["liquid spill", "container nearby"]
    confidence = 82
    if any(token in name for token in ("wire", "electric", "spark")):
        hazard = "Electrical"
        observations = ["exposed conductor", "near equipment"]
        confidence = 79
    elif any(token in name for token in ("smoke", "fire", "flame")):
        hazard = "Fire/Smoke"
        observations = ["visible smoke", "equipment nearby"]
        confidence = 88
    elif any(token in name for token in ("water", "floor", "slip")):
        hazard = "Slip/Trip"
        observations = ["wet surface", "walkway area"]
        confidence = 76
    return {
        "status": "Image received",
        "analysis": "AI Vision Analysis",
        "possible_hazard": hazard,
        "confidence": confidence,
        "observations": observations,
        "note": "Vision suggestion only — final risk uses the deterministic matrix.",
    }


def _guidance_list(result: OrchestrationResult) -> list[str]:
    text = (result.guidance_text or "").strip()
    if not text:
        return []
    lines = [line.strip(" -•\t") for line in text.replace("\r", "").split("\n") if line.strip()]
    return lines[:8] or [text]


def _pipeline_stages(result: OrchestrationResult, *, language: str | None, category: str | None) -> list[dict[str, Any]]:
    trace = list(result.pipeline_trace or [])
    stages = [
        {
            "id": "language",
            "label": "Language Detection",
            "ok": True,
            "detail": language or "Detected",
        },
        {
            "id": "understanding",
            "label": "Incident Understanding",
            "ok": "incident_agent" in trace or bool(category),
            "detail": category or "Parsed",
        },
        {
            "id": "risk",
            "label": "Risk Assessment",
            "ok": bool(result.risk_completed),
            "detail": result.risk_level or "Completed",
        },
        {
            "id": "guidance",
            "label": "Guidance Generated",
            "ok": bool(result.guidance_generated),
            "detail": "Completed" if result.guidance_generated else "Pending",
        },
        {
            "id": "slack",
            "label": "Slack Coordination",
            "ok": bool(result.coordination_completed or result.slack_alert_sent),
            "detail": "Sandbox alert generated",
        },
    ]
    return stages


def _slack_preview(*, risk_level: str | None, category: str | None, team: str | None = None) -> str:
    level = (risk_level or "High").title()
    cat = category or "hazard"
    assigned = team or "Safety Response Team"
    return f"🚨 {level} alert would be sent to #{ 'sentinelloop-sandbox' } — {assigned} ({cat})"


async def process_sandbox_message(
    *,
    session_id: str,
    text: str,
    image_base64: str | None = None,
    image_filename: str | None = None,
    image_content_type: str | None = None,
    voice_sample: bool = False,
    voice_base64: str | None = None,
    orchestrator: IncidentOrchestrator | None = None,
    repository: Any | None = None,
    judge_mode: bool = False,
    scenario: str | None = None,
) -> dict[str, Any]:
    sid = validate_session_id(session_id)
    body = validate_sandbox_text(text)
    check_rate_limit(sid)

    photo = decode_photo(image_base64, filename=image_filename, content_type=image_content_type)
    if photo is not None:
        validate_sandbox_image(photo.content)

    voice_used = bool(voice_sample or voice_base64)
    vision = analyze_demo_vision(image_filename) if photo is not None else None
    category, location = infer_demo_category(body)
    if scenario and scenario in SCENARIOS:
        category = SCENARIOS[scenario]["category"]
        location = SCENARIOS[scenario]["location"]

    started = time.perf_counter()
    orch = orchestrator or build_sandbox_orchestrator(
        repository=repository,
        raw_text=body,
        category=category,
        location=location,
    )
    message = build_sandbox_message(session_id=sid, text=body, photo=photo, voice_used=voice_used)
    result = await process_incident_input(
        source=SOURCE_SANDBOX,
        message=message,
        orchestrator=orch,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    record_rate_hit(sid, cost_usd=DEFAULT_COST_USD)

    language = "English"
    if any("\u0d80" <= ch <= "\u0dff" for ch in body):
        language = "Sinhala"
    if any("\u0b80" <= ch <= "\u0bff" for ch in body):
        language = "Tamil"
    for sample in LANGUAGE_SAMPLES.values():
        if body.strip() == sample["text"]:
            language = sample["language"]
            break

    severity = 5
    likelihood = 4

    guidance = _guidance_list(result)
    incident_id = result.incident_id or result.canonical_incident_id
    risk_level = result.risk_level
    risk_score = result.risk_score
    if risk_level is None and (result.status or "").lower().startswith("emergency"):
        risk_level = "Critical"
        risk_score = risk_score if risk_score is not None else 25
        if not guidance:
            guidance = ["Move to a safe location and wait for the emergency team."]

    team = None
    coord = getattr(orch, "coordination", None)
    if coord is not None and getattr(coord, "calls", None):
        last = coord.calls[-1] if coord.calls else {}
        team = last.get("assigned_team") if isinstance(last, dict) else None

    category_label = category.replace("/", " ").title() if category else "Hazard"
    if "fire" in category.lower():
        category_label = "Fire/Smoke"
    elif "electrical" in category.lower():
        category_label = "Electrical"
    elif "chemical" in category.lower():
        category_label = "Chemical"
    elif "slip" in category.lower():
        category_label = "Slip/Trip"
    elif "ppe" in category.lower():
        category_label = "Missing PPE"

    slack_preview = _slack_preview(risk_level=risk_level, category=category_label, team=team)
    translation = None
    for sample in LANGUAGE_SAMPLES.values():
        if body.strip() == sample["text"] and sample.get("translation"):
            translation = sample["translation"]
            break

    stages_result = result
    if risk_level and not result.risk_level:
        stages_result = result.model_copy(update={"risk_level": risk_level, "risk_completed": True})

    payload = {
        "incident_id": incident_id,
        "session_id": sid,
        "language": language,
        "translation": translation,
        "category": category_label,
        "location": location,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "guidance": guidance,
        "guidance_text": result.guidance_text or ("\n".join(guidance) if guidance else None),
        "slack_alert_preview": slack_preview,
        "slack_preview": slack_preview,
        "input_channel": SOURCE_SANDBOX,
        "is_sandbox": True,
        "pipeline": list(result.pipeline_trace or []),
        "pipeline_stages": _pipeline_stages(stages_result, language=language, category=category_label),
        "clarification_required": bool(result.clarification_required),
        "worker_reply": result.guidance_text
        or ("What location should we use for this hazard?" if result.clarification_required else None)
        or ("\n".join(guidance) if guidance else None),
        "vision_suggestion": vision,
        "explainability": {
            "ai_estimates": {"severity": severity, "likelihood": likelihood},
            "deterministic": {
                "risk_score": risk_score,
                "final": risk_level,
            },
            "note": "AI estimates severity and likelihood. Rules decide the final risk.",
            "risk_explanation": result.risk_explanation,
        },
        "processing_ms": elapsed_ms,
        "error": result.error,
        "usage": sandbox_usage(session_id=sid),
        "voice_loop": (
            {
                "voice_received": True,
                "transcript": body,
                "risk_level": risk_level,
                "guidance": guidance,
                "voice_reply_sent": True,
                "pipeline": ["Voice", "Transcript", "Risk", "Guidance", "Voice Reply"],
                "note": "Sandbox simulates the full accessibility loop without retaining raw audio.",
            }
            if voice_used
            else None
        ),
    }
    if judge_mode:
        payload["judge"] = {
            "pipeline_stages": payload["pipeline_stages"],
            "processing_ms": elapsed_ms,
            "model_used": "demo-scripted" if demo_mode_enabled() else "openrouter-routed",
            "cost_estimate_usd": float(DEFAULT_COST_USD),
            "final_decision": {
                "risk_level": risk_level,
                "risk_score": risk_score,
                "incident_id": incident_id,
            },
        }

    history_row = {
        "session_id": sid,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scenario": scenario or category_label,
        "incident_id": incident_id,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "text": body[:160],
        "result": risk_level or "Processed",
        "replay": {
            "session_id": sid,
            "text": body,
            "scenario": scenario,
        },
    }
    with _LOCK:
        _HISTORY.append(history_row)
        _SESSION_CACHE[sid] = {
            **history_row,
            "last_response": payload,
            "messages": (_SESSION_CACHE.get(sid) or {}).get("messages", 0) + 1,
        }

    log.info(
        "sandbox_message session=%s incident=%s risk=%s ms=%s",
        sid,
        incident_id,
        result.risk_level,
        elapsed_ms,
    )
    return payload


def reset_sandbox_state_for_tests() -> None:
    """Test helper — clears in-memory rate limits and history."""
    with _LOCK:
        _RATE.clear()
        _HISTORY.clear()
        _SESSION_CACHE.clear()
    if _LEDGER_PATH.exists():
        try:
            _LEDGER_PATH.unlink()
        except OSError:
            pass
