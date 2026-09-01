"""Incident intelligence detail page contract tests.

Source-level checks keep the investigation workspace wired for explainability,
audit export, duplicate banners, evidence, and risk decision separation.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.api import DashboardHandler
from database.repository import IncidentRepository
from tests.test_database import FakeBackend, _create_payload

FRONTEND = Path(__file__).resolve().parents[1] / "dashboard" / "frontend"
INCIDENT_DIR = FRONTEND / "src" / "components" / "incident"
DETAIL_PAGE = FRONTEND / "src" / "pages" / "IncidentDetailPage.tsx"


def _app(repo: IncidentRepository) -> TestClient:
    handler = DashboardHandler(repository=repo)
    app = FastAPI()
    app.include_router(handler.get_router())
    return TestClient(app)


def test_incident_detail_components_exist():
    required = [
        "IncidentHeader.tsx",
        "RiskBadge.tsx",
        "IncidentTimeline.tsx",
        "RiskExplanation.tsx",
        "EvidenceGallery.tsx",
        "AuditExportButton.tsx",
        "AssignmentPanel.tsx",
        "RelatedIncidents.tsx",
        "GuidancePanel.tsx",
    ]
    for name in required:
        assert (INCIDENT_DIR / name).is_file(), name


def test_incident_header_and_live_status_surface_on_page():
    page = DETAIL_PAGE.read_text(encoding="utf-8")
    header = (INCIDENT_DIR / "IncidentHeader.tsx").read_text(encoding="utf-8")
    assert "IncidentHeader" in page
    assert "RiskBadge" in header
    assert "Reported" in header
    assert "SafetyStatusBadge" in header or "SafetyStatusBadge" in page
    assert "Export audit trail" in page
    assert "audit-export" in page


def test_timeline_renders_updates_and_respects_reduced_motion():
    page = DETAIL_PAGE.read_text(encoding="utf-8")
    timeline = (INCIDENT_DIR / "IncidentTimeline.tsx").read_text(encoding="utf-8")
    css = (FRONTEND / "src" / "styles" / "incident-intel.css").read_text(encoding="utf-8")
    assert "IncidentTimeline" in page
    assert "detail.timeline" in page
    assert "ii-timeline" in timeline
    assert "prefers-reduced-motion" in css
    assert "No status changes recorded" in timeline


def test_risk_explanation_separates_ai_from_deterministic_matrix():
    page = DETAIL_PAGE.read_text(encoding="utf-8")
    explain = (INCIDENT_DIR / "RiskExplanation.tsx").read_text(encoding="utf-8")
    assert "RiskExplanation" in page
    assert "How SentinelLoop Made This Decision" in explain
    assert "AI Estimation" in explain
    assert "Rule-Based Decision" in explain
    assert "Calculated by safety matrix" in explain
    assert "Why this risk level exists" in explain
    assert "risk_explanation" in page


def test_evidence_gallery_and_verification_states():
    page = DETAIL_PAGE.read_text(encoding="utf-8")
    gallery = (INCIDENT_DIR / "EvidenceGallery.tsx").read_text(encoding="utf-8")
    assert "EvidenceGallery" in page
    assert "Evidence & Verification" in gallery
    assert "Initial Hazard Evidence" in gallery
    assert "Resolution Evidence" in gallery
    assert "Pending Verification" in gallery
    assert "Verified" in gallery
    assert "No evidence uploaded yet" in gallery
    assert "Original Evidence" in page
    assert "Before / After Safety Comparison" in page
    assert "AI Image Analysis" in page
    assert "High Confidence" in page


def test_audit_export_button_calls_endpoint():
    page = DETAIL_PAGE.read_text(encoding="utf-8")
    button = (INCIDENT_DIR / "AuditExportButton.tsx").read_text(encoding="utf-8")
    client = (FRONTEND / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    assert "AuditExportButton" in page or "exportAudit" in page
    assert 'data-testid="audit-export"' in button or 'data-testid="audit-export"' in page
    assert "fetchAuditExport" in page
    assert "/audit-export" in client


def test_duplicate_banner_appears_when_count_gt_one():
    page = DETAIL_PAGE.read_text(encoding="utf-8")
    banner = (INCIDENT_DIR / "DuplicateBanner.tsx").read_text(encoding="utf-8")
    css = (FRONTEND / "src" / "styles" / "incident-intel.css").read_text(encoding="utf-8")
    assert "DuplicateBanner" in page
    assert "duplicate_count" in page
    assert "Reported by" in banner
    assert "--signal-amber" in css
    assert "ii-duplicate" in css


def test_assignment_workflow_and_related_incidents_visible():
    page = DETAIL_PAGE.read_text(encoding="utf-8")
    assign = (INCIDENT_DIR / "AssignmentPanel.tsx").read_text(encoding="utf-8")
    related = (INCIDENT_DIR / "RelatedIncidents.tsx").read_text(encoding="utf-8")
    assert "AssignmentPanel" in page
    assert "Accept" in assign
    assert "Reassign" in assign
    assert "Escalate" in assign
    assert "RelatedIncidents" in page
    assert "linked_incidents" in page
    assert "/incidents/" in related


def test_live_polling_hook_wired():
    page = DETAIL_PAGE.read_text(encoding="utf-8")
    hook = (FRONTEND / "src" / "hooks" / "useIncidentDetailPolling.ts").read_text(encoding="utf-8")
    assert "useIncidentDetailPolling" in page
    assert "12000" in hook
    assert "fetchIncident" in hook


def test_error_and_loading_states():
    page = DETAIL_PAGE.read_text(encoding="utf-8")
    assert "Incident unavailable" in page
    assert "Retry" in page
    assert "ii-skeleton" in page
    assert "/dashboard" in page


def test_detail_api_exposes_risk_explanation_for_header_and_timeline():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    incident = repo.create_incident(
        _create_payload(
            incident_ref="SL-2026-000421",
            current_risk_level="Critical",
            status="OPEN",
            hazard_category="electrical",
            hazard_description="Panel sparking near CNC",
        )
    )
    client = _app(repo)
    payload = client.get(f"/api/incidents/{incident.incident_ref}").json()
    assert payload["incident_id"] == "SL-2026-000421"
    assert "risk" in payload
    assert "timeline" in payload
    assert "evidence" in payload
    audit = client.get(f"/api/incidents/{incident.incident_ref}/audit-export")
    assert audit.status_code == 200
    body = audit.json()
    assert "incident_information" in body
    assert body["incident_information"]["incident_id"] == "SL-2026-000421"


def test_maroon_tokens_only_in_incident_intel_css():
    css = (FRONTEND / "src" / "styles" / "incident-intel.css").read_text(encoding="utf-8")
    for token in (
        "--ink",
        "--panel",
        "--panel-raised",
        "--chalk",
        "--muted",
        "--maroon",
        "--verified-teal",
        "--signal-amber",
        "--ember-orange",
        "--hazard-red",
    ):
        assert token in css
    assert "#" not in css
