"""Seed a realistic Horizon Engineering Workshop demo into the existing tables.

Uses only the five SentinelLoop tables (incidents, incident_evidence,
risk_assessments, assignments, incident_updates). Organization, workers, and
locations are encoded on those rows — no extra schema.

Usage (from use-cases/sentinelloop-ai):

    uv run python scripts/seed_demo_data.py
    uv run python scripts/seed_demo_data.py --reset
    uv run python scripts/seed_demo_data.py --verbose
    uv run python scripts/seed_demo_data.py --summary
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.client import DatabaseConfigError  # noqa: E402
from database.exceptions import EvidenceUploadError, PersistenceError, RecordNotFoundError  # noqa: E402
from database.repository import IncidentRepository  # noqa: E402
from database.schemas import (  # noqa: E402
    AssignmentCreate,
    EvidenceCreate,
    EvidenceFile,
    IncidentCreate,
    IncidentUpdateCreate,
)
from tools.lifecycle import to_repository_status  # noqa: E402
from tools.qr_tags import format_loc_prefix  # noqa: E402
from tools.risk_tools import calculate_risk  # noqa: E402

ORG_NAME = "Horizon Engineering Workshop"
SITE_ID = "horizon-engineering-workshop"
INDUSTRY = "Industrial Engineering / Manufacturing"
EMPLOYEE_COUNT = 120
DEMO_REF_PREFIX = "DEMO-HORIZON-"
DUP_GROUP = "DUP-ELECTRICAL-CNC-001"

# 1x1 PNG so evidence uploads stay valid without external files.
DEMO_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)

WORKERS = (
    {
        "id": "demo_worker_001",
        "name": "Nimal Perera",
        "language": "si",
        "language_name": "Sinhala",
        "reporter_id": "telegram:demo_worker_001",
        "anonymous": False,
    },
    {
        "id": "demo_worker_002",
        "name": "Kavitha Rajan",
        "language": "ta",
        "language_name": "Tamil",
        "reporter_id": "telegram:demo_worker_002",
        "anonymous": False,
    },
    {
        "id": "demo_worker_003",
        "name": "James Cole",
        "language": "en",
        "language_name": "English",
        "reporter_id": "telegram:demo_worker_003",
        "anonymous": False,
    },
    {
        "id": "demo_worker_004",
        "name": "Anonymous reporter",
        "language": "en",
        "language_name": "English",
        "reporter_id": "anonymous:demo_worker_004",
        "anonymous": True,
    },
)

LOCATIONS = (
    {"id": "demo_location_main_workshop", "name": "Main Workshop Floor"},
    {"id": "demo_location_cnc_area", "name": "CNC Area"},
    {"id": "demo_location_chemical_storage", "name": "Chemical Storage Room"},
    {"id": "demo_location_welding", "name": "Welding Section"},
    {"id": "demo_location_loading_bay", "name": "Loading Bay"},
    {"id": "demo_location_electrical_room", "name": "Electrical Room"},
)

TEAMS = {
    "electrical": "Electrical Maintenance",
    "fire/smoke": "Emergency Response Team",
    "chemical": "Lab Safety Team",
    "missing PPE": "Safety Supervisor",
    "slip/trip": "Facilities",
    "unsafe behaviour": "Safety Supervisor",
    "structural": "Facilities",
}

CHANNEL_ENV = {
    "Electrical Maintenance": "SLACK_CHANNEL_ELECTRICAL_MAINTENANCE",
    "Emergency Response Team": "SLACK_CHANNEL_EMERGENCY_RESPONSE",
    "Lab Safety Team": "SLACK_CHANNEL_LAB_SAFETY",
    "Safety Supervisor": "SLACK_CHANNEL_SAFETY_SUPERVISOR",
    "Facilities": "SLACK_CHANNEL_FACILITIES",
}


@dataclass
class ReportSpec:
    report_id: str
    worker_id: str
    raw_text: str
    translated_text: str
    hours_ago: float


@dataclass
class TimelineEventSpec:
    demo_key: str
    update_type: str
    message: str
    previous_status: str | None = None
    new_status: str | None = None
    actor_type: str = "agent"
    actor_reference: str = "intake_agent"
    metadata: dict[str, Any] = field(default_factory=dict)
    minutes_after: int = 0


@dataclass
class IncidentSpec:
    demo_id: str
    ref: str
    worker_id: str
    category: str
    location: str
    display_status: str
    severity: int
    likelihood: int
    active: bool
    people_exposed: int
    already_injured: bool
    raw_text: str
    translated_text: str
    language: str
    equipment: str | None = None
    qr: bool = False
    anonymous: bool = False
    duplicate_count: int = 0
    duplicate_group: str | None = None
    reports: tuple[ReportSpec, ...] = ()
    hours_ago: float = 6
    officer: str | None = None
    guidance_file: str | None = None
    guidance_line: str | None = None
    blocked_guidance: str | None = None
    evidence: tuple[tuple[str, str, str], ...] = ()
    slack_actions: tuple[str, ...] = ()
    telegram: tuple[tuple[str, str], ...] = ()


def _utc(hours_ago: float = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours_ago)


def _iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()


def _demo_uuid(key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"sentinelloop-demo:{key}"))


def _worker(worker_id: str) -> dict[str, Any]:
    for row in WORKERS:
        if row["id"] == worker_id:
            return row
    raise KeyError(worker_id)


def _channel_for(team: str) -> str:
    env_name = CHANNEL_ENV.get(team)
    if env_name:
        value = (os.environ.get(env_name) or "").strip()
        if value:
            return value
    slug = team.split()[0].upper()[:8]
    return f"C-DEMO-{slug}"


def load_local_env(path: Path | None = None) -> None:
    env_path = path or (ROOT / ".env")
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def incident_catalog() -> tuple[IncidentSpec, ...]:
    electrical_line = "Keep away from exposed wires, sparks, smoke, or damaged electrical equipment."
    chemical_line = "Move away from a chemical spill, leak, strong smell, or visible vapour."
    fire_line = "Move away from flames, heavy smoke, or increasing heat."
    general_line = "Keep a safe distance from the hazard."
    welding_qr = format_loc_prefix("Welding Section", "Welder-07")
    workshop_qr = format_loc_prefix("Workshop Floor A", "CNC-04")
    return (
        IncidentSpec(
            demo_id="demo_horizon_incident_001",
            ref="DEMO-HORIZON-001",
            worker_id="demo_worker_001",
            category="electrical",
            location="Electrical Room",
            display_status="Assigned",
            severity=5,
            likelihood=5,
            active=True,
            people_exposed=8,
            already_injured=False,
            raw_text="මැෂින් panel එකෙන් spark එනවා",
            translated_text="The machine panel is producing sparks",
            language="si",
            equipment="Panel B17",
            hours_ago=4,
            officer="R. Silva",
            guidance_file="electrical_safety.md",
            guidance_line=electrical_line,
            slack_actions=("notified",),
            telegram=(
                ("inbound", "මැෂින් panel එකෙන් spark එනවා"),
                ("inbound", "කේබල් එක කැඩිලා තියෙනවා"),
                ("outbound", "Keep away from exposed wires, sparks, smoke, or damaged electrical equipment."),
            ),
        ),
        IncidentSpec(
            demo_id="demo_horizon_incident_002",
            ref="DEMO-HORIZON-002",
            worker_id="demo_worker_003",
            category="fire/smoke",
            location="Welding Section",
            display_status="Accepted",
            severity=5,
            likelihood=4,
            active=True,
            people_exposed=6,
            already_injured=False,
            raw_text="Worker reported smoke near welding station",
            translated_text="Worker reported smoke near welding station",
            language="en",
            equipment="Bay welder bank",
            hours_ago=3,
            officer="A. Fernando",
            guidance_file="fire_safety.md",
            guidance_line=fire_line,
            slack_actions=("notified", "accepted", "escalated"),
            telegram=(("inbound", "Worker reported smoke near welding station"), ("outbound", fire_line)),
        ),
        IncidentSpec(
            demo_id="demo_horizon_incident_003",
            ref="DEMO-HORIZON-003",
            worker_id="demo_worker_002",
            category="chemical",
            location="Chemical Storage Room",
            display_status="Awaiting Verification",
            severity=4,
            likelihood=3,
            active=False,
            people_exposed=3,
            already_injured=False,
            raw_text="இயந்திரத்தில் எண்ணெய் கசிவு உள்ளது",
            translated_text="There is an oil leak from the machine",
            language="ta",
            equipment="Storage Cabinet A",
            hours_ago=8,
            officer="N. Jayasuriya",
            guidance_file="chemical_safety.md",
            guidance_line=chemical_line,
            evidence=(
                (
                    "remediation",
                    "spill_cleaned.png",
                    "Officer: chemical spill cleaned, awaiting worker confirmation",
                ),
            ),
            slack_actions=("notified", "accepted"),
            telegram=(
                ("inbound", "இயந்திரத்தில் எண்ணெய் கசிவு உள்ளது"),
                ("outbound", chemical_line),
                ("inbound", "Not sure"),
                ("system", "Worker confirmation pending"),
            ),
        ),
        IncidentSpec(
            demo_id="demo_horizon_incident_004",
            ref="DEMO-HORIZON-004",
            worker_id="demo_worker_001",
            category="electrical",
            location="CNC Area",
            display_status="In Progress",
            severity=3,
            likelihood=3,
            active=True,
            people_exposed=4,
            already_injured=False,
            raw_text=f"{workshop_qr} Machine panel spark noticed",
            translated_text="Machine panel spark noticed",
            language="en",
            equipment="CNC-04",
            qr=True,
            duplicate_count=3,
            duplicate_group=DUP_GROUP,
            hours_ago=20,
            officer="R. Silva",
            guidance_file="electrical_safety.md",
            guidance_line=electrical_line,
            reports=(
                ReportSpec(
                    "report_001", "demo_worker_001", "Machine panel spark noticed", "Machine panel spark noticed", 20
                ),
                ReportSpec(
                    "report_002",
                    "demo_worker_003",
                    "Same electrical smell and sparks",
                    "Same electrical smell and sparks",
                    12,
                ),
                ReportSpec(
                    "report_003",
                    "demo_worker_002",
                    "Repeated issue at same machine",
                    "Repeated issue at same machine",
                    5,
                ),
            ),
            slack_actions=("notified", "accepted", "escalated"),
            telegram=(
                ("inbound", "Machine panel spark noticed"),
                ("inbound", "Same electrical smell and sparks"),
                ("inbound", "Repeated issue at same machine"),
            ),
        ),
        IncidentSpec(
            demo_id="demo_horizon_incident_005",
            ref="DEMO-HORIZON-005",
            worker_id="demo_worker_002",
            category="missing PPE",
            location="Main Workshop Floor",
            display_status="Assigned",
            severity=3,
            likelihood=3,
            active=True,
            people_exposed=2,
            already_injured=False,
            raw_text="Helmet illa",
            translated_text="No helmet available",
            language="ta",
            hours_ago=2,
            officer="S. Bandara",
            guidance_file="general_hazards.md",
            guidance_line=general_line,
            slack_actions=("notified",),
            telegram=(("inbound", "Helmet illa"), ("outbound", general_line)),
        ),
        IncidentSpec(
            demo_id="demo_horizon_incident_006",
            ref="DEMO-HORIZON-006",
            worker_id="demo_worker_003",
            category="slip/trip",
            location="Loading Bay",
            display_status="Closed",
            severity=2,
            likelihood=2,
            active=False,
            people_exposed=1,
            already_injured=False,
            raw_text="Oil on the loading-bay floor, easy to slip",
            translated_text="Oil on the loading-bay floor, easy to slip",
            language="en",
            hours_ago=30,
            officer="M. Perera",
            guidance_file="general_hazards.md",
            guidance_line=general_line,
            evidence=(
                ("report", "before_spill.png", "Before: chemical spill on Loading Bay floor"),
                ("verification", "after_cleaned.png", "After: area cleaned and dry"),
            ),
            slack_actions=("notified", "accepted", "closed"),
            telegram=(
                ("inbound", "Oil on the loading-bay floor, easy to slip"),
                ("outbound", general_line),
                ("inbound", "Yes"),
                ("system", "Worker confirmed the area is safe"),
            ),
        ),
        IncidentSpec(
            demo_id="demo_horizon_incident_007",
            ref="DEMO-HORIZON-007",
            worker_id="demo_worker_003",
            category="fire/smoke",
            location="Welding Section",
            display_status="In Progress",
            severity=4,
            likelihood=3,
            active=True,
            people_exposed=2,
            already_injured=False,
            raw_text=f"{welding_qr} Smoke coming from equipment",
            translated_text="Smoke coming from equipment",
            language="en",
            equipment="Welder-07",
            qr=True,
            hours_ago=1.5,
            officer="A. Fernando",
            guidance_file="fire_safety.md",
            guidance_line=fire_line,
            slack_actions=("notified",),
            telegram=(("inbound", f"{welding_qr} Smoke coming from equipment"), ("outbound", fire_line)),
        ),
        IncidentSpec(
            demo_id="demo_horizon_incident_008",
            ref="DEMO-HORIZON-008",
            worker_id="demo_worker_004",
            category="unsafe behaviour",
            location="Main Workshop Floor",
            display_status="Assessed",
            severity=3,
            likelihood=2,
            active=True,
            people_exposed=4,
            already_injured=False,
            raw_text="Operator bypassed the press guard to speed the cycle",
            translated_text="Operator bypassed the press guard to speed the cycle",
            language="en",
            anonymous=True,
            hours_ago=10,
            officer="S. Bandara",
            guidance_file="general_hazards.md",
            guidance_line=general_line,
            slack_actions=("notified",),
            telegram=(("inbound", "Operator bypassed the press guard to speed the cycle"),),
        ),
        IncidentSpec(
            demo_id="demo_horizon_incident_009",
            ref="DEMO-HORIZON-009",
            worker_id="demo_worker_001",
            category="structural",
            location="Loading Bay",
            display_status="Validating",
            severity=3,
            likelihood=2,
            active=True,
            people_exposed=2,
            already_injured=False,
            raw_text="Crack appearing in the loading-bay beam",
            translated_text="Crack appearing in the loading-bay beam",
            language="en",
            hours_ago=0.4,
            guidance_file="general_hazards.md",
            guidance_line=general_line,
            blocked_guidance="Turn off the electrical supply yourself.",
            telegram=(("inbound", "Crack appearing in the loading-bay beam"),),
        ),
    )


@dataclass
class SeedSummary:
    organization: str = ORG_NAME
    workers: int = 0
    locations: int = 0
    incidents: int = 0
    created: int = 0
    reused: int = 0
    critical: int = 0
    recurring: int = 0
    closed_with_evidence: int = 0
    qr_reports: int = 0
    duplicate_reports: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "organization": self.organization,
            "workers": self.workers,
            "locations": self.locations,
            "incidents": self.incidents,
            "created": self.created,
            "reused": self.reused,
            "critical": self.critical,
            "recurring": self.recurring,
            "closed_with_evidence": self.closed_with_evidence,
            "qr_reports": self.qr_reports,
            "duplicate_reports": self.duplicate_reports,
            "errors": list(self.errors),
        }


class DemoSeeder:
    def __init__(self, repository: IncidentRepository, *, verbose: bool = False) -> None:
        self.repo = repository
        self.client = repository._client
        self.verbose = verbose
        self.created_refs: list[str] = []

    def log(self, message: str) -> None:
        if self.verbose:
            print(f"  · {message}")

    def seed(self, *, reset: bool = False) -> SeedSummary:
        if reset:
            removed = self.reset_demo_data()
            self.log(f"reset removed {removed} demo incident(s)")
        summary = SeedSummary(workers=len(WORKERS), locations=len(LOCATIONS))
        created_ids: list[UUID] = []
        created_refs: list[str] = []
        try:
            for spec in incident_catalog():
                incident, created = self._upsert_incident(spec)
                if created:
                    summary.created += 1
                    created_ids.append(incident.id)
                    created_refs.append(spec.ref)
                    self.created_refs.append(spec.ref)
                else:
                    summary.reused += 1
                self._ensure_related(incident, spec)
                summary.incidents += 1
                level = (incident.current_risk_level or "").upper()
                if level == "CRITICAL":
                    summary.critical += 1
                if spec.duplicate_count >= 3:
                    summary.recurring += 1
                    summary.duplicate_reports = max(summary.duplicate_reports, spec.duplicate_count)
                if spec.qr:
                    summary.qr_reports += 1
                if spec.display_status == "Closed" and spec.evidence:
                    summary.closed_with_evidence += 1
        except Exception as exc:
            summary.errors.append(str(exc) or exc.__class__.__name__)
            if created_ids or created_refs:
                self.log("partial failure — removing incidents created in this run")
                if self.repo.is_live_schema():
                    self._delete_live_refs(created_refs)
                else:
                    self._delete_incident_ids(created_ids)
            raise
        return summary

    def reset_demo_data(self) -> int:
        if self.repo.is_live_schema():
            refs = [spec.ref for spec in incident_catalog()]
            existing = sum(1 for spec in incident_catalog() if self.repo.get_incident_by_ref(spec.ref) is not None)
            self._delete_live_refs(refs)
            return existing
        ids = [item.id for item in self._demo_incidents()]
        self._delete_incident_ids(ids)
        return len(ids)

    def _delete_live_refs(self, refs: list[str]) -> None:
        for table in ("incident_evidence", "incident_updates", "assignments", "risk_assessments"):
            for ref in refs:
                self._delete_eq(table, "incident_id", ref)
        for ref in refs:
            self._delete_eq("incidents", "incident_id", ref)

    def _demo_incidents(self):
        found = []
        for spec in incident_catalog():
            row = self.repo.get_incident_by_ref(spec.ref)
            if row is not None:
                found.append(row)
        return found

    def _delete_incident_ids(self, ids: list[UUID]) -> None:
        keys = [str(item) for item in ids]
        if not keys:
            return
        for table, column in (
            ("incident_evidence", "incident_id"),
            ("incident_updates", "incident_id"),
            ("assignments", "incident_id"),
            ("risk_assessments", "incident_id"),
        ):
            for key in keys:
                self._delete_eq(table, column, key)
        pk = "incident_id" if self.repo.is_live_schema() else "id"
        for key in keys:
            self._delete_eq("incidents", pk, key)
            self._delete_eq("incidents", "incident_ref", str(key))

    def _delete_eq(self, table: str, column: str, value: str) -> None:
        try:
            query = self.client.table(table)
            if not hasattr(query, "delete"):
                self._delete_from_fake(table, column, value)
                return
            query.delete().eq(column, value).execute()
        except Exception as exc:
            if hasattr(self.client, "tables"):
                self._delete_from_fake(table, column, value)
                return
            message = getattr(exc, "message", None) or str(exc)
            raise PersistenceError(f"failed to delete demo rows from {table}: {message}") from exc

    def _delete_from_fake(self, table: str, column: str, value: str) -> None:
        rows = getattr(self.client, "tables", {}).get(table)
        if not isinstance(rows, list):
            return
        rows[:] = [row for row in rows if str(row.get(column)) != str(value)]

    def _live_upsert(self, table: str, payload: dict[str, Any], conflict: str) -> None:
        payload = {key: value for key, value in payload.items() if value is not None}
        query = self.client.table(table)
        upsert = getattr(query, "upsert", None)
        try:
            if upsert is not None:
                upsert(payload, on_conflict=conflict).execute()
                return
            query.insert(payload).execute()
        except Exception as exc:
            message = getattr(exc, "message", None) or str(exc)
            lowered = message.lower()
            if "duplicate" in lowered or "23505" in lowered or "already exists" in lowered:
                self.log(f"{table} already present")
                return
            raise PersistenceError(f"{table} write failed: {message}") from exc

    def _upsert_live_incident(self, spec: IncidentSpec):
        existing = self.repo.get_incident_by_ref(spec.ref)
        risk = calculate_risk(
            spec.severity,
            spec.likelihood,
            spec.active,
            spec.people_exposed,
            spec.category,
            spec.already_injured,
        )
        worker = _worker(spec.worker_id)
        reporter = "anonymous" if spec.anonymous else worker["reporter_id"]
        payload: dict[str, Any] = {
            "incident_id": spec.ref,
            "title": spec.translated_text,
            "description": spec.raw_text,
            "category": spec.category,
            "location": spec.location,
            "equipment_involved": spec.equipment or SITE_ID,
            "risk_level": risk["level"],
            "risk_score": risk["score"],
            "risk_explanation": risk["explanation"],
            "status": to_repository_status(spec.display_status),
            "reported_date": _iso(_utc(spec.hours_ago)),
            "reporter_id": reporter,
            "reporter_language": spec.language,
            "assigned_officer_id": spec.officer,
            "is_anonymous": spec.anonymous,
            "duplicate_count": spec.duplicate_count if spec.duplicate_count else 1,
        }
        if spec.display_status in {"Resolved", "Closed"}:
            payload["resolved_date"] = _iso(_utc(max(spec.hours_ago - 2, 0.1)))
        self._live_upsert("incidents", payload, "incident_id")
        refreshed = self.repo.get_incident_by_ref(spec.ref)
        if refreshed is None:
            raise PersistenceError(f"live incident {spec.ref} was written but could not be read back")
        self.log(f"{'reuse' if existing else 'created'} {spec.ref} (live) risk={risk['level']}")
        return refreshed, existing is None

    def _upsert_incident(self, spec: IncidentSpec):
        if self.repo.is_live_schema():
            return self._upsert_live_incident(spec)
        existing = self.repo.get_incident_by_ref(spec.ref)
        risk = calculate_risk(
            spec.severity,
            spec.likelihood,
            spec.active,
            spec.people_exposed,
            spec.category,
            spec.already_injured,
        )
        worker = _worker(spec.worker_id)
        reporter = "anonymous" if spec.anonymous else worker["reporter_id"]
        if existing is not None:
            self.log(f"reuse {spec.ref}")
            return existing, False
        created = self.repo.create_incident(
            IncidentCreate(
                incident_ref=spec.ref,
                reporter_id=reporter,
                source_channel="telegram",
                session_id=f"demo_session_{spec.demo_id}",
                detected_language=spec.language,
                hazard_category=spec.category,
                hazard_description=spec.translated_text,
                location=spec.location,
                injury_occurred=spec.already_injured,
                hazard_currently_active=spec.active,
                people_exposed=spec.people_exposed,
                status=to_repository_status(spec.display_status),
                current_risk_level=risk["level"],
                original_message_id=f"wamid.{spec.demo_id}",
                original_message_text=spec.raw_text,
                site_id=SITE_ID,
            )
        )
        self.log(f"created {spec.ref} risk={risk['level']} status={spec.display_status}")
        self._patch_incident(
            created.id,
            {
                "is_anonymous": spec.anonymous,
                "duplicate_count": spec.duplicate_count,
                "created_at": _iso(_utc(spec.hours_ago)),
                "site_id": SITE_ID,
            },
        )
        if spec.display_status in {"Resolved", "Closed"}:
            closed_at = _utc(max(spec.hours_ago - 2, 0.1))
            fields = {"resolved_at": _iso(closed_at)}
            if spec.display_status == "Closed":
                fields["closed_at"] = _iso(closed_at)
            try:
                self.repo.update_incident_fields(created.id, fields)
            except PersistenceError:
                self._patch_incident(created.id, fields)
        refreshed = self.repo.get_incident(created.id) or created
        return refreshed, True

    def _patch_incident(self, incident_id: UUID, fields: dict[str, Any]) -> None:
        try:
            allowed = {
                key: value
                for key, value in fields.items()
                if key
                in {
                    "status",
                    "resolved_at",
                    "closed_at",
                    "reopen_count",
                    "hazard_category",
                    "hazard_description",
                    "location",
                    "injury_occurred",
                    "hazard_currently_active",
                    "people_exposed",
                    "current_risk_level",
                    "session_id",
                    "detected_language",
                    "original_message_text",
                    "duplicate_of",
                    "site_id",
                }
                and value is not None
            }
            extra = {key: value for key, value in fields.items() if key not in allowed}
            if allowed:
                try:
                    self.repo.update_incident_fields(incident_id, allowed)
                except PersistenceError:
                    extra.update(allowed)
            if extra:
                self.client.table("incidents").update(extra).eq("id", str(incident_id)).execute()
        except Exception as exc:
            self.log(f"optional incident patch skipped: {exc.__class__.__name__}")

    def _ensure_related(self, incident, spec: IncidentSpec) -> None:
        risk = calculate_risk(
            spec.severity,
            spec.likelihood,
            spec.active,
            spec.people_exposed,
            spec.category,
            spec.already_injured,
        )
        record_key: UUID | str = spec.ref if self.repo.is_live_schema() else incident.id
        self._ensure_risk(record_key, spec, risk)
        self._ensure_assignment(record_key, spec)
        self._ensure_timeline(record_key, spec, risk)
        self._ensure_evidence(record_key, spec)

    def _has_demo_key(self, incident_id: UUID | str, demo_key: str) -> bool:
        for row in self.repo.list_updates_for_incident(incident_id):
            meta = row.metadata or {}
            if meta.get("demo_key") == demo_key:
                return True
        return False

    def _add_live_event(self, incident_ref: str, event: TimelineEventSpec) -> None:
        envelope = {
            "demo_key": event.demo_key,
            "update_type": event.update_type,
            "message": event.message,
            "previous_status": event.previous_status,
            "new_status": event.new_status,
            "actor_type": event.actor_type,
            "actor_reference": event.actor_reference,
            "metadata": event.metadata,
        }
        payload: dict[str, Any] = {
            "update_id": _demo_uuid(event.demo_key),
            "incident_id": incident_ref,
            "message": json.dumps(envelope, ensure_ascii=False),
            "updated_by": event.actor_reference,
        }
        if event.new_status:
            payload["status"] = event.new_status
        self._live_upsert("incident_updates", payload, "update_id")
        self.log(f"timeline {event.update_type} ({event.demo_key})")

    def _add_event(self, incident_id: UUID | str, event: TimelineEventSpec) -> None:
        if self._has_demo_key(incident_id, event.demo_key):
            return
        if self.repo.is_live_schema():
            self._add_live_event(str(incident_id), event)
            return
        self.repo.add_update(
            IncidentUpdateCreate(
                incident_id=incident_id if isinstance(incident_id, UUID) else UUID(str(incident_id)),
                update_type=event.update_type,
                previous_status=event.previous_status,
                new_status=event.new_status,
                actor_type=event.actor_type,
                actor_reference=event.actor_reference,
                message=event.message,
                metadata={"demo_key": event.demo_key, **event.metadata},
            )
        )
        self.log(f"timeline {event.update_type} ({event.demo_key})")

    def _ensure_risk(self, incident_id: UUID | str, spec: IncidentSpec, risk: dict[str, Any]) -> None:
        if self.repo.is_live_schema():
            self._live_upsert(
                "risk_assessments",
                {
                    "assessment_id": _demo_uuid(f"{spec.demo_id}:risk"),
                    "incident_id": str(incident_id),
                    "severity": spec.severity,
                    "likelihood": spec.likelihood,
                    "exposure": spec.people_exposed,
                    "final_score": risk["score"],
                    "explanation": risk["explanation"],
                    "confidence": 0.92,
                    "reviewed_by_human": spec.display_status in {"Awaiting Verification", "Closed", "Resolved"},
                },
                "assessment_id",
            )
            self.log(f"risk {risk['level']} score={risk['score']}")
            return
        existing = self.repo.list_risk_assessments_for_incident(incident_id)
        if existing:
            return
        payload = {
            "incident_id": str(incident_id),
            "severity": spec.severity,
            "severity_reason": risk["explanation"],
            "likelihood": spec.likelihood,
            "likelihood_reason": risk["explanation"],
            "risk_score": risk["score"],
            "base_risk_level": risk["base_level"],
            "final_risk_level": risk["level"],
            "applied_overrides": risk["escalation_reasons"],
            "assessment_version": 1,
        }
        try:
            self.client.table("risk_assessments").insert(payload).execute()
            self.log(f"risk {risk['level']} score={risk['score']}")
        except Exception as exc:
            self.log(f"risk insert skipped: {exc.__class__.__name__}")

    def _ensure_assignment(self, incident_id: UUID | str, spec: IncidentSpec) -> None:
        if spec.display_status in {"New", "Validating"}:
            return
        team = TEAMS.get(spec.category, "Facilities")
        assigned_at = _utc(spec.hours_ago - 0.2)
        if self.repo.is_live_schema():
            payload: dict[str, Any] = {
                "assignment_id": _demo_uuid(f"{spec.demo_id}:assignment"),
                "incident_id": str(incident_id),
                "department": team,
                "assigned_person": spec.officer,
                "due_time": _iso(assigned_at),
            }
            if spec.display_status in {"Accepted", "In Progress", "Awaiting Verification", "Resolved", "Closed"}:
                payload["accepted_time"] = _iso(_utc(spec.hours_ago - 0.35))
            if spec.display_status in {"Resolved", "Closed"}:
                payload["completion_time"] = _iso(_utc(max(spec.hours_ago - 2, 0.1)))
            self._live_upsert("assignments", payload, "assignment_id")
            self.log(f"assigned {team}")
            return
        existing = self.repo.get_assignment_for_incident(incident_id)
        if existing is not None:
            return
        team = TEAMS.get(spec.category, "Facilities")
        status_map = {
            "Assigned": "assigned",
            "Accepted": "accepted",
            "In Progress": "in_progress",
            "Awaiting Verification": "in_progress",
            "Resolved": "completed",
            "Closed": "completed",
            "Assessed": "assigned",
        }
        created = self.repo.assign_incident(
            AssignmentCreate(
                incident_id=incident_id if isinstance(incident_id, UUID) else UUID(str(incident_id)),
                team=team,
                slack_channel_id=_channel_for(team),
                assigned_to=spec.officer,
                assignment_status=status_map.get(spec.display_status, "assigned"),
            )
        )
        assigned_at = _utc(spec.hours_ago - 0.2)
        extra: dict[str, Any] = {"assigned_at": _iso(assigned_at)}
        if spec.display_status in {"Accepted", "In Progress", "Awaiting Verification", "Resolved", "Closed"}:
            extra["acknowledged_at"] = _iso(_utc(spec.hours_ago - 0.35))
        if spec.display_status in {"Resolved", "Closed"}:
            extra["completed_at"] = _iso(_utc(max(spec.hours_ago - 2, 0.1)))
        try:
            self.client.table("assignments").update(extra).eq("id", str(created.id)).execute()
        except Exception:
            pass
        self.log(f"assigned {team}")

    def _ensure_timeline(self, incident_id: UUID, spec: IncidentSpec, risk: dict[str, Any]) -> None:
        worker = _worker(spec.worker_id)
        team = TEAMS.get(spec.category, "Facilities")
        channel = _channel_for(team)
        org_meta = {
            "organization": ORG_NAME,
            "industry": INDUSTRY,
            "employees": EMPLOYEE_COUNT,
            "site_id": SITE_ID,
            "demo_worker_id": spec.worker_id,
            "preferred_language": worker["language"],
            "is_anonymous": spec.anonymous,
        }
        events: list[TimelineEventSpec] = [
            TimelineEventSpec(
                f"{spec.demo_id}:created",
                "incident_created",
                f"{ORG_NAME}: worker reported {spec.category} at {spec.location}.",
                new_status="REPORTED",
                metadata={
                    **org_meta,
                    "raw_text": spec.raw_text,
                    "translated_text": spec.translated_text,
                    "language": spec.language,
                    "location": spec.location,
                    "equipment": spec.equipment,
                    "qr": spec.qr,
                },
            ),
            TimelineEventSpec(
                f"{spec.demo_id}:intake",
                "intake_completed",
                f"AI intake classified language={spec.language} category={spec.category}.",
                previous_status="REPORTED",
                new_status="ASSESSING",
                metadata={
                    "raw_text": spec.raw_text,
                    "translated_text": spec.translated_text,
                    "language": spec.language,
                    "qr_location": spec.location if spec.qr else None,
                    "qr_equipment": spec.equipment if spec.qr else None,
                },
            ),
            TimelineEventSpec(
                f"{spec.demo_id}:assessed",
                "risk_assessed",
                risk["explanation"],
                previous_status="ASSESSING",
                new_status="OPEN",
                actor_reference="risk_agent",
                metadata={
                    "severity": spec.severity,
                    "likelihood": spec.likelihood,
                    "risk_score": risk["score"],
                    "risk_level": risk["level"],
                    "risk_explanation": risk["explanation"],
                    "people_exposed": spec.people_exposed,
                    "hazard_category": spec.category,
                    "location": spec.location,
                    "equipment": spec.equipment,
                },
            ),
        ]
        if spec.duplicate_count >= 3:
            for report in spec.reports:
                report_worker = _worker(report.worker_id)
                events.append(
                    TimelineEventSpec(
                        f"{spec.demo_id}:{report.report_id}",
                        "duplicate_report_linked",
                        f"Duplicate hazard detected from {report_worker['id']}: {report.translated_text}",
                        actor_reference="duplicate_tools",
                        metadata={
                            "duplicate_group_id": spec.duplicate_group,
                            "report_id": report.report_id,
                            "similarity": 0.86,
                            "location": spec.location,
                            "category": spec.category,
                            "raw_text": report.raw_text,
                            "translated_text": report.translated_text,
                            "hours_ago": report.hours_ago,
                        },
                    )
                )
            events.append(
                TimelineEventSpec(
                    f"{spec.demo_id}:dup_escalation",
                    "duplicate_threshold_reached",
                    "Priority increased — reported by multiple workers.",
                    actor_reference="duplicate_tools",
                    metadata={
                        "event": "duplicate_threshold_reached",
                        "duplicate_group_id": spec.duplicate_group,
                        "count": spec.duplicate_count,
                        "reason": "Multiple workers reporting same hazard",
                    },
                )
            )
        if spec.guidance_line:
            events.append(
                TimelineEventSpec(
                    f"{spec.demo_id}:guidance",
                    "guidance_sent",
                    spec.guidance_line,
                    actor_reference="guidance_agent",
                    metadata={
                        "knowledge_base_file": spec.guidance_file,
                        "guidance_source": spec.guidance_file,
                        "matched_lines": [spec.guidance_line],
                        "matched_line_count": 1,
                        "guidance_count": 1,
                        "hallucination_check": "Passed",
                        "validation_status": "approved",
                        "validated": True,
                        "generated_guidance": spec.guidance_line,
                    },
                )
            )
        if spec.blocked_guidance:
            events.append(
                TimelineEventSpec(
                    f"{spec.demo_id}:guidance_blocked",
                    "guidance_fallback",
                    "Invented instruction blocked; knowledge-base line released instead.",
                    actor_reference="guidance_agent",
                    metadata={
                        "knowledge_base_file": spec.guidance_file,
                        "ai_attempted": spec.blocked_guidance,
                        "hallucination_check": "Blocked",
                        "validation_status": "blocked",
                        "validated": False,
                        "generated_guidance": spec.guidance_line,
                        "matched_lines": [spec.guidance_line] if spec.guidance_line else [],
                    },
                )
            )
        if spec.category == "unsafe behaviour":
            events.append(
                TimelineEventSpec(
                    f"{spec.demo_id}:supervisor_review",
                    "supervisor_review",
                    "Supervisor reviewed the unsafe behaviour. Corrective action: toolbox talk and press-guard interlock check.",
                    actor_type="safety_officer",
                    actor_reference=spec.officer or "Safety Supervisor",
                    metadata={
                        "corrective_action": "toolbox talk and press-guard interlock reinstated",
                        "assigned_team": "Safety Supervisor",
                    },
                )
            )
        if spec.display_status not in {"New", "Validating"}:
            thread = f"{spec.ref}.thread"
            events.append(
                TimelineEventSpec(
                    f"{spec.demo_id}:slack",
                    "slack_coordination_completed",
                    f"Slack alert posted to {team} ({channel}).",
                    previous_status="OPEN",
                    new_status="ASSIGNED",
                    actor_reference="coordination_agent",
                    metadata={
                        "slack_channel": channel,
                        "message_id": f"{spec.ref}.msg",
                        "thread_id": thread,
                        "assigned_team": team,
                        "incident_id": spec.ref,
                        "risk": risk["level"],
                    },
                )
            )
        for action in spec.slack_actions:
            if action == "accepted":
                events.append(
                    TimelineEventSpec(
                        f"{spec.demo_id}:slack_accepted",
                        "incident_accepted",
                        "Accepted",
                        actor_type="safety_officer",
                        actor_reference=spec.officer or "officer",
                        previous_status="ASSIGNED",
                        new_status="ASSIGNED",
                        metadata={"slack_action": "Accepted", "assigned_team": team},
                    )
                )
            elif action == "escalated":
                events.append(
                    TimelineEventSpec(
                        f"{spec.demo_id}:slack_escalated",
                        "escalation_sent",
                        "Escalate",
                        actor_type="safety_officer",
                        actor_reference=spec.officer or "officer",
                        metadata={"slack_action": "Escalated", "assigned_team": team},
                    )
                )
            elif action == "closed":
                events.append(
                    TimelineEventSpec(
                        f"{spec.demo_id}:slack_closed",
                        "incident_closed",
                        "Closed",
                        actor_type="safety_officer",
                        actor_reference=spec.officer or "officer",
                        previous_status="RESOLVED",
                        new_status="CLOSED",
                        metadata={"slack_action": "Closed", "assigned_team": team},
                    )
                )
        if spec.display_status == "Awaiting Verification":
            events.append(
                TimelineEventSpec(
                    f"{spec.demo_id}:officer_resolution",
                    "incident_resolved",
                    "Chemical spill cleaned but worker confirmation pending.",
                    actor_type="safety_officer",
                    actor_reference=spec.officer or "officer",
                    previous_status="IN_PROGRESS",
                    new_status="AWAITING_VERIFICATION",
                    metadata={"resolution_attempt": True, "worker_confirmation": "pending"},
                )
            )
        if spec.display_status == "Closed":
            events.append(
                TimelineEventSpec(
                    f"{spec.demo_id}:worker_yes",
                    "worker_verification_confirmed",
                    "Worker confirmed the area is safe.",
                    actor_type="worker",
                    actor_reference=worker["reporter_id"],
                    previous_status="RESOLVED",
                    new_status="CLOSED",
                    metadata={"telegram_reply": "Yes"},
                )
            )
            events.append(
                TimelineEventSpec(
                    f"{spec.demo_id}:evidence_gallery",
                    "evidence_uploaded",
                    "Before/after evidence attached for closure.",
                    actor_type="safety_officer",
                    actor_reference=spec.officer or "officer",
                    metadata={
                        "before_image_url": "demo://horizon/before_spill.png",
                        "after_image_url": "demo://horizon/after_cleaned.png",
                        "type": "image/png",
                        "uploaded_by": spec.officer or worker["id"],
                    },
                )
            )
        for index, (direction, text) in enumerate(spec.telegram):
            events.append(
                TimelineEventSpec(
                    f"{spec.demo_id}:wa_{index}",
                    (
                        "telegram_inbound"
                        if direction == "inbound"
                        else ("telegram_outbound" if direction == "outbound" else "system_note")
                    ),
                    text,
                    actor_type="worker" if direction == "inbound" else "agent",
                    actor_reference=worker["reporter_id"] if direction == "inbound" else "telegram_handler",
                    metadata={"channel": "telegram", "direction": direction, "is_anonymous": spec.anonymous},
                )
            )
        if spec.display_status == "In Progress" and spec.duplicate_count:
            events.append(
                TimelineEventSpec(
                    f"{spec.demo_id}:still_exists",
                    "incident_reopened",
                    "No, still exists — incident returned to In Progress and the team was re-notified.",
                    actor_type="worker",
                    actor_reference=worker["reporter_id"],
                    previous_status="RESOLVED",
                    new_status="IN_PROGRESS",
                    metadata={"telegram_reply": "No, still exists", "team_renotified": True},
                )
            )
        path = _lifecycle_path(spec.display_status)
        for index, (previous, target) in enumerate(path):
            events.append(
                TimelineEventSpec(
                    f"{spec.demo_id}:lifecycle_{index}",
                    "status_transition",
                    f"{previous} → {target}",
                    previous_status=to_repository_status(previous),
                    new_status=to_repository_status(target),
                    metadata={"lifecycle": True},
                )
            )
        for event in events:
            self._add_event(incident_id, event)

    def _ensure_evidence(self, incident_id: UUID | str, spec: IncidentSpec) -> None:
        if not spec.evidence:
            return
        worker = _worker(spec.worker_id)
        if self.repo.is_live_schema():
            for stage, filename, caption in spec.evidence:
                file_url = f"demo://horizon/{spec.ref}/{filename}"
                try:
                    path = f"{spec.ref}/{stage}/{filename}"
                    self.client.storage.from_(self.repo._bucket).upload(path, DEMO_PNG, {"content-type": "image/png"})
                    url = self.client.storage.from_(self.repo._bucket).get_public_url(path)
                    if isinstance(url, str) and url:
                        file_url = url
                except Exception as exc:
                    self.log(f"evidence upload skipped: {exc.__class__.__name__}")
                self._live_upsert(
                    "incident_evidence",
                    {
                        "evidence_id": _demo_uuid(f"{spec.demo_id}:{stage}:{filename}"),
                        "incident_id": str(incident_id),
                        "evidence_stage": stage,
                        "file_type": "image/png",
                        "file_url": file_url,
                        "uploaded_by": worker["id"] if spec.anonymous is False else "anonymous",
                        "uploaded_time": _iso(_utc(max(spec.hours_ago - 1, 0.05))),
                    },
                    "evidence_id",
                )
                self.log(f"evidence {stage} {filename}")
            return
        existing = self.repo.list_evidence_for_incident(incident_id)
        captions = {row.caption_or_description for row in existing}
        worker = _worker(spec.worker_id)
        for stage, filename, caption in spec.evidence:
            if caption in captions:
                continue
            metadata = EvidenceCreate(
                evidence_type="image/png",
                source="telegram" if stage == "report" else "slack",
                caption_or_description=caption,
                uploaded_by=worker["id"] if spec.anonymous is False else "anonymous",
                external_message_id=f"wamid.{spec.demo_id}.{stage}",
            )
            try:
                self.repo.add_evidence(
                    EvidenceFile(content=DEMO_PNG, filename=filename, content_type="image/png"),
                    incident_id,
                    stage,
                    metadata=metadata,
                    filename=filename,
                    content_type="image/png",
                )
                self.log(f"evidence {stage} {filename}")
            except (EvidenceUploadError, PersistenceError, RecordNotFoundError):
                try:
                    self.client.table("incident_evidence").insert(
                        {
                            "incident_id": str(incident_id),
                            "stage": stage,
                            "evidence_type": "image/png",
                            "source": metadata.source,
                            "storage_reference": f"demo://horizon/{spec.ref}/{filename}",
                            "caption_or_description": caption,
                            "uploaded_by": metadata.uploaded_by,
                            "external_message_id": metadata.external_message_id,
                        }
                    ).execute()
                    self.log(f"evidence row without storage {filename}")
                except Exception as exc:
                    self.log(f"evidence skipped: {exc.__class__.__name__}")


def _lifecycle_path(display_status: str) -> list[tuple[str, str]]:
    order = (
        "New",
        "Validating",
        "Assessed",
        "Assigned",
        "Accepted",
        "In Progress",
        "Awaiting Verification",
        "Resolved",
        "Closed",
    )
    if display_status not in order:
        return []
    end = order.index(display_status)
    return list(zip(order[:end], order[1 : end + 1]))


def collect_summary(repository: IncidentRepository, seed: SeedSummary | None = None) -> SeedSummary:
    summary = seed or SeedSummary(workers=len(WORKERS), locations=len(LOCATIONS))
    incidents = []
    for spec in incident_catalog():
        row = repository.get_incident_by_ref(spec.ref)
        if row is not None:
            incidents.append((spec, row))
    summary.incidents = len(incidents)
    summary.critical = sum(1 for spec, row in incidents if (row.current_risk_level or "").upper() == "CRITICAL")
    summary.recurring = sum(1 for spec, _row in incidents if spec.duplicate_count >= 3)
    summary.qr_reports = sum(1 for spec, _row in incidents if spec.qr)
    summary.duplicate_reports = max((spec.duplicate_count for spec, _row in incidents), default=0)
    summary.closed_with_evidence = 0
    for spec, row in incidents:
        if spec.display_status != "Closed":
            continue
        key = repository.row_key(row)
        if repository.list_evidence_for_incident(key):
            summary.closed_with_evidence += 1
    return summary


def _check_mark() -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        "✓".encode(encoding)
        return "✓"
    except LookupError:
        return "OK"
    except UnicodeEncodeError:
        return "OK"


def print_report(summary: SeedSummary) -> None:
    mark = _check_mark()
    print()
    print("================================")
    print("Horizon Engineering Demo Seeder")
    print("================================")
    print()
    print("Organization:")
    print(f"{mark} {summary.organization}")
    print()
    print("Workers:")
    print(f"{mark} {summary.workers} created")
    print()
    print("Locations:")
    print(f"{mark} {summary.locations} created")
    print()
    print("Incidents:")
    print(f"{mark} {summary.incidents} created")
    print()
    print("Critical:")
    print(f"{mark} {summary.critical}")
    print()
    print("Recurring Hazards:")
    print(f"{mark} {summary.recurring}")
    print()
    print("Closed with Evidence:")
    print(f"{mark} {summary.closed_with_evidence}")
    print()
    print("QR Reports:")
    print(f"{mark} {summary.qr_reports}")
    print()
    print("Duplicate Reports:")
    print(f"{mark} {summary.duplicate_reports}")
    print()
    print("================================")
    print()
    print("Demo environment ready.")
    print("================================")
    print()


def seed_demo(
    repository: IncidentRepository | None = None,
    *,
    reset: bool = False,
    verbose: bool = False,
) -> SeedSummary:
    """Populate demo rows. Inject a repository in tests so no live credentials are required."""
    repo = repository or build_repository()
    summary = DemoSeeder(repo, verbose=verbose).seed(reset=reset)
    return collect_summary(repo, summary)


def build_repository(client: Any | None = None) -> IncidentRepository:
    if client is not None:
        return IncidentRepository(client, storage_bucket=os.environ.get("SUPABASE_STORAGE_BUCKET") or "evidence")
    return IncidentRepository()


def main(argv: list[str] | None = None, *, repository: IncidentRepository | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed Horizon Engineering Workshop demo data.")
    parser.add_argument("--reset", action="store_true", help="Delete only demo rows, then reseed.")
    parser.add_argument("--verbose", action="store_true", help="Print each insert.")
    parser.add_argument("--summary", action="store_true", help="Print the current demo summary without writing.")
    args = parser.parse_args(argv)
    load_local_env()
    try:
        repo = repository or build_repository()
    except DatabaseConfigError as exc:
        print(f"Cannot seed: {exc}", file=sys.stderr)
        print("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (see .env.example).", file=sys.stderr)
        return 2
    seeder = DemoSeeder(repo, verbose=args.verbose)
    try:
        if args.summary:
            summary = collect_summary(repo)
        else:
            summary = seeder.seed(reset=args.reset)
            summary = collect_summary(repo, summary)
    except PersistenceError as exc:
        cause = exc.__cause__
        extra = ""
        if cause is not None:
            extra = f" ({getattr(cause, 'message', None) or cause})"
        print(f"Database unavailable or schema mismatch: {exc}{extra}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"Demo seed failed: {exc}", file=sys.stderr)
        return 1
    print_report(summary)
    if args.verbose:
        print(json.dumps(summary.as_dict(), indent=2))
    if summary.errors:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
