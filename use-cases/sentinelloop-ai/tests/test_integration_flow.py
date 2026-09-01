"""Full mocked Telegram → intake → duplicate → incident → risk → guardrails → guidance → Slack → repository flow."""

from __future__ import annotations

import time

from guardrails.output_validation import validate_guidance_output
from tests.conftest import run
from tests.test_incident_orchestrator import FakeCoord, MemoryRepo, RecordingClient, _msg, _orch
from tools.duplicate_tools import DuplicateQuery, check_for_duplicate
from tools.lifecycle import STATUS_ASSIGNED
from tools.risk_tools import calculate_risk


def test_full_mocked_pipeline_order_and_data_passing():
    orch = _orch()
    result = run(orch.process_incoming_telegram_message(_msg()))
    assert "intake_agent" in orch.pipeline_trace
    assert "duplicate_tools" in orch.pipeline_trace
    assert "incident_agent" in orch.pipeline_trace
    assert "risk_agent" in orch.pipeline_trace
    assert "guidance_agent" in orch.pipeline_trace
    assert "coordination_agent" in orch.pipeline_trace
    assert "repository" in orch.pipeline_trace
    assert orch.pipeline_trace.index("intake_agent") < orch.pipeline_trace.index("duplicate_tools")
    assert orch.pipeline_trace.index("duplicate_tools") < orch.pipeline_trace.index("incident_agent")
    assert orch.pipeline_trace.index("incident_agent") < orch.pipeline_trace.index("risk_agent")
    assert orch.pipeline_trace.index("risk_agent") < orch.pipeline_trace.index("guidance_agent")
    assert orch.pipeline_trace.index("repository") < orch.pipeline_trace.index("coordination_agent")
    assert result.is_hazard_report is True
    assert result.incident_id is not None
    assert orch._repo.create_calls
    assert orch._coord.calls
    created = orch._repo.create_calls[0]
    assert created.hazard_category == "electrical"
    assert created.location == "Electrical Room"


def test_slack_unavailable_still_saves_incident():
    coord = FakeCoord()
    coord.fail = True
    orch = _orch(coordination=coord)
    result = run(orch.process_incoming_telegram_message(_msg(provider_message_id="wamid.slack-down")))
    assert result.incident_id is not None
    assert orch._repo.create_calls
    assert result.coordination_completed is False


def test_telegram_unavailable_still_saves_incident():
    client = RecordingClient()
    client.fail = True
    orch = _orch(client=client)
    result = run(orch.process_incoming_telegram_message(_msg(provider_message_id="wamid.wa-down")))
    assert result.incident_id is not None
    assert orch._repo.create_calls
    assert result.guidance_sent is False


def test_repository_unavailable_is_not_false_success():
    repo = MemoryRepo()
    repo.fail_create = True
    orch = _orch(repository=repo)
    result = run(orch.process_incoming_telegram_message(_msg(provider_message_id="wamid.repo-down")))
    assert result.incident_id is None
    assert result.coordination_completed is False
    assert result.error


def test_model_unavailable_preserves_saved_incident_or_fallback():
    from tests.test_incident_orchestrator import Scripted

    orch = _orch(risk_fn=Scripted("risk", responses=[RuntimeError("model down")]))
    result = run(orch.process_incoming_telegram_message(_msg(provider_message_id="wamid.model-down")))
    assert result.incident_id is not None
    assert orch._repo.create_calls


def test_pipeline_functions_pass_data_without_network(sample_knowledge_base):
    risk = calculate_risk(
        severity=5, likelihood=4, active=True, people_exposed=8, category="electrical", already_injured=False
    )
    assert risk["level"] == "Critical"
    dup = check_for_duplicate(
        DuplicateQuery(translated_text="panel sparking", location="Bay 1", hazard_category="electrical"),
        repository=MemoryRepo(),
    )
    assert dup.action == "create_new"
    guidance = validate_guidance_output("Move away from the damaged equipment.", sample_knowledge_base)
    assert guidance["approved"] is True
    assert STATUS_ASSIGNED == "Assigned"


def test_performance_one_hundred_risk_duplicate_and_validations(sample_knowledge_base):
    started = time.perf_counter()
    for i in range(100):
        calculate_risk(
            severity=2,
            likelihood=2,
            active=False,
            people_exposed=i % 6,
            category="machine",
            already_injured=False,
        )
        check_for_duplicate(
            DuplicateQuery(
                translated_text="oil leak near press",
                location=f"Bay {i % 9}",
                hazard_category="machine",
            ),
            repository=MemoryRepo(),
        )
        validate_guidance_output("Move away from the damaged equipment.", sample_knowledge_base)
    elapsed = time.perf_counter() - started
    assert elapsed < 8.0, f"100 safety checks took {elapsed:.2f}s"
