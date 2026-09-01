"""Outbound validation for guidance, closure, privacy, and model budget.

Registered as an Agent Kernel PostHook on user-facing replies. Inner handoffs
are not hooked by Agent Kernel 0.6.0 — agents must call these functions directly.

The knowledge base is the single source of truth for safety instructions.
An optional LLM judge must never approve invented procedures.
"""

from __future__ import annotations

import logging
import os
import re
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import Any

from agentkernel.core.hooks import PostHook
from agentkernel.core.model import AgentReply, AgentReplyText
from pydantic import BaseModel, ConfigDict, Field

from guardrails.config import load_guardrail_config
from guardrails.events import (
    EVENT_BUDGET_BLOCKED,
    EVENT_BUDGET_WARNING,
    EVENT_CLOSURE_BLOCKED,
    EVENT_FAILED,
    EVENT_GUIDANCE_BLOCKED,
    EVENT_MODEL_ALLOWED,
    EVENT_MODEL_BLOCKED_BUDGET,
    EVENT_PASSED,
    EVENT_PRIVACY_REDACTION,
    emit_guardrail_event,
)

log = logging.getLogger("sentinelloop.guardrails.output")

# SPEC.md Rule: AI-generated safety instructions must be grounded
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_WORD_RE = re.compile(r"[a-z0-9]+", re.I)
_PHONE_RE = re.compile(r"(?:\+|00)?(?:94|1)?[\s\-()]*(?:\d[\s\-()]*){9,15}")
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", re.I)
_TELEGRAM_ID_RE = re.compile(r"\b(?:telegram:|t\.me/)\S+\b", re.I)
_API_KEY_RE = re.compile(r"\b(?:sk-|sk-or-|xoxb-|xoxp-|ghp_)[A-Za-z0-9_\-]{8,}\b")

HUMAN_REVIEW_LEVELS = frozenset({"high", "critical"})
AUTO_CLOSE_LEVELS = frozenset({"low", "medium"})
SLACK_CLOSED_ACTIONS = frozenset({"closed", "incident_closed"})
PRIVACY_KEYS = frozenset(
    {
        "phone",
        "phone_number",
        "worker_chat_id",
        "reporter_id",
        "telegram_id",
        "telegram_chat_id",
        "telegram_user_id",
        "email",
        "email_address",
        "name",
        "full_name",
        "display_name",
        "national_id",
        "nic",
    }
)


class GuidanceValidation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    approved: bool
    violations: list[str] = Field(default_factory=list)
    matched_lines: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class ClosureValidation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    approved: bool
    human_review_required: bool = False
    violations: list[str] = Field(default_factory=list)
    decision: str | None = None


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _normalize_sentence(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip().lower())
    return cleaned.strip(" .;:!?")


def _sentences(text: str) -> list[str]:
    parts = [part.strip() for part in _SENTENCE_SPLIT.split(text or "") if part and part.strip()]
    return parts or ([text.strip()] if text and text.strip() else [])


def _kb_lines(knowledge_base: Any) -> list[str]:
    if knowledge_base is None:
        return []
    if isinstance(knowledge_base, str):
        return [
            line.lstrip("- ").strip()
            for line in knowledge_base.splitlines()
            if line.strip() and not line.startswith("#")
        ]
    if isinstance(knowledge_base, (list, tuple)):
        lines: list[str] = []
        for item in knowledge_base:
            if isinstance(item, str):
                lines.append(item)
            else:
                text = getattr(item, "text", None) or getattr(item, "source_text", None)
                if text:
                    lines.append(str(text))
        return lines
    dump = getattr(knowledge_base, "action_lines", None)
    if dump:
        return [str(getattr(line, "text", line)) for line in dump]
    return [str(knowledge_base)]


