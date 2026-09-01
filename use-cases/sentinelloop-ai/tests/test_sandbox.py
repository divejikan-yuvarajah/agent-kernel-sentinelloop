"""Try It Live sandbox — identical pipeline, isolated from production analytics."""

from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.api import DashboardHandler
from dashboard.service import DashboardReadService
from services.demo_pipeline import MemoryRepo, build_demo_orchestrator
from services.sandbox_isolation import filter_production_incidents, incident_is_sandbox
from services.sandbox_service import (
    RATE_LIMIT_PER_HOUR,
    build_sandbox_orchestrator,
    process_sandbox_message,
    reset_sandbox_state_for_tests,
)


def _app(repo: MemoryRepo | None = None, orch=None) -> TestClient:
    repository = repo or MemoryRepo()
    handler = DashboardHandler(
        repository=repository,
        service=DashboardReadService(repository),
        orchestrator=orch,
    )
    app = FastAPI()
    app.include_router(handler.get_router())
    return TestClient(app)


def setup_function() -> None:
    reset_sandbox_state_for_tests()


def test_sandbox_api_returns_incident_risk_guidance():
    repo = MemoryRepo()
    orch = build_sandbox_orchestrator(
        repository=repo,
        raw_text="There is a damaged wire near machine 4 with workers nearby.",
        category="electrical",
        location="Machine 4",
    )
    client = _app(repo, orch)
    # Prefer a non-emergency sample so the full agent pipeline runs in demos/tests.
    SAMPLE = "There is a damaged wire near machine 4 with workers nearby."

    response = client.post(
        "/api/sandbox/message",
        json={"session_id": "demo-user-001", "text": SAMPLE, "simulate": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["incident_id"]
    assert body["is_sandbox"] is True
    assert body["input_channel"] == "sandbox"
    assert body["risk_level"]
    assert body["risk_score"] is not None
    assert body["guidance"] or body["guidance_text"]
    assert "sandbox" in (body.get("slack_alert_preview") or body.get("slack_preview") or "").lower()
    assert repo.create_calls
    assert repo.create_calls[0].source_channel == "sandbox"
    assert repo.create_calls[0].is_sandbox is True


def test_sandbox_isolation_from_production_analytics():
    repo = MemoryRepo()
    production = build_demo_orchestrator(repository=repo, raw_text="Telegram smoke", category="fire/smoke")
    sandbox = build_sandbox_orchestrator(repository=repo, raw_text="Sandbox smoke", category="fire/smoke")

    async def seed():
        from services.incident_intake_service import process_incident_input

        await process_incident_input(
            source="telegram",
            raw_text="Damaged cable near the packing line with two workers nearby.",
            metadata={"sender_id": "telegram:prod"},
            orchestrator=production,
        )
        await process_sandbox_message(
            session_id="demo-iso-001",
            text="Damaged cable near the packing line with two workers nearby.",
            orchestrator=sandbox,
            repository=repo,
        )

    asyncio.run(seed())
    all_rows = repo.list_all_incidents()
    sandbox_rows = [row for row in all_rows if incident_is_sandbox(row)]
    production_rows = filter_production_incidents(all_rows)
    assert sandbox_rows
    assert production_rows
    assert all(not incident_is_sandbox(row) for row in production_rows)
    assert all((row.source_channel or "").lower() != "sandbox" for row in production_rows)

    # Production analytics helpers must drop sandbox rows.
    assert len(filter_production_incidents(all_rows)) == len(production_rows)
    assert len(sandbox_rows) >= 1
    assert any((call.source_channel or "").lower() == "sandbox" for call in repo.create_calls)
    assert any((call.source_channel or "").lower() == "telegram" for call in repo.create_calls)


def test_sandbox_pipeline_agents_execute():
    repo = MemoryRepo()
    orch = build_sandbox_orchestrator(
        repository=repo,
        raw_text="There is a damaged wire near machine 4",
        category="electrical",
        location="Machine 4",
    )

    async def run():
        return await process_sandbox_message(
            session_id="demo-pipe-001",
            text="There is a damaged wire near machine 4",
            orchestrator=orch,
            repository=repo,
            judge_mode=True,
        )

    payload = asyncio.run(run())
    assert payload["error"] is None
    pipeline = payload["pipeline"]
    for step in ("intake_agent", "incident_agent", "risk_agent", "guidance_agent", "coordination_agent"):
        assert step in pipeline
    assert payload["judge"]["model_used"]
    assert orch.coordination.calls
    assert payload["risk_level"] in {"Critical", "CRITICAL", "High", "HIGH"}
    assert payload["risk_score"] is not None
    assert int(payload["risk_score"]) >= 12


def test_sandbox_rate_limit_blocks_21st_message():
    repo = MemoryRepo()
    client = _app(repo)
    session = "demo-rate-001"
    accepted = 0
    blocked = 0
    for index in range(RATE_LIMIT_PER_HOUR + 1):
        orch = build_sandbox_orchestrator(
            repository=repo,
            raw_text=f"Smoke coming from machine 4 sample {index}",
            category="fire/smoke",
            location="Machine 4",
        )
        handler = DashboardHandler(
            repository=repo,
            service=DashboardReadService(repo),
            orchestrator=orch,
        )
        app = FastAPI()
        app.include_router(handler.get_router())
        local = TestClient(app)
        response = local.post(
            "/api/sandbox/message",
            json={
                "session_id": session,
                "text": f"Damaged cable near packing line sample {index}",
                "simulate": True,
            },
        )
        if response.status_code == 200:
            accepted += 1
        elif response.status_code == 429:
            blocked += 1
        else:
            raise AssertionError(f"unexpected status {response.status_code}: {response.text}")
    assert accepted == RATE_LIMIT_PER_HOUR
    assert blocked == 1
