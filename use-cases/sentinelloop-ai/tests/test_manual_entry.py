"""Manual dashboard entry must match Telegram risk classification for equivalent facts."""

from __future__ import annotations

import asyncio

from services.demo_pipeline import build_demo_orchestrator
from services.incident_intake_service import (
    compose_manual_report_text,
    process_incident_input,
    validate_manual_incident,
)
from tools.risk_tools import calculate_risk, normalize_category

# Same narrative used by smoke_test / Telegram-style fixture scenarios.
SAMPLE = "There is smoke coming from machine 4. Three workers are nearby."
CATEGORY = "Fire/Smoke"
LOCATION = "Machine 4"
PEOPLE = 3


def test_validate_manual_requires_min_description_length():
    error = validate_manual_incident(
        description="Too short",
        category=CATEGORY,
        location=LOCATION,
        people_exposed=PEOPLE,
        is_active=True,
        injury_reported=False,
    )
    assert error == "Description must be at least 10 characters"


def test_manual_and_telegram_paths_share_calculate_risk_matrix():
    """Prove risk is not chosen on the form — both channels use calculate_risk()."""
    category = normalize_category(CATEGORY)
    shared = calculate_risk(
        severity=5,
        likelihood=4,
        active=True,
        people_exposed=PEOPLE,
        category=category,
        already_injured=False,
    )
    assert shared["level"] == "Critical"
    assert shared["score"] == 20
    assert "explanation" in shared


def test_manual_entry_matches_telegram_risk_for_same_scenario():
    raw_text = compose_manual_report_text(
        SAMPLE,
        category=CATEGORY,
        location=LOCATION,
        people_exposed=PEOPLE,
        is_active=True,
        injury_reported=False,
    )

    async def run(source: str):
        orch = build_demo_orchestrator(
            raw_text=raw_text if source == "manual" else SAMPLE,
            category="fire/smoke",
            location=LOCATION,
            people_exposed=PEOPLE,
            is_active=True,
            already_injured=False,
        )
        result = await process_incident_input(
            source=source,
            raw_text=raw_text if source == "manual" else SAMPLE,
            metadata={
                "created_by": "parity_officer" if source == "manual" else None,
                "sender_id": "telegram:parity" if source == "telegram" else None,
                "category": CATEGORY,
                "location": LOCATION,
                "people_exposed": PEOPLE,
                "is_active": True,
                "injury_reported": False,
            },
            orchestrator=orch,
        )
        return result, orch

    telegram_result, telegram_orch = asyncio.run(run("telegram"))
    manual_result, manual_orch = asyncio.run(run("manual"))

    assert telegram_result.error is None, telegram_result.error
    assert manual_result.error is None, manual_result.error
    assert telegram_result.risk_level == manual_result.risk_level
    assert telegram_result.risk_score == manual_result.risk_score
    assert telegram_result.risk_completed is True
    assert manual_result.risk_completed is True
    assert "risk_agent" in (manual_result.pipeline_trace or [])
    assert "guidance_agent" in (manual_result.pipeline_trace or [])
    assert "coordination_agent" in (manual_result.pipeline_trace or [])
    assert manual_orch._repo.create_calls[0].source_channel == "manual"
    assert telegram_orch._repo.create_calls[0].source_channel == "telegram"
    assert telegram_result.risk_level == manual_result.risk_level == "Critical"
    assert telegram_result.risk_score == manual_result.risk_score == 20