def _guidance_items(response: Any) -> list[tuple[str | None, str]]:
    if response is None:
        return []
    if isinstance(response, str):
        return [(None, sentence) for sentence in _sentences(response)]
    if isinstance(response, (list, tuple)):
        items: list[tuple[str | None, str]] = []
        for item in response:
            if isinstance(item, dict):
                items.append((item.get("source_text"), str(item.get("output_text") or item.get("text") or "")))
            elif isinstance(item, str):
                items.append((None, item))
            else:
                items.append((getattr(item, "source_text", None), str(getattr(item, "output_text", item))))
        return [(src, out) for src, out in items if out]
    if isinstance(response, dict):
        selected = response.get("selected") or response.get("guidance") or []
        if isinstance(selected, list):
            return _guidance_items(selected)
        if response.get("output_text"):
            return [(response.get("source_text"), str(response["output_text"]))]
        return [(None, sentence) for sentence in _sentences(str(response))]
    items = getattr(response, "guidance", None)
    if items:
        return _guidance_items(items)
    return [(None, sentence) for sentence in _sentences(str(response))]


def _is_non_latin(text: str) -> bool:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False
    return sum(1 for ch in letters if ord(ch) > 127) / len(letters) >= 0.4


def _token_set(text: str) -> set[str]:
    return set(_WORD_RE.findall(_normalize_sentence(text)))


def _coverage(output: str, kb_line: str) -> float:
    output_tokens = _token_set(output)
    kb_tokens = _token_set(kb_line)
    if not output_tokens:
        return 0.0
    return len(output_tokens & kb_tokens) / len(output_tokens)


