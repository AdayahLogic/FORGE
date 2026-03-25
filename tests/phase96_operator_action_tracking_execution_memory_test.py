"""
Phase 96 operator action tracking + execution memory tests.

Run: python tests/phase96_operator_action_tracking_execution_memory_test.py
"""

from __future__ import annotations

import shutil
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@contextmanager
def _local_test_dir():
    base = ROOT / ".tmp_test_runs"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"phase96_{uuid.uuid4().hex[:8]}"
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


def _write_base_package(project_path: Path, package_id: str) -> None:
    from NEXUS.execution_package_registry import write_execution_package_safe

    ok = write_execution_package_safe(
        str(project_path),
        {
            "package_id": package_id,
            "project_name": "phase96proj",
            "project_path": str(project_path),
            "pipeline_stage": "proposal_pending",
            "execution_score": 0.9,
            "roi_estimate": 0.86,
            "conversion_probability": 0.81,
            "time_sensitivity": 0.74,
            "metadata": {
                "governance_status": "approved",
                "governance_routing_outcome": "continue",
                "enforcement_status": "continue",
            },
        },
    )
    assert ok


def test_normalize_execution_package_adds_operator_action_memory_fields():
    from NEXUS.execution_package_registry import normalize_execution_package

    normalized = normalize_execution_package(
        {
            "project_name": "phase96proj",
            "project_path": "C:/phase96",
            "pipeline_stage": "qualified",
        }
    )
    assert normalized["operator_action_status"] in {
        "pending",
        "acknowledged",
        "in_progress",
        "completed",
        "failed",
        "ignored",
        "cancelled",
    }
    assert bool(normalized["operator_action_id"])
    assert "operator_action_created_at" in normalized
    assert "operator_action_due_at" in normalized
    assert normalized["operator_action_attention_status"] in {"normal", "needs_attention", "overdue", "escalated"}
    assert isinstance(normalized["operator_action_history"], list)
    assert "linked_execution_result" in normalized
    assert "linked_conversion_result" in normalized
    assert "linked_revenue_realized" in normalized
    assert "operator_action_effect_on_revenue" in normalized
    assert "action_success_rate" in normalized
    assert "action_follow_through_rate" in normalized
    assert "action_to_reply_rate" in normalized
    assert "action_to_conversion_rate" in normalized


def test_command_surface_operator_action_lifecycle_and_outcome_linkage():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_base_package(tmp, "pkg-phase96-lifecycle")

        ack = run_command(
            "execution_package_acknowledge_operator_action",
            project_path=str(tmp),
            execution_package_id="pkg-phase96-lifecycle",
            acknowledgement_actor="operator-96",
            acknowledgement_notes="Acknowledge operator queue item.",
        )
        assert ack["status"] == "ok"
        assert ack["payload"]["operator_action"]["operator_action_status"] == "acknowledged"

        start = run_command(
            "execution_package_start_operator_action",
            project_path=str(tmp),
            execution_package_id="pkg-phase96-lifecycle",
            start_actor="operator-96",
            start_notes="Work in progress.",
        )
        assert start["status"] == "ok"
        assert start["payload"]["operator_action"]["operator_action_status"] == "in_progress"

        complete = run_command(
            "execution_package_complete_operator_action",
            project_path=str(tmp),
            execution_package_id="pkg-phase96-lifecycle",
            completion_actor="operator-96",
            completion_notes="Completed with explicit outcome links.",
            linked_execution_result="execution_completed",
            linked_conversion_result="closed_won",
            linked_revenue_realized=1.0,
            linked_communication_delivery_status="delivered",
            operator_action_effect_on_revenue="positive",
            operator_action_effect_reason="Converted after governed operator follow-through.",
        )
        assert complete["status"] == "ok"
        payload = complete["payload"]["operator_action"]
        assert payload["operator_action_status"] == "completed"
        assert float(payload["action_success_rate"] or 0.0) >= 0.0

        details = run_command(
            "execution_package_details",
            project_path=str(tmp),
            execution_package_id="pkg-phase96-lifecycle",
        )
        assert details["status"] == "ok"
        review_header = details["payload"]["review_header"]
        assert review_header["operator_action_status"] == "completed"
        assert review_header["linked_conversion_result"] == "closed_won"
        assert review_header["operator_action_effect_on_revenue"] == "positive"
        sections = details["payload"]["sections"]
        assert "operator_action_lifecycle" in sections
        assert "operator_action_memory" in sections
        assert sections["operator_action_memory"]["operator_action_history_count"] >= 1


def test_execution_package_queue_exposes_pending_overdue_and_attention_items():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import write_execution_package_safe

    with _local_test_dir() as tmp:
        _write_base_package(tmp, "pkg-phase96-overdue")
        _write_base_package(tmp, "pkg-phase96-complete")

        set_overdue = write_execution_package_safe(
            str(tmp),
            {
                "package_id": "pkg-phase96-overdue",
                "project_name": "phase96proj",
                "project_path": str(tmp),
                "operator_action_status": "pending",
                "operator_action_due_at": "2020-01-01T00:00:00+00:00",
                "operator_action_priority": "high",
                "metadata": {
                    "governance_status": "approved",
                    "governance_routing_outcome": "continue",
                    "enforcement_status": "continue",
                },
            },
        )
        assert set_overdue

        complete = run_command(
            "execution_package_complete_operator_action",
            project_path=str(tmp),
            execution_package_id="pkg-phase96-complete",
            completion_actor="operator-96",
            completion_notes="Closed item for queue segment validation.",
        )
        assert complete["status"] == "ok"

        queue = run_command("execution_package_queue", project_path=str(tmp), n=20)
        assert queue["status"] == "ok"
        payload = queue["payload"]
        assert "pending_operator_actions" in payload
        assert "overdue_operator_actions" in payload
        assert "completed_operator_actions" in payload
        assert "highest_priority_operator_attention" in payload

        pending_ids = {str(item.get("package_id") or "") for item in payload["pending_operator_actions"]}
        overdue_ids = {str(item.get("package_id") or "") for item in payload["overdue_operator_actions"]}
        completed_ids = {str(item.get("package_id") or "") for item in payload["completed_operator_actions"]}
        attention_ids = {str(item.get("package_id") or "") for item in payload["highest_priority_operator_attention"]}
        assert "pkg-phase96-overdue" in pending_ids
        assert "pkg-phase96-overdue" in overdue_ids
        assert "pkg-phase96-overdue" in attention_ids
        assert "pkg-phase96-complete" in completed_ids


def main():
    tests = [
        test_normalize_execution_package_adds_operator_action_memory_fields,
        test_command_surface_operator_action_lifecycle_and_outcome_linkage,
        test_execution_package_queue_exposes_pending_overdue_and_attention_items,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
