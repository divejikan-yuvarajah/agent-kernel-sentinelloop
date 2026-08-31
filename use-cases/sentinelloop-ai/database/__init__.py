"""SentinelLoop database package.

Durable Supabase persistence. Not an Agent Kernel session adapter.

The service-role key must stay server-side. Dashboard frontends must call
an API that uses this package; they must never embed SUPABASE_SERVICE_ROLE_KEY.
"""

from database.client import (
    create_supabase_client,
    evidence_bucket_name,
    get_supabase_client,
    reset_supabase_client,
)
from database.exceptions import (
    DatabaseConfigError,
    DatabaseError,
    EvidenceUploadError,
    PartialPersistenceError,
    PersistenceError,
    RecordNotFoundError,
)
from database.models import Assignment, Incident, IncidentEvidence, IncidentUpdate, RiskAssessment
from database.repository import (
    IncidentRepository,
    add_evidence,
    add_update,
    assign_incident,
    create_incident,
    get_incident,
    increment_duplicate_count,
    list_incidents,
    reset_default_repository,
    update_incident_status,
)
from database.schemas import (
    AssignmentCreate,
    EvidenceCreate,
    EvidenceFile,
    IncidentCreate,
    IncidentFilters,
    IncidentUpdateCreate,
)

__all__ = [
    "Assignment",
    "AssignmentCreate",
    "DatabaseConfigError",
    "DatabaseError",
    "EvidenceCreate",
    "EvidenceFile",
    "EvidenceUploadError",
    "Incident",
    "IncidentCreate",
    "IncidentEvidence",
    "IncidentFilters",
    "IncidentRepository",
    "IncidentUpdate",
    "IncidentUpdateCreate",
    "PartialPersistenceError",
    "PersistenceError",
    "RecordNotFoundError",
    "RiskAssessment",
    "add_evidence",
    "add_update",
    "assign_incident",
    "create_incident",
    "create_supabase_client",
    "evidence_bucket_name",
    "get_incident",
    "get_supabase_client",
    "increment_duplicate_count",
    "list_incidents",
    "reset_default_repository",
    "reset_supabase_client",
    "update_incident_status",
]
