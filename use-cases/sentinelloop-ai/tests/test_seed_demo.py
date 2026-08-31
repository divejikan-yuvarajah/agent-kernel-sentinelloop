"""Offline tests for the Horizon Engineering Workshop demo seeder."""

from __future__ import annotations

from dashboard.safety import guidance_from_updates
from dashboard.service import DashboardReadService, mask_reporter
from database.client import reset_supabase_client
from database.repository import IncidentRepository
from scripts.seed_demo_data import (
    DUP_GROUP,
    ORG_NAME,
    SITE_ID,
    incident_catalog,
    load_local_env,
    main,
    seed_demo,
)
from tests.test_database import FakeBackend
from tools.qr_tags import extract_qr_origin


def _repo() -> tuple[IncidentRepository, FakeBackend]:
    backend = FakeBackend()
    return IncidentRepository(backend, storage_bucket="evidence"), backend


def test_seed_runs_and_creates_required_horizon_environment():
    repo, backend = _repo()
    summary = seed_demo(repo)
    assert summary.organization == ORG_NAME
    assert 8 <= summary.incidents <= 10
    assert summary.incidents == 9
    assert summary.workers == 4
    assert summary.locations == 6
    assert summary.recurring == 1
    assert summary.duplicate_reports == 3
    assert summary.closed_with_evidence == 1
    assert summary.qr_reports >= 1
    assert summary.critical >= 1
    assert len(backend.tables["incidents"]) == 9
    site_ids = {row.get("site_id") for row in backend.tables["incidents"]}
    assert site_ids == {SITE_ID}


def test_second_execution_creates_no_duplicates():
    repo, backend = _repo()
    first = seed_demo(repo)
    refs = [row["incident_ref"] for row in backend.tables["incidents"]]
    update_count = len(backend.tables["incident_updates"])
    evidence_count = len(backend.tables["incident_evidence"])
    assignment_count = len(backend.tables["assignments"])
    risk_count = len(backend.tables["risk_assessments"])
    second = seed_demo(repo)
    assert second.incidents == first.incidents == 9
    assert second.created == 0
    assert second.reused == 9
    assert [row["incident_ref"] for row in backend.tables["incidents"]] == refs
    assert len(backend.tables["incidents"]) == 9
    assert len(backend.tables["incident_updates"]) == update_count
    assert len(backend.tables["incident_evidence"]) == evidence_count
    assert len(backend.tables["assignments"]) == assignment_count
    assert len(backend.tables["risk_assessments"]) == risk_count


def test_required_scenarios_exist():
    repo, _backend = _repo()
    seed_demo(repo)
    by_ref = {spec.ref: repo.get_incident_by_ref(spec.ref) for spec in incident_catalog()}
    awaiting = by_ref["DEMO-HORIZON-003"]
    closed = by_ref["DEMO-HORIZON-006"]
    recurring = by_ref["DEMO-HORIZON-004"]
    qr = by_ref["DEMO-HORIZON-007"]
    anonymous = by_ref["DEMO-HORIZON-008"]
    validating = by_ref["DEMO-HORIZON-009"]
    assert awaiting is not None and awaiting.status == "AWAITING_VERIFICATION"
    assert closed is not None and closed.status == "CLOSED"
    assert closed.closed_at is not None
    assert closed.resolved_at is not None
    assert repo.list_evidence_for_incident(closed.id)
    stages = {row.stage for row in repo.list_evidence_for_incident(closed.id)}
    assert "report" in stages
    assert "verification" in stages
    assert recurring is not None
    assert recurring.duplicate_count == 3
    assert recurring.status == "IN_PROGRESS"
    assert recurring.location == "CNC Area"
    assert recurring.hazard_category == "electrical"
    assert qr is not None
    origin = extract_qr_origin(qr.original_message_text)
    assert origin["location_verified"] is True
    assert origin["qr_equipment"] == "Welder-07"
    assert anonymous is not None
    assert anonymous.is_anonymous is True
    assert "+" not in (anonymous.reporter_id or "")
    assert mask_reporter(anonymous.reporter_id, is_anonymous=True) == "anonymous"
    assert validating is not None and validating.status == "ASSESSING"


def test_duplicate_group_and_escalation_history():
    repo, _backend = _repo()
    seed_demo(repo)
    incident = repo.get_incident_by_ref("DEMO-HORIZON-004")
    assert incident is not None
    updates = repo.list_updates_for_incident(incident.id)
    types = {row.update_type for row in updates}
    assert "duplicate_report_linked" in types
    assert "duplicate_threshold_reached" in types
    linked = [row for row in updates if row.update_type == "duplicate_report_linked"]
    assert len(linked) == 3
    groups = {((row.metadata or {}).get("duplicate_group_id")) for row in linked}
    assert groups == {DUP_GROUP}
    escalated = next(row for row in updates if row.update_type == "duplicate_threshold_reached")
    assert "multiple workers" in (escalated.message or "").lower()


def test_multilingual_sinhala_tamil_english_examples():
    repo, _backend = _repo()
    seed_demo(repo)
    sinhala = repo.get_incident_by_ref("DEMO-HORIZON-001")
    tamil = repo.get_incident_by_ref("DEMO-HORIZON-003")
    english = repo.get_incident_by_ref("DEMO-HORIZON-002")
    ppe = repo.get_incident_by_ref("DEMO-HORIZON-005")
    assert sinhala is not None
    assert sinhala.detected_language == "si"
    assert "spark" in (sinhala.original_message_text or "") or "මැෂින්" in (sinhala.original_message_text or "")
    assert tamil is not None and tamil.detected_language == "ta"
    assert "எண்ணெய்" in (tamil.original_message_text or "")
    assert english is not None and english.detected_language == "en"
    assert "smoke" in (english.original_message_text or "").lower()
    assert ppe is not None and ppe.original_message_text == "Helmet illa"
    languages = {spec.language for spec in incident_catalog() if repo.get_incident_by_ref(spec.ref)}
    assert {"si", "ta", "en"} <= languages


