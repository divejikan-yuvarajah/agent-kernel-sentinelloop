"""Smoke pipeline executes every agent stage without live credentials."""

from __future__ import annotations

import asyncio

from scripts.smoke_test import run_smoke


def test_smoke_pipeline_completes():
    payload = asyncio.run(run_smoke())
    assert payload["success"] is True
    assert payload["incident_id"]
    assert payload["execution_time_ms"] < 30_000
    for stage in (
        "intake_agent",
        "incident_agent",
        "risk_agent",
        "guidance_agent",
        "coordination_agent",
    ):
        assert stage in payload["stages_completed"]
    assert payload["slack_alert_sent"] is True
    assert payload["risk_level"]
    assert payload["error"] is None
