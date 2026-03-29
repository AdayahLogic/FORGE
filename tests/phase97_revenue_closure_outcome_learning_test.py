"""
Phase 97 revenue closure + outcome learning tests.

Run: python tests/phase97_revenue_closure_outcome_learning_test.py
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


def _write_package(project_path: Path, package_id: str, **overrides):
    from NEXUS.execution_package_registry import write_execution_package_safe

    package = {
        "package_id": package_id,
        "package_kind": "review_only_execution_envelope",
        "project_name": "phase97proj",
        "project_path": str(project_path),
        "run_id": "run-phase97",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "review_status": "reviewed",
        "runtime_target_id": "openclaw",
        "decision_status": "approved",
        "eligibility_status": "eligible",
        "release_status": "released",
        "handoff_status": "authorized",
        "execution_status": "pending",
        "mission_id": "msn-phase97",
        "mission_status": "in_progress",
        "lead_id": "lead-phase97",
        "lead_status": "new",
        "lead_priority": "medium",
        "email_status": "approval_required",
        "email_requires_approval": True,
        "follow_up_required": True,
        "follow_up_status": "pending",
        "follow_up_next_at": (datetime.now(timezone.utc) - timedelta(hours=96)).isoformat(),
        "delivery_status": "pending",
        "post_delivery_status": "pending",
        "deal_status": "open",
        "pipeline_stage": "follow_up",
        "metadata": {},
    }
    package.update(overrides)
    out = write_execution_package_safe(str(project_path), package)
    assert out


def test_follow_up_scheduler_and_stale_detection():
    from NEXUS.revenue_followup_scheduler import build_follow_up_status_summary
    from NEXUS.revenue_communication_loop import schedule_follow_up_safe

    with _local_test_dir() as tmp:
        _write_package(
            tmp,
            "pkg-followup",
            metadata={"last_outbound_email_at": (datetime.now(timezone.utc) - timedelta(hours=80)).isoformat()},
        )
        result = schedule_follow_up_safe(project_path=str(tmp), package_id="pkg-followup", no_response_hours=24, max_attempts=3)
        assert result["status"] == "ok"
        follow = result["follow_up"]
        assert "follow_up_reason" in follow
        assert "follow_up_retry_limit" in follow
        summary = build_follow_up_status_summary(project_path=str(tmp))
        assert summary["follow_up_status"] == "ok"
        assert summary["follow_up_count"] >= 1


def test_stalled_deal_detection_and_reengagement_queue():
    from NEXUS.revenue_followup_scheduler import build_reengagement_queue_summary, build_stalled_deals_summary

    with _local_test_dir() as tmp:
        _write_package(
            tmp,
            "pkg-stall",
            conversation_last_updated_at=(datetime.now(timezone.utc) - timedelta(hours=140)).isoformat(),
            follow_up_next_at=(datetime.now(timezone.utc) - timedelta(hours=70)).isoformat(),
            deal_status="open",
            pipeline_stage="negotiation",
            upsell_opportunity_detected=True,
        )
        stalled = build_stalled_deals_summary(project_path=str(tmp), stall_hours=72)
        assert stalled["stalled_deals_status"] == "ok"
        assert stalled["stalled_deals_count"] >= 1
        queue = build_reengagement_queue_summary(project_path=str(tmp))
        assert queue["reengagement_queue_status"] == "ok"
        assert queue["reengagement_count"] >= 1


def test_communication_send_receipt_transitions():
    from NEXUS.communication_receipt_registry import read_communication_receipt_journal_tail
    from NEXUS.revenue_communication_loop import send_email_safe

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-comm", email_thread_id="thread-1")
        blocked = send_email_safe(
            project_path=str(tmp),
            package_id="pkg-comm",
            to_email="lead@example.com",
            subject="Follow-up",
            body_text="Checking in.",
            approval_granted=False,
            approval_actor="operator",
        )
        assert blocked["status"] == "approval_required"
        rows = read_communication_receipt_journal_tail(project_path=str(tmp), n=20)
        assert rows
        assert rows[-1]["send_status"] == "approval_required"


def test_outcome_verification_and_performance_delta():
    from NEXUS.execution_package_registry import read_execution_package, record_execution_package_outcome_adaptation_safe
    from NEXUS.outcome_verifier_registry import build_performance_summary, read_outcome_verification_journal_tail

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-outcome", email_message_id="msg-1", execution_receipt_id="rcpt-1", verification_id="ver-1")
        result = record_execution_package_outcome_adaptation_safe(
            project_path=str(tmp),
            package_id="pkg-outcome",
            updates={
                "expected_outcome": "close_deal",
                "actual_outcome": "deal_closed",
                "expected_revenue": 1000.0,
                "actual_revenue": 1200.0,
                "expected_conversion": 0.4,
                "actual_conversion": 0.5,
                "outcome_status": "success",
                "operator_confirmed_outcome": True,
            },
        )
        assert result["status"] == "ok"
        package = read_execution_package(str(tmp), "pkg-outcome")
        assert package
        assert package.get("outcome_verification_status") in {"verified", "unverified", "pending"}
        rows = read_outcome_verification_journal_tail(project_path=str(tmp), n=20)
        assert rows
        perf = build_performance_summary(project_path=str(tmp), n=20)
        assert perf["performance_summary_status"] == "ok"
        assert perf["count"] >= 1


def test_helix_outcome_ingestion_inputs():
    from NEXUS.helix_outcome_inputs import build_helix_outcome_inputs
    from NEXUS.outcome_verifier_registry import append_outcome_verification_safe

    with _local_test_dir() as tmp:
        append_outcome_verification_safe(
            project_path=str(tmp),
            record={
                "execution_package_id": "pkg-helix",
                "expected_outcome": "delivery_success",
                "actual_outcome": "delivery_success",
                "expected_revenue": 500.0,
                "actual_revenue": 650.0,
                "success_classification": "success",
                "verification_status": "verified",
                "confidence": 0.9,
            },
        )
        inputs = build_helix_outcome_inputs(project_path=str(tmp))
        assert inputs["helix_outcome_inputs_status"] == "ok"
        assert inputs["verified_outcome_count"] >= 1
        assert "follow_up_effectiveness" in inputs


def test_command_surface_visibility_for_phase_6():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import record_execution_package_outcome_adaptation_safe

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-cmd")
        record_execution_package_outcome_adaptation_safe(
            project_path=str(tmp),
            package_id="pkg-cmd",
            updates={
                "expected_outcome": "retain_client",
                "actual_outcome": "partial_retention",
                "expected_revenue": 2000.0,
                "actual_revenue": 1400.0,
                "expected_conversion": 0.7,
                "actual_conversion": 0.45,
                "outcome_status": "partial",
            },
        )
        for command in (
            "follow_up_status",
            "stalled_deals",
            "reengagement_queue",
            "outcome_verification_status",
            "performance_summary",
            "helix_outcome_inputs",
        ):
            res = run_command(command, project_path=str(tmp), execution_package_id="pkg-cmd")
            assert res["status"] == "ok"
            assert isinstance(res.get("payload"), dict)


def main():
    tests = [
        test_follow_up_scheduler_and_stale_detection,
        test_stalled_deal_detection_and_reengagement_queue,
        test_communication_send_receipt_transitions,
        test_outcome_verification_and_performance_delta,
        test_helix_outcome_ingestion_inputs,
        test_command_surface_visibility_for_phase_6,
    ]
    passed = sum(1 for fn in tests if _run(fn.__name__, fn))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())

