"""
Phase 97 follow-up intelligence + action sequencing tests.

Run: python tests/phase97_follow_up_intelligence_action_sequencing_test.py
"""

from __future__ import annotations

import shutil
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@contextmanager
def _local_test_dir():
    base = ROOT / ".tmp_test_runs"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"phase97_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _run(name: str, fn):
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except Exception as exc:
        print(f"FAIL: {name} - {exc}")
        return False


def _write_base_package(project_path: Path, package_id: str, **overrides):
    from NEXUS.execution_package_registry import write_execution_package_safe

    payload = {
        "package_id": package_id,
        "project_name": "phase97proj",
        "project_path": str(project_path),
        "pipeline_stage": "follow_up",
        "execution_score": 0.86,
        "roi_estimate": 0.84,
        "conversion_probability": 0.78,
        "time_sensitivity": 0.77,
        "communication_channel": "email",
        "communication_approval_status": "approved",
        "communication_status": "sent",
        "communication_sent_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "communication_delivery_status": "delivered",
        "follow_up_status": "follow_up_due",
        "follow_up_due_at": (datetime.now(timezone.utc) - timedelta(days=2)).replace(microsecond=0).isoformat(),
        "metadata": {
            "governance_status": "approved",
            "governance_routing_outcome": "continue",
            "enforcement_status": "continue",
        },
    }
    payload.update(overrides)
    assert write_execution_package_safe(str(project_path), payload)


def test_normalize_adds_action_sequence_and_follow_up_intelligence_fields():
    from NEXUS.execution_package_registry import normalize_execution_package

    normalized = normalize_execution_package(
        {
            "project_name": "phase97proj",
            "project_path": "C:/phase97",
            "pipeline_stage": "follow_up",
            "execution_score": 0.85,
            "roi_estimate": 0.8,
            "conversion_probability": 0.75,
            "time_sensitivity": 0.7,
            "communication_channel": "email",
            "communication_approval_status": "approved",
            "communication_status": "sent",
            "communication_sent_at": "2026-01-01T00:00:00+00:00",
            "communication_delivery_status": "delivered",
            "follow_up_status": "follow_up_due",
            "follow_up_due_at": "2026-01-04T00:00:00+00:00",
            "metadata": {
                "governance_status": "approved",
                "governance_routing_outcome": "continue",
                "enforcement_status": "continue",
            },
        }
    )
    assert normalized["action_sequence_status"] in {"not_started", "active", "waiting", "completed", "abandoned", "stalled"}
    assert normalized["action_sequence_type"] in {"follow_up", "proposal", "negotiation", "onboarding", "general"}
    assert int(normalized["action_sequence_total_steps"] or 0) >= 1
    assert "action_sequence_next_step" in normalized
    assert normalized["follow_up_intelligence_status"] in {
        "not_applicable",
        "pending_send",
        "waiting_response",
        "action_recommended",
        "overdue_action",
        "dropoff_risk",
    }
    assert normalized["follow_up_priority"] in {"low", "medium", "high", "critical"}
    assert normalized["follow_up_recommendation"] in {
        "send_second_follow_up",
        "escalate_to_human_review",
        "wait_for_response",
        "prepare_offer",
        "schedule_final_attempt",
        "defer_low_value_follow_up",
    }
    assert normalized["follow_up_window_status"] in {"no_window", "upcoming", "due_now", "overdue"}
    assert isinstance(bool(normalized["action_sequence_dropoff_detected"]), bool)


def test_command_surface_action_sequence_transitions_are_governed():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_base_package(tmp, "pkg-phase97-seq")

        advance = run_command(
            "execution_package_advance_action_sequence",
            project_path=str(tmp),
            execution_package_id="pkg-phase97-seq",
            advance_actor="operator-97",
            advance_notes="Move to the next governed step.",
        )
        assert advance["status"] == "ok"
        assert advance["payload"]["action_sequence"]["action_sequence_status"] in {"active", "completed", "stalled"}

        pause = run_command(
            "execution_package_pause_action_sequence",
            project_path=str(tmp),
            execution_package_id="pkg-phase97-seq",
            pause_actor="operator-97",
            pause_notes="Waiting for client response.",
        )
        assert pause["status"] == "ok"
        assert pause["payload"]["action_sequence"]["action_sequence_status"] == "waiting"

        status = run_command(
            "execution_package_action_sequence_status",
            project_path=str(tmp),
            execution_package_id="pkg-phase97-seq",
        )
        assert status["status"] == "ok"
        assert status["payload"]["action_sequence"]["action_sequence_status"] in {"waiting", "active", "completed", "abandoned", "stalled"}
        assert "follow_up_intelligence" in status["payload"]


def test_execution_package_queue_exposes_phase97_segments():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_base_package(tmp, "pkg-phase97-overdue")
        _write_base_package(
            tmp,
            "pkg-phase97-stalled",
            action_sequence_status="stalled",
            action_sequence_step=2,
            action_sequence_total_steps=3,
            action_sequence_dropoff_detected=True,
            action_sequence_dropoff_reason="sequence_stalled",
            action_sequence_recovery_recommendation="escalate_to_human_review",
        )

        queue = run_command("execution_package_queue", project_path=str(tmp), n=20)
        assert queue["status"] == "ok"
        payload = queue["payload"]
        assert "overdue_follow_ups" in payload
        assert "stalled_sequences" in payload
        assert "next_best_follow_up_actions" in payload
        assert "recovery_needed_opportunities" in payload
        assert len(payload["overdue_follow_ups"]) >= 1
        assert len(payload["stalled_sequences"]) >= 1


if __name__ == "__main__":
    tests = [
        ("test_normalize_adds_action_sequence_and_follow_up_intelligence_fields", test_normalize_adds_action_sequence_and_follow_up_intelligence_fields),
        ("test_command_surface_action_sequence_transitions_are_governed", test_command_surface_action_sequence_transitions_are_governed),
        ("test_execution_package_queue_exposes_phase97_segments", test_execution_package_queue_exposes_phase97_segments),
    ]
    passed = 0
    for name, fn in tests:
        if _run(name, fn):
            passed += 1
    total = len(tests)
    print(f"\n{passed}/{total} passed")
    raise SystemExit(0 if passed == total else 1)
