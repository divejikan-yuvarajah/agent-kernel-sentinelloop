"""UI safety-state validation without a browser runner.

Dashboard JSON and design-system source are the contract the frontend renders.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.api import DashboardHandler
from dashboard.safety import build_review_queue, build_safety_panel, safety_status_for_incident
from database.repository import IncidentRepository
from tests.test_database import FakeBackend, _create_payload

FRONTEND = Path(__file__).resolve().parents[1] / "dashboard" / "frontend"
ROOT = Path(__file__).resolve().parents[1]


def _app(repo: IncidentRepository) -> TestClient:
    handler = DashboardHandler(repository=repo)
    app = FastAPI()
    app.include_router(handler.get_router())
    return TestClient(app)


def test_critical_incident_safety_badge_is_human_review_required():
    status = safety_status_for_incident(risk_level="Critical", status="OPEN")
    assert status == "Human Review Required"
    badge = (FRONTEND / "design-system" / "components" / "SafetyStatusBadge.tsx").read_text(encoding="utf-8")
    assert "Safety Status" in badge
    detail = (FRONTEND / "src" / "pages" / "IncidentDetailPage.tsx").read_text(encoding="utf-8")
    assert "SafetyStatusBadge" in detail


def test_guardrail_panel_shows_guidance_risk_and_privacy_state():
    panel = build_safety_panel(
        incident_id="SL-2026-000040",
        risk_level="Critical",
        status="OPEN",
        assigned_officer="N. Fernando",
        guidance={
            "knowledge_base_file": "electrical_safety.md",
            "matched_line_count": 3,
            "guidance_count": 3,
            "hallucination_check": "Passed",
            "generated_guidance": "Move away from the damaged equipment.",
        },
    )
    assert panel.safety_status == "Human Review Required"
    assert panel.human_review == "Required"
    assert panel.guidance_verification.hallucination_check == "Passed"
    assert panel.guidance_verification.knowledge_base_file == "electrical_safety.md"
    assert panel.auto_close_disabled is True
    page = (FRONTEND / "src" / "pages" / "IncidentDetailPage.tsx").read_text(encoding="utf-8")
    assert "AI Decision Safety Panel" in page
    assert "Hallucination Check" in page
    assert "Human Review" in page
    safety_center = (FRONTEND / "src" / "pages" / "SafetyCenterPage.tsx").read_text(encoding="utf-8")
    assert "Privacy" in safety_center or "privacy" in safety_center.lower()


def test_review_queue_lists_high_and_critical_not_low():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    repo.create_incident(
        _create_payload(
            incident_ref="SL-2026-000041",
            current_risk_level="Critical",
            status="OPEN",
            hazard_category="electrical",
        )
    )
    repo.create_incident(
        _create_payload(
            incident_ref="SL-2026-000042",
            current_risk_level="High",
            status="IN_PROGRESS",
            hazard_category="chemical",
        )
    )
    repo.create_incident(
        _create_payload(
            incident_ref="SL-2026-000043",
            current_risk_level="Low",
            status="OPEN",
            hazard_category="other",
        )
    )
    incidents = repo.list_incidents()
    queue = build_review_queue(incidents, {})
    ids = {item.incident_id for item in queue.items}
    assert "SL-2026-000041" in ids
    assert "SL-2026-000042" in ids
    assert "SL-2026-000043" not in ids
    page = (FRONTEND / "src" / "pages" / "ReviewQueuePage.tsx").read_text(encoding="utf-8")
    assert "High and Critical" in page or "Review Required" in page


def test_audit_export_contains_decisions_timestamps_and_validation():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    incident = repo.create_incident(
        _create_payload(
            incident_ref="SL-2026-000044",
            current_risk_level="Critical",
            status="RESOLVED",
            hazard_category="electrical",
            location="Bay 1",
        )
    )
    client = _app(repo)
    response = client.get(f"/api/incidents/{incident.incident_ref}/audit-export")
    assert response.status_code == 200
    body = response.json()
    dumped = str(body)
    assert "incident_information" in body
    assert "ai_decision" in body or "risk_analysis" in body
    assert "timestamp" in dumped.lower() or "created" in dumped.lower()
    assert body.get("risk_analysis") is not None or body.get("ai_decision") is not None
    detail = client.get(f"/api/incidents/{incident.incident_ref}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["safety_status"] == "Human Review Required"
    page = (FRONTEND / "src" / "pages" / "IncidentDetailPage.tsx").read_text(encoding="utf-8")
    assert "Export audit trail" in page
    assert "audit-export" in page


def test_incident_detail_api_exposes_safety_panel_for_critical():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    repo.create_incident(
        _create_payload(
            incident_ref="SL-2026-000045",
            current_risk_level="Critical",
            status="OPEN",
            hazard_category="fire/smoke",
        )
    )
    client = _app(repo)
    payload = client.get("/api/incidents/SL-2026-000045").json()
    assert payload["safety_status"] == "Human Review Required"
    assert payload["safety"]["auto_close_disabled"] is True
    assert "guidance_verification" in payload["safety"]


def test_live_feed_component_humanizes_json_envelopes():
    source = (FRONTEND / "design-system" / "components" / "ActivityFeed.tsx").read_text(encoding="utf-8")
    assert "function humanize" in source
    assert "JSON.parse" in source
    assert "ds-feed__summary" in source
    css = (FRONTEND / "design-system" / "layout.css").read_text(encoding="utf-8")
    assert "overflow-wrap: anywhere" in css


def test_horizon_demo_dataset_covers_command_center():
    demo = (FRONTEND / "src" / "data" / "demoData.ts").read_text(encoding="utf-8")
    assert "Horizon Engineering Workshop" in demo
    assert "INC-2026-00421" in demo
    assert "මැෂින් panel එකෙන් spark එනවා" in demo
    assert "Lorem ipsum" not in demo
    assert "Test User" not in demo
    settings = (FRONTEND / "src" / "pages" / "SettingsPage.tsx").read_text(encoding="utf-8")
    assert "Demo Mode" in settings
    client = (FRONTEND / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    assert "isDemoMode" in client
    assert "demoAdapter" in client
    app = (FRONTEND / "src" / "App.tsx").read_text(encoding="utf-8")
    for path in (
        "/duplicates",
        "/follow-up",
        "/coordination",
        "/knowledge",
        "/reports",
        "/people",
        "/notifications",
        "/telegram",
    ):
        assert path in app
    dashboard = (FRONTEND / "src" / "pages" / "DashboardPage.tsx").read_text(encoding="utf-8")
    assert "Total incidents" in dashboard
    assert "AI detection accuracy" in dashboard
    detail = (FRONTEND / "src" / "pages" / "IncidentDetailPage.tsx").read_text(encoding="utf-8")
    assert "Worker report" in detail
    assert "AI extraction" in detail
    assert "Future Risk Warning" in detail
    dashboard = (FRONTEND / "src" / "pages" / "DashboardPage.tsx").read_text(encoding="utf-8")
    assert "Predicted Risk Zones" in dashboard
    assert "ds-predict-panel" in dashboard
    css = (FRONTEND / "src" / "styles" / "command-center.css").read_text(encoding="utf-8")
    assert "--signal-amber" in css
    assert "ds-predict__card" in css
    zones = (FRONTEND / "design-system" / "components" / "PredictedRiskZones.tsx").read_text(encoding="utf-8")
    assert "Schedule Inspection" in zones
    assert 'data-testid="schedule-inspection"' in zones
    app = (FRONTEND / "src" / "App.tsx").read_text(encoding="utf-8")
    assert "/forecast/:predictionId" in app
    analytics = (FRONTEND / "src" / "pages" / "AnalyticsPage.tsx").read_text(encoding="utf-8")
    assert "Predicted Risk Zones" in analytics
    assert "Safety Prediction Heatmap" in analytics
    coordination = (FRONTEND / "src" / "pages" / "CoordinationPage.tsx").read_text(encoding="utf-8")
    assert "inspection_request" in coordination


def test_vision_intelligence_surfaces_on_dashboard_incident_analytics_and_audit():
    dashboard = (FRONTEND / "src" / "pages" / "DashboardPage.tsx").read_text(encoding="utf-8")
    assert "AI Vision Insights" in dashboard
    assert "Images analyzed" in dashboard
    assert "High confidence detections" in dashboard
    detail = (FRONTEND / "src" / "pages" / "IncidentDetailPage.tsx").read_text(encoding="utf-8")
    assert "AI Image Analysis" in detail
    assert "High Confidence" in detail
    assert "Before / After Safety Comparison" in detail
    assert "Original Evidence" in detail
    analytics = (FRONTEND / "src" / "pages" / "AnalyticsPage.tsx").read_text(encoding="utf-8")
    assert "Hazard Detection By Image" in analytics
    assert "Confidence Distribution" in analytics
    assert "Free Vision Models" in analytics
    audit = (FRONTEND / "src" / "components" / "AuditTrailView.tsx").read_text(encoding="utf-8")
    assert "AI Vision Suggestion" in audit
    layout = (FRONTEND / "design-system" / "layout.css").read_text(encoding="utf-8")
    assert "ds-confidence--high" in layout
    assert "ds-confidence--medium" in layout
    assert "ds-confidence--low" in layout


def test_emergency_command_center_surfaces_on_dashboard_and_audit():
    dashboard = (FRONTEND / "src" / "pages" / "DashboardPage.tsx").read_text(encoding="utf-8")
    assert "Emergency Alerts Today" in dashboard
    assert "Average Response Time" in dashboard
    assert "Active Critical Incidents" in dashboard
    command = (FRONTEND / "src" / "pages" / "EmergencyPage.tsx").read_text(encoding="utf-8")
    assert "Emergency Command Center" in command
    assert "Active Emergency" in command
    assert "Emergency Response History" in command
    assert "Detection Time" in command
    history = (FRONTEND / "src" / "pages" / "EmergencyHistoryPage.tsx").read_text(encoding="utf-8")
    assert "Emergency Response History" in history
    sidebar = (FRONTEND / "design-system" / "components" / "Sidebar.tsx").read_text(encoding="utf-8")
    assert "Emergency Command Center" in sidebar
    audit = (FRONTEND / "src" / "components" / "AuditTrailView.tsx").read_text(encoding="utf-8")
    assert "Emergency Bypass" in audit
    assert "AI triage" in audit
    tokens = (FRONTEND / "design-system" / "tokens.css").read_text(encoding="utf-8")
    assert "--signal-red" in tokens
    layout = (FRONTEND / "design-system" / "layout.css").read_text(encoding="utf-8")
    assert "ds-emergency-card" in layout
    assert "ds-shell--collapsed" in layout
    assert "overscroll-behavior: contain" in layout


def test_shift_handover_surfaces_on_dashboard_and_history():
    dashboard = (FRONTEND / "src" / "pages" / "DashboardPage.tsx").read_text(encoding="utf-8")
    assert "HandoverPanel" in dashboard
    panel = (FRONTEND / "src" / "components" / "HandoverPanel.tsx").read_text(encoding="utf-8")
    assert "Safety Shift Handover Panel" in panel
    assert "Generate Shift Handover" in panel
    assert "Top Safety Concerns" in panel
    history = (FRONTEND / "src" / "pages" / "HandoverHistoryPage.tsx").read_text(encoding="utf-8")
    assert "Shift Handover History" in history
    assert "Compare Shifts" in history
    assert "How this handover was generated" in history
    assert "Export Handover Report" in history
    detail = (FRONTEND / "src" / "pages" / "IncidentDetailPage.tsx").read_text(encoding="utf-8")
    assert "Included in Handover" in detail
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Phase 2:" in readme
    assert "Automatic shift-end scheduling using Agent Kernel scheduler." in readme
