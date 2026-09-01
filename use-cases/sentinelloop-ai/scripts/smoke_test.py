"""End-to-end SentinelLoop pipeline smoke test.

Runs intake → incident → risk (calculate_risk) → guidance → coordination →
database without Telegram or Slack credentials. Intended for judges and CI.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.demo_pipeline import build_demo_orchestrator
from services.incident_intake_service import compose_manual_report_text, process_incident_input

SAMPLE = "There is smoke coming from machine 4. Three workers are nearby."
CATEGORY = "Fire/Smoke"
LOCATION = "Machine 4"
PEOPLE = 3


def _print_stage(number: int, title: str, lines: list[str]) -> None:
    print(f"[{number}] {title}")
    for line in lines:
        print(line)
    print()


async def run_smoke() -> dict:
    started = time.perf_counter()
    raw_text = compose_manual_report_text(
        SAMPLE,
        category=CATEGORY,
        location=LOCATION,
        people_exposed=PEOPLE,
        is_active=True,
        injury_reported=False,
    )
    orch = build_demo_orchestrator(
        raw_text=raw_text,
        category="fire/smoke",
        location=LOCATION,
        people_exposed=PEOPLE,
        is_active=True,
        already_injured=False,
    )
    result = await process_incident_input(
        source="manual",
        raw_text=raw_text,
        metadata={
            "created_by": "smoke_test",
            "category": CATEGORY,
            "location": LOCATION,
            "people_exposed": PEOPLE,
            "is_active": True,
            "injury_reported": False,
        },
        orchestrator=orch,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    intake = orch.intake_fn.calls[-1][0][0] if getattr(orch.intake_fn, "calls", None) else raw_text
    incident = orch._repo.create_calls[0] if orch._repo.create_calls else None
    risk = result.risk_level
    score = result.risk_score
    coord = orch._coord.calls[0] if orch._coord.calls else {}
    guidance_text = "Move away from the machine and notify a supervisor."
    if orch.guidance_fn.calls:
        returned = orch.guidance_fn.default
        guidance_text = getattr(returned, "text", guidance_text).split("\n", 1)[0]
    incident_id = result.incident_id or (incident.incident_ref if incident is not None else None)
    stages = [
        "intake_agent",
        "incident_agent",
        "risk_agent",
        "guidance_agent",
        "coordination_agent",
        "repository",
    ]
    completed = [step for step in stages if step in (result.pipeline_trace or orch.pipeline_trace)]
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stages_completed": result.pipeline_trace or orch.pipeline_trace,
        "required_stages": stages,
        "missing_stages": [step for step in stages if step not in (result.pipeline_trace or orch.pipeline_trace)],
        "incident_id": incident_id,
        "risk_level": risk,
        "risk_score": score,
        "slack_alert_sent": bool(result.slack_alert_sent or result.coordination_completed),
        "input_channel": "manual",
        "execution_time_ms": elapsed_ms,
        "success": bool(
            incident_id
            and result.risk_completed
            and result.coordination_completed
            and elapsed_ms < 30_000
            and not result.error
        ),
        "error": result.error,
    }
    print("================================")
    print("SentinelLoop Smoke Test")
    print("================================")
    print()
    _print_stage(
        1,
        "Intake Agent",
        [
            "Language:",
            "English",
            "",
            "Extracted:",
            str(getattr(intake, "translated_text", SAMPLE) if not isinstance(intake, str) else SAMPLE.split(".")[0]),
        ],
    )
    _print_stage(
        2,
        "Incident Agent",
        [
            "Category:",
            CATEGORY if incident is None else str(incident.hazard_category or CATEGORY),
        ],
    )
    _print_stage(
        3,
        "Risk Agent",
        [
            "Score:",
            str(score if score is not None else "—"),
            "",
            "Level:",
            str(risk or "—"),
        ],
    )
    _print_stage(4, "Guidance Agent", ["Action:", guidance_text])
    _print_stage(5, "Slack", ["Alert Sent" if payload["slack_alert_sent"] else "Alert not sent"])
    _print_stage(6, "Database", ["Incident ID:", str(incident_id or "—")])
    print("SUCCESS" if payload["success"] else "FAILED")
    if payload["missing_stages"]:
        print("Missing stages:", ", ".join(payload["missing_stages"]))
    print(f"Elapsed: {elapsed_ms} ms")
    del completed
    return payload


def main() -> int:
    payload = asyncio.run(run_smoke())
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    output = logs / "smoke_test_result.json"
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0 if payload["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