def test_ai_decision_trail_risk_guidance_and_slack():
    repo, _backend = _repo()
    seed_demo(repo)
    levels = set()
    for spec in incident_catalog():
        incident = repo.get_incident_by_ref(spec.ref)
        assert incident is not None
        assessments = repo.list_risk_assessments_for_incident(incident.id)
        assert assessments
        risk = assessments[0]
        assert risk.severity == spec.severity
        assert risk.likelihood == spec.likelihood
        assert risk.risk_score == spec.severity * spec.likelihood
        assert risk.severity_reason
        assert "severity" in (risk.severity_reason or "").lower()
        levels.add((incident.current_risk_level or "").upper())
        updates = repo.list_updates_for_incident(incident.id)
        types = {row.update_type for row in updates}
        assert "incident_created" in types
        assert "risk_assessed" in types
        guidance = guidance_from_updates(updates)
        if spec.guidance_line:
            assert guidance.get("knowledge_base_file") or guidance.get("hallucination_check")
        if spec.display_status not in {"New", "Validating"}:
            assert repo.get_assignment_for_incident(incident.id) is not None
            assert "slack_coordination_completed" in types
    assert {"LOW", "MEDIUM", "HIGH", "CRITICAL"} <= levels


def test_guardrail_blocked_and_approved_guidance_examples():
    repo, _backend = _repo()
    seed_demo(repo)
    approved = repo.get_incident_by_ref("DEMO-HORIZON-001")
    blocked = repo.get_incident_by_ref("DEMO-HORIZON-009")
    assert approved is not None and blocked is not None
    approved_meta = guidance_from_updates(repo.list_updates_for_incident(approved.id))
    assert (approved_meta.get("validation_status") or "").lower() == "approved"
    blocked_updates = repo.list_updates_for_incident(blocked.id)
    blocked_row = next(row for row in blocked_updates if row.update_type == "guidance_fallback")
    meta = blocked_row.metadata or {}
    assert meta.get("validation_status") == "blocked"
    assert (
        "invented" in (meta.get("ai_attempted") or "").lower()
        or "electrical" in (meta.get("ai_attempted") or "").lower()
    )


def test_whatsapp_reopen_and_qr_workshop_tag():
    repo, _backend = _repo()
    seed_demo(repo)
    recurring = repo.get_incident_by_ref("DEMO-HORIZON-004")
    assert recurring is not None
    origin = extract_qr_origin(recurring.original_message_text)
    assert origin["qr_location"] == "Workshop Floor A"
    assert origin["qr_equipment"] == "CNC-04"
    updates = repo.list_updates_for_incident(recurring.id)
    assert any(row.update_type == "incident_reopened" for row in updates)
    assert any((row.metadata or {}).get("whatsapp_reply") == "No, still exists" for row in updates)
    inbound = [row for row in updates if row.update_type == "whatsapp_inbound"]
    assert inbound


def test_dashboard_cards_and_review_queue_are_populated():
    repo, _backend = _repo()
    seed_demo(repo)
    service = DashboardReadService(repo)
    summary = service.analytics_summary()
    assert summary.total_incidents == 9
    assert summary.critical_incidents >= 1
    assert summary.qr_tagged_incidents >= 1
    assert summary.most_repeated_hazards
    queue = service.review_queue()
    assert queue.total >= 1
    closed = repo.get_incident_by_ref("DEMO-HORIZON-006")
    assert closed is not None
    detail = service.get_incident(closed.incident_ref)
    assert detail is not None
    assert detail.evidence


def test_reset_removes_only_demo_rows_then_reseeds():
    repo, backend = _repo()
    seed_demo(repo)
    seed_demo(repo, reset=True)
    assert len(backend.tables["incidents"]) == 9
    assert all(str(row["incident_ref"]).startswith("DEMO-HORIZON-") for row in backend.tables["incidents"])


def test_cli_summary_and_missing_credentials(monkeypatch, capsys):
    repo, _backend = _repo()
    seed_demo(repo)
    code = main(["--summary"], repository=repo)
    captured = capsys.readouterr()
    assert code == 0
    assert "Horizon Engineering Demo Seeder" in captured.out
    assert "Horizon Engineering Workshop" in captured.out
    monkeypatch.setattr("scripts.seed_demo_data.load_local_env", lambda path=None: None)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    reset_supabase_client()
    missing = main([])
    err = capsys.readouterr()
    assert missing == 2
    assert "SUPABASE_URL" in err.err or "Cannot seed" in err.err


def test_load_local_env_does_not_override_existing(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("SUPABASE_URL=http://example.invalid\n", encoding="utf-8")
    monkeypatch.setenv("SUPABASE_URL", "http://already-set")
    load_local_env(env_file)
    from os import environ

    assert environ["SUPABASE_URL"] == "http://already-set"


def test_catalog_covers_risk_statuses_and_languages():
    specs = incident_catalog()
    assert 8 <= len(specs) <= 10
    statuses = {spec.display_status for spec in specs}
    assert "Awaiting Verification" in statuses
    assert "Closed" in statuses
    assert any(spec.duplicate_count == 3 for spec in specs)
    assert any(spec.qr for spec in specs)
    assert any(spec.anonymous for spec in specs)
    assert any(spec.language == "si" for spec in specs)
    assert any(spec.language == "ta" for spec in specs)
    assert any(spec.blocked_guidance for spec in specs)
