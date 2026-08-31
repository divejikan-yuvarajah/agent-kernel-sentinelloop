"""Normalize the deployed Supabase columns onto SPEC row models."""

from database.models import Assignment, Incident, IncidentEvidence, IncidentUpdate, RiskAssessment
from database.schema_map import (
    coerce_uuid,
    normalize_assignment_row,
    normalize_evidence_row,
    normalize_incident_row,
    normalize_risk_row,
    normalize_update_row,
)


def test_live_incident_row_maps_to_spec_model():
    incident = Incident.model_validate(
        normalize_incident_row(
            {
                "incident_id": "SL-2026-000042",
                "title": "Oil leak",
                "description": "Oil on floor near press",
                "category": "Mechanical",
                "location": "Bay 4",
                "status": "OPEN",
                "risk_level": "HIGH",
                "reported_date": "2026-08-31T10:00:00+00:00",
                "reporter_id": "whatsapp:+94770000000",
                "reporter_language": "en",
                "duplicate_count": 2,
            }
        )
    )
    assert incident.incident_ref == "SL-2026-000042"
    assert incident.id == coerce_uuid("SL-2026-000042")
    assert incident.hazard_category == "Mechanical"
    assert incident.hazard_description == "Oil on floor near press"
    assert incident.current_risk_level == "HIGH"
    assert incident.source_channel == "whatsapp"


def test_spec_incident_row_is_unchanged():
    row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "incident_ref": "SL-2026-000001",
        "reporter_id": "r1",
        "source_channel": "whatsapp",
        "status": "OPEN",
        "created_at": "2026-08-31T10:00:00+00:00",
    }
    assert normalize_incident_row(row) is row


def test_related_live_rows_validate():
    evidence = IncidentEvidence.model_validate(
        normalize_evidence_row(
            {
                "evidence_id": "22222222-2222-2222-2222-222222222222",
                "incident_id": "SL-2026-000042",
                "evidence_stage": "report",
                "file_type": "image/jpeg",
                "file_url": "https://example.test/e.jpg",
                "uploaded_time": "2026-08-31T10:01:00+00:00",
            }
        )
    )
    assert evidence.stage == "report"
    assignment = Assignment.model_validate(
        normalize_assignment_row(
            {
                "assignment_id": "33333333-3333-3333-3333-333333333333",
                "incident_id": "SL-2026-000042",
                "assigned_person": "Officer Perera",
                "department": "Mechanical",
            }
        )
    )
    assert assignment.assigned_to == "Officer Perera"
    update = IncidentUpdate.model_validate(
        normalize_update_row(
            {
                "update_id": "44444444-4444-4444-4444-444444444444",
                "incident_id": "SL-2026-000042",
                "message": "Assigned",
                "status": "ASSIGNED",
                "timestamp": "2026-08-31T10:02:00+00:00",
                "updated_by": "system",
            }
        )
    )
    assert update.update_type == "timeline"
    risk = RiskAssessment.model_validate(
        normalize_risk_row(
            {
                "assessment_id": "55555555-5555-5555-5555-555555555555",
                "incident_id": "SL-2026-000042",
                "severity": 4,
                "likelihood": 3,
                "final_score": 12,
                "explanation": "Active machinery",
            }
        )
    )
    assert risk.risk_score == 12