def _jaccard(left: str, right: str) -> float:
    a, b = _token_set(left), _token_set(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _ratio(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalize_sentence(left), _normalize_sentence(right)).ratio()


def _embedding_similarity(_left: str, _right: str) -> float | None:
    """Secondary semantic check. Optional; unused unless a local embedder is wired.

    Never sufficient on its own to approve a sentence with no lexical overlap.
    """
    return None


def _optional_llm_judge(_sentence: str, _kb_lines: list[str]) -> bool | None:
    """Optional LLM judge. Must not approve completely invented safety actions.

    SPEC.md Rule: Guidance failure — never invent approved guidance.
    Returning None keeps knowledge-base matching as the final authority.
    """
    return None


def validate_guidance_output(
    response: Any,
    knowledge_base: Any,
    *,
    knowledge_base_file: str | None = None,
    incident_id: str | None = None,
) -> dict[str, Any]:
    """Every guidance sentence must be an exact KB line or a close paraphrase.

    SPEC.md Rule: AI-generated safety instructions must be grounded.
    The knowledge base remains the single source of truth.
    """
    limits = load_guardrail_config()
    sim_min = float(limits["guidance_similarity_min"])
    jac_min = float(limits["guidance_jaccard_min"])
    sentences = [item for item in _guidance_items(response) if item[1]]
    kb_lines = [item for item in _kb_lines(knowledge_base) if item]
    violations: list[str] = []
    matched: list[str] = []
    scores: list[float] = []
    if not sentences:
        violations.append("empty guidance output")
    if not kb_lines:
        violations.append("knowledge base text missing")
    invented_markers = (
        "disconnect the main breaker",
        "reset the breaker",
        "repair the",
        "rewire",
        "open the panel",
        "cut the power yourself",
        "perform cpr",
        "administer",
        "disconnect the power cable",
    )
    for source_text, sentence in sentences:
        targets = [source_text] + kb_lines if source_text else kb_lines
        targets = [line for line in targets if line]
        lowered = sentence.lower()
        if any(marker in lowered for marker in invented_markers):
            best = max((_ratio(sentence, line) for line in targets), default=0.0)
            if best < 0.85:
                violations.append("Not supported by knowledge base.")
                scores.append(best)
                continue
        if source_text and _is_non_latin(sentence):
            matched.append(source_text)
            scores.append(1.0)
            continue
        best_line = source_text or ""
        best_score = _ratio(sentence, source_text) if source_text else 0.0
        for line in targets:
            if _normalize_sentence(sentence) == _normalize_sentence(line):
                best_line, best_score = line, 1.0
                break
            score = max(_ratio(sentence, line), _jaccard(sentence, line), _coverage(sentence, line))
            embedded = _embedding_similarity(sentence, line)
            if embedded is not None:
                score = max(score, float(embedded))
            if score > best_score:
                best_score = score
                best_line = line
        judge = _optional_llm_judge(sentence, kb_lines)
        if judge is False:
            best_score = min(best_score, 0.0)
        ratio_ok = best_line and (
            _ratio(sentence, best_line) >= sim_min or _normalize_sentence(sentence) == _normalize_sentence(best_line)
        )
        jaccard_ok = best_line and _jaccard(sentence, best_line) >= jac_min
        coverage_ok = best_line and _coverage(sentence, best_line) >= jac_min
        if ratio_ok or jaccard_ok or coverage_ok:
            matched.append(best_line)
            scores.append(best_score)
        else:
            violations.append("Not supported by knowledge base.")
            scores.append(best_score)
    approved = not violations
    confidence = round(sum(scores) / len(scores), 4) if scores else 0.0
    if not approved:
        emit_guardrail_event(
            EVENT_GUIDANCE_BLOCKED,
            guardrail="guidance_grounding",
            approved=False,
            incident_id=incident_id,
            rule="SPEC.md Rule: AI-generated safety instructions must be grounded",
            decision="fallback_to_knowledge_base",
            violations=violations,
            metadata={"knowledge_base_file": knowledge_base_file, "confidence": confidence},
        )
        log.warning("guidance_blocked file=%s violations=%s", knowledge_base_file, violations)
    else:
        emit_guardrail_event(
            EVENT_PASSED,
            guardrail="guidance_grounding",
            approved=True,
            incident_id=incident_id,
            rule="SPEC.md Rule: AI-generated safety instructions must be grounded",
            decision="release_guidance",
            metadata={
                "knowledge_base_file": knowledge_base_file,
                "matched": len(matched),
                "total": len(sentences),
                "confidence": confidence,
            },
        )
    payload = GuidanceValidation(
        approved=approved,
        violations=violations,
        matched_lines=matched,
        confidence=confidence,
    )
    return payload.model_dump()


def safe_guidance_fallback(knowledge_base: Any, *, limit: int = 2) -> list[str]:
    """Original knowledge-base lines. Never leave a worker without approved guidance."""
    lines = _kb_lines(knowledge_base)
    return (
        lines[: max(1, limit)] if lines else ["Always follow instructions from trained safety or emergency personnel."]
    )


def _risk_key(value: str | None) -> str:
    return (value or "").strip().lower()


def _slack_action_valid(slack_closed_action: dict[str, Any] | None) -> bool:
    if not isinstance(slack_closed_action, dict):
        return False
    action = str(slack_closed_action.get("action") or slack_closed_action.get("action_id") or "").strip().lower()
    actor = slack_closed_action.get("closed_by") or slack_closed_action.get("user") or slack_closed_action.get("actor")
    source = str(slack_closed_action.get("source") or slack_closed_action.get("closed_source") or "").lower()
    if action not in SLACK_CLOSED_ACTIONS and action != "closed":
        return False
    if not actor:
        return False
    if source and source not in {"slack", ""}:
        return False
    return True


def validate_closure_request(
    *,
    risk_level: str | None,
    source: str | None = None,
    reviewed_by_human: bool = False,
    slack_closed_action: dict[str, Any] | None = None,
    incident_id: str | None = None,
) -> dict[str, Any]:
    """Low/Medium may auto-close. High/Critical require explicit Slack Closed.

    SPEC.md Rule: SentinelLoop assists safety teams; it does not replace accountable
    humans. Human intervention for Critical incidents and closure overrides.
    """
    level = _risk_key(risk_level)
    origin = (source or "").strip().lower()
    slack_ok = _slack_action_valid(slack_closed_action)
    human_ok = bool(reviewed_by_human) and slack_ok
    human_review = level in HUMAN_REVIEW_LEVELS
    if level in AUTO_CLOSE_LEVELS:
        approved = True
        decision = "auto_close_allowed"
        violations: list[str] = []
    elif human_review or not level:
        if slack_ok or human_ok:
            approved = True
            decision = "human_slack_close_allowed"
            violations = []
        else:
            approved = False
            decision = "human_review_required"
            violations = ["High/Critical incidents require explicit human Closed action in Slack"]
    else:
        approved = False
        decision = "unknown_risk_block"
        violations = [f"unrecognized risk level {risk_level}"]
    if origin in {"telegram", "worker", "auto"} and human_review and not slack_ok:
        approved = False
        decision = "human_review_required"
        violations = ["High/Critical incidents require explicit human Closed action in Slack"]
    event = EVENT_PASSED if approved else EVENT_CLOSURE_BLOCKED
    emit_guardrail_event(
        event,
        guardrail="closure",
        approved=approved,
        incident_id=incident_id,
        rule="SPEC.md Rule: Human intervention for Critical incidents",
        decision=decision,
        violations=violations,
        metadata={"risk_level": risk_level, "source": source, "reviewed_by_human": reviewed_by_human},
    )
    return ClosureValidation(
        approved=approved,
        human_review_required=human_review and not approved,
        violations=violations,
        decision=decision,
    ).model_dump()


def validate_slack_closure(
    *,
    action: str | None,
    actor: str | None,
    incident_id: str | None,
    expected_incident_id: str | None,
    thread_ts: str | None = None,
    expected_thread_ts: str | None = None,
    channel_id: str | None = None,
    expected_channel_id: str | None = None,
    is_bot: bool = False,
) -> dict[str, Any]:
    """Only accept Closed from an authorized officer on the correct Slack thread.

    SPEC.md Rule: Manual overrides always preserve an auditable reason.
    """
    violations: list[str] = []
    action_key = (action or "").strip().lower()
    if action_key not in SLACK_CLOSED_ACTIONS and action_key != "closed":
        violations.append("only Closed action is accepted")
    if not actor or is_bot:
        violations.append("unauthorized user")
    if not incident_id or (expected_incident_id and str(incident_id) != str(expected_incident_id)):
        violations.append("incident ID mismatch")
    if expected_thread_ts and thread_ts and str(thread_ts) != str(expected_thread_ts):
        violations.append("unrelated Slack thread")
    if expected_channel_id and channel_id and str(channel_id) != str(expected_channel_id):
        violations.append("unrelated Slack channel")
    approved = not violations
    emit_guardrail_event(
        EVENT_PASSED if approved else EVENT_FAILED,
        guardrail="slack_closure",
        approved=approved,
        incident_id=str(incident_id) if incident_id else None,
        rule="SPEC.md Rule: Manual overrides always preserve an auditable reason",
        decision="slack_closed" if approved else "reject_slack_close",
        violations=violations,
        metadata={"actor": actor, "action": action},
    )
    return {"approved": approved, "violations": violations}


def detect_privacy_leaks(record: dict[str, Any] | None) -> list[str]:
    """Scan analytics payloads for phone numbers, emails, and Telegram IDs.

    SPEC.md Rule: Collect only information necessary for incident management.
    """
    blob = json_dumps_safe(record or {})
    hits: list[str] = []
    if _PHONE_RE.search(blob):
        hits.append("phone_number")
    if _EMAIL_RE.search(blob):
        hits.append("email")
    if _TELEGRAM_ID_RE.search(blob):
        hits.append("telegram_id")
    return hits


def json_dumps_safe(value: Any) -> str:
    import json

    return json.dumps(value, default=str)


def sanitize_analytics_record(record: dict[str, Any] | None, *, is_anonymous: bool | None = None) -> dict[str, Any]:
    """Strip personal identifiers from analytics when the report is anonymous.

    SPEC.md Rule: Do not unnecessarily expose worker contact data.
    """
    data = dict(record or {})
    anonymous = is_anonymous
    if anonymous is None:
        anonymous = bool(data.get("is_anonymous") or data.get("anonymous"))
    removed: list[str] = []
    if anonymous:
        for key in list(data.keys()):
            if key.lower() in PRIVACY_KEYS or "phone" in key.lower():
                data.pop(key, None)
                removed.append(key)
        data["anonymous"] = True
        data.pop("is_anonymous", None)
    leaks = detect_privacy_leaks(data)
    if anonymous or leaks:
        if leaks:
            for key in list(data.keys()):
                raw = data.get(key)
                if isinstance(raw, str) and (
                    _PHONE_RE.search(raw) or _EMAIL_RE.search(raw) or _TELEGRAM_ID_RE.search(raw)
                ):
                    data[key] = "[redacted]"
                    removed.append(key)
            for leak_key in ("phone", "phone_number", "email", "telegram_id", "telegram_chat_id", "worker_chat_id"):
                if leak_key in data:
                    data.pop(leak_key, None)
                    removed.append(leak_key)
            emit_guardrail_event(
                EVENT_PRIVACY_REDACTION,
                guardrail="privacy",
                approved=False,
                rule="SPEC.md Rule: Do not unnecessarily expose worker contact data",
                decision="block_analytics_leak",
                violations=leaks,
            )
        elif removed:
            emit_guardrail_event(
                EVENT_PRIVACY_REDACTION,
                guardrail="privacy",
                approved=True,
                rule="SPEC.md Rule: Do not unnecessarily expose worker contact data",
                decision="redact_anonymous_identifiers",
                metadata={"removed": removed},
            )
    return data


def build_safe_analytics_event(record: dict[str, Any] | None) -> dict[str, Any]:
    """Privacy-safe analytics row: region/category, never worker phone when anonymous."""
    data = dict(record or {})
    anonymous = bool(data.get("is_anonymous") or data.get("anonymous"))
    safe = {
        "anonymous": anonymous,
        "region": data.get("region") or data.get("location") or data.get("site_id"),
        "category": data.get("category") or data.get("hazard_category"),
        "risk_level": data.get("risk_level") or data.get("current_risk_level"),
        "status": data.get("status"),
        "source": data.get("source") or data.get("source_channel"),
        "incident_id": data.get("incident_id") or data.get("incident_ref"),
    }
    if not anonymous:
        safe["reporter_present"] = bool(data.get("phone") or data.get("phone_number") or data.get("reporter_id"))
    return sanitize_analytics_record(safe, is_anonymous=anonymous)


def validate_model_budget(
    *,
    current_cost: Any = None,
    requested_cost: Any = None,
    ceiling: Any = None,
    incident_id: str | None = None,
) -> dict[str, Any]:
    """Refuse spend that would exceed OPENROUTER_BUDGET_CEILING_USD.

    SPEC.md Rule: Never place real secrets in logs. Budget is operational policy.
    """
    env_ceiling = _decimal(os.environ.get("OPENROUTER_BUDGET_CEILING_USD"))
    cap = _decimal(ceiling) if ceiling is not None else env_ceiling
    current = _decimal(current_cost) or Decimal("0")
    requested = _decimal(requested_cost) or Decimal("0")
    if cap is None:
        emit_guardrail_event(
            EVENT_PASSED,
            guardrail="budget",
            approved=True,
            incident_id=incident_id,
            rule="SPEC.md Rule: Paid OpenRouter spend is governed by OPENROUTER_BUDGET_CEILING_USD",
            decision="ceiling_unset_paid_disabled",
        )
        return {"approved": True, "violations": [], "remaining": None, "warning": False}
    projected = current + requested
    remaining = cap - current
    ratio = float(current / cap) if cap > 0 else 0.0
    warning_ratio = float(load_guardrail_config()["budget_warning_ratio"])
    warning = ratio >= warning_ratio and projected <= cap
    if projected > cap:
        emit_guardrail_event(
            EVENT_MODEL_BLOCKED_BUDGET,
            guardrail="budget",
            approved=False,
            incident_id=incident_id,
            rule="SPEC.md Rule: Paid OpenRouter spend is governed by OPENROUTER_BUDGET_CEILING_USD",
            decision="block_paid_call",
            violations=["OPENROUTER_BUDGET_CEILING_USD exceeded"],
            metadata={"current": str(current), "ceiling": str(cap), "requested": str(requested)},
        )
        emit_guardrail_event(
            EVENT_BUDGET_BLOCKED,
            guardrail="budget",
            approved=False,
            incident_id=incident_id,
            rule="SPEC.md Rule: Paid OpenRouter spend is governed by OPENROUTER_BUDGET_CEILING_USD",
            decision="block_paid_call",
        )
        return {
            "approved": False,
            "violations": ["OPENROUTER_BUDGET_CEILING_USD exceeded"],
            "remaining": str(remaining),
            "warning": True,
        }
    if warning:
        emit_guardrail_event(
            EVENT_BUDGET_WARNING,
            guardrail="budget",
            approved=True,
            incident_id=incident_id,
            rule="SPEC.md Rule: Paid OpenRouter spend is governed by OPENROUTER_BUDGET_CEILING_USD",
            decision="budget_warning",
            metadata={"ratio": round(ratio, 4)},
        )
    else:
        emit_guardrail_event(
            EVENT_MODEL_ALLOWED,
            guardrail="budget",
            approved=True,
            incident_id=incident_id,
            rule="SPEC.md Rule: Paid OpenRouter spend is governed by OPENROUTER_BUDGET_CEILING_USD",
            decision="allow_model_call",
            metadata={"current": str(current), "ceiling": str(cap)},
        )
    return {"approved": True, "violations": [], "remaining": str(remaining), "warning": warning}


def assert_model_budget_within_limit(current_cost: Any, ceiling: Any | None = None) -> None:
    """Test-visible assertion: current_cost <= OPENROUTER_BUDGET_CEILING_USD."""
    cap = _decimal(ceiling) if ceiling is not None else _decimal(os.environ.get("OPENROUTER_BUDGET_CEILING_USD"))
    current = _decimal(current_cost) or Decimal("0")
    assert cap is not None, "OPENROUTER_BUDGET_CEILING_USD is not set"
    assert current <= cap, f"current_cost {current} exceeds OPENROUTER_BUDGET_CEILING_USD {cap}"


class OutputSafetyPostHook(PostHook):
    """Agent Kernel post-execution hook. Sees only the final user-facing reply."""

    async def on_run(self, session: Any, requests: list[Any], agent: Any, agent_reply: AgentReply) -> AgentReply:
        # SPEC.md Rule: Post-execution structured-output validation of user-visible text.
        text = getattr(agent_reply, "response", None) or getattr(agent_reply, "text", "") or ""
        if _API_KEY_RE.search(text):
            cleaned = _API_KEY_RE.sub("[redacted]", text)
            log.warning("output_guardrail_redacted_secret agent=%s", getattr(agent, "name", None))
            emit_guardrail_event(
                EVENT_FAILED,
                guardrail="output_post_hook",
                approved=False,
                agent=getattr(agent, "name", None),
                rule="SPEC.md Rule: Never place real secrets in logs or replies",
                decision="redact_secret",
            )
            if isinstance(agent_reply, AgentReplyText):
                update = {"response": cleaned} if hasattr(agent_reply, "response") else {"text": cleaned}
                return agent_reply.model_copy(update=update)
        emit_guardrail_event(
            EVENT_PASSED,
            guardrail="output_post_hook",
            approved=True,
            agent=getattr(agent, "name", None),
            rule="SPEC.md Rule: Post-execution validation of the user-visible reply",
            metadata={"session_id": getattr(session, "id", None)},
        )
        return agent_reply

    def name(self) -> str:
        return "sentinelloop_output_safety"
