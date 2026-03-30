"""
Phase 95 live governed revenue channel tests.

Run: python tests/phase95_live_governed_revenue_channel_test.py
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
    path = base / f"phase95_{uuid.uuid4().hex[:8]}"
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


def _write_revenue_ready_package(project_path: Path, *, package_id: str = "pkg-phase95"):
    from NEXUS.execution_package_registry import write_execution_package_safe

    assert write_execution_package_safe(
        str(project_path),
        {
            "package_id": package_id,
            "project_name": "phase95proj",
            "project_path": str(project_path),
            "pipeline_stage": "follow_up",
            "requires_human_approval": True,
            "approval_id_refs": ["approval-phase95"],
            "metadata": {
                "revenue_preview": {
                    "response_summary": {
                        "response_status": "response_ready",
                        "response_message": "Thanks for the details. Here is the proposed next step.",
                    }
                },
                "revenue_lane": {
                    "channel": "smtp_email",
                    "truth": {
                        "draft_ready": True,
                        "awaiting_approval": True,
                    },
                },
            },
        },
    )


def _patch_send(ok: bool = True):
    import NEXUS.revenue_communication_registry as comms

    old_send = comms.send_governed_email_safe
    old_ready = comms.smtp_channel_readiness

    def _ready():
        return {
            "channel_id": "smtp_email",
            "channel_type": "email",
            "ready": True,
            "missing_requirements": [],
            "config": {"host": "smtp.test", "port": 587, "from": "forge@example.com", "username": "forge", "use_starttls": True},
            "safety_posture": "explicit_approval_required",
        }

    def _send_success(**kwargs):
        return {
            "status": "sent",
            "failure_class": "",
            "error": "",
            "provider_message_id": "msg-phase95-success",
            "channel_readiness": _ready(),
        }

    def _send_failure(**kwargs):
        return {
            "status": "failed",
            "failure_class": "smtp_send_failed",
            "error": "simulated smtp outage",
            "provider_message_id": "msg-phase95-failure",
            "channel_readiness": _ready(),
        }

    comms.smtp_channel_readiness = _ready
    comms.send_governed_email_safe = _send_success if ok else _send_failure
    return old_send, old_ready


def _restore_send(old_send, old_ready):
    import NEXUS.revenue_communication_registry as comms

    comms.send_governed_email_safe = old_send
    comms.smtp_channel_readiness = old_ready


def test_approved_send_path_persists_real_receipt():
    from NEXUS.approval_registry import append_approval_record_safe
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_revenue_ready_package(tmp, package_id="pkg-approved")
        append_approval_record_safe(
            project_path=str(tmp),
            record={
                "approval_id": "approval-phase95",
                "status": "approved",
                "decision": "approve",
                "project_name": "phase95proj",
            },
        )
        old_send, old_ready = _patch_send(ok=True)
        try:
            send = run_command(
                "governed_revenue_send_request",
                project_path=str(tmp),
                execution_package_id="pkg-approved",
                approval_id="approval-phase95",
                operator_id="operator",
                to_email="lead@example.com",
                subject="Governed follow-up",
                body="Approved response message.",
            )
            assert send["status"] == "ok"
            assert send["payload"]["send_status"] == "sent"
            receipt = send["payload"]["receipt"]
            assert receipt["status"] == "sent"
            assert receipt["provider_message_id"] == "msg-phase95-success"

            receipts = run_command("sent_receipts", project_path=str(tmp), n=20)
            assert receipts["status"] == "ok"
            rows = receipts["payload"]["receipts"]
            assert any(str(row.get("status") or "") == "sent" for row in rows)
        finally:
            _restore_send(old_send, old_ready)


def test_unapproved_send_is_blocked_and_receipt_backed():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_revenue_ready_package(tmp, package_id="pkg-unapproved")
        old_send, old_ready = _patch_send(ok=True)
        try:
            send = run_command(
                "governed_revenue_send_request",
                project_path=str(tmp),
                execution_package_id="pkg-unapproved",
                approval_id="missing-approval",
                operator_id="operator",
                to_email="lead@example.com",
                subject="Governed follow-up",
                body="This should be blocked.",
            )
            assert send["status"] == "error"
            assert send["payload"]["send_status"] == "blocked"
            assert send["payload"]["receipt"]["failure_class"] == "approval_required"
        finally:
            _restore_send(old_send, old_ready)


def test_send_failure_marks_failed_and_visible():
    from NEXUS.approval_registry import append_approval_record_safe
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_revenue_ready_package(tmp, package_id="pkg-failure")
        append_approval_record_safe(
            project_path=str(tmp),
            record={
                "approval_id": "approval-phase95",
                "status": "approved",
                "decision": "approve",
                "project_name": "phase95proj",
            },
        )
        old_send, old_ready = _patch_send(ok=False)
        try:
            send = run_command(
                "governed_revenue_send_request",
                project_path=str(tmp),
                execution_package_id="pkg-failure",
                approval_id="approval-phase95",
                operator_id="operator",
                to_email="lead@example.com",
                subject="Governed follow-up",
                body="This should fail.",
            )
            assert send["status"] == "error"
            assert send["payload"]["send_status"] == "failed"
            queue = run_command("execution_package_queue", project_path=str(tmp), n=20)
            package = next((row for row in queue["payload"]["packages"] if row.get("package_id") == "pkg-failure"), {})
            truth = package.get("revenue_lane_truth") or {}
            assert bool(truth.get("failed"))
        finally:
            _restore_send(old_send, old_ready)


def test_response_event_linkage_updates_lane_truth():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_revenue_ready_package(tmp, package_id="pkg-response")
        event = run_command(
            "record_revenue_response_event",
            project_path=str(tmp),
            execution_package_id="pkg-response",
            receipt_id="receipt-1",
            event_type="response_received",
            event_summary="Prospect replied with discovery call availability.",
            evidence_ref="email_thread://phase95/receipt-1",
        )
        assert event["status"] == "ok"
        events = run_command("response_events", project_path=str(tmp), n=20)
        assert events["status"] == "ok"
        assert any(str(row.get("event_type") or "") == "response_received" for row in events["payload"]["events"])


def test_outcome_verification_updates_pipeline_and_history():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import read_execution_package

    with _local_test_dir() as tmp:
        _write_revenue_ready_package(tmp, package_id="pkg-outcome")
        outcome = run_command(
            "verify_revenue_outcome",
            project_path=str(tmp),
            execution_package_id="pkg-outcome",
            receipt_id="receipt-1",
            outcome_status="closed_won",
            outcome_summary="Client accepted the offer and started onboarding.",
            evidence_ref="crm://deals/phase95/won",
            operator_confirmed=True,
        )
        assert outcome["status"] == "ok"
        outcomes = run_command("real_revenue_outcomes", project_path=str(tmp), n=20)
        assert outcomes["status"] == "ok"
        assert outcomes["payload"]["closed_won_count"] == 1
        pkg = read_execution_package(str(tmp), "pkg-outcome") or {}
        assert pkg.get("pipeline_stage") == "closed_won"
        assert pkg.get("revenue_outcome_status") == "closed_won"


def test_operator_visibility_commands_expose_lane_state():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_revenue_ready_package(tmp, package_id="pkg-visibility")
        pending = run_command("approval_ready_sends", project_path=str(tmp), n=20)
        assert pending["status"] == "ok"
        assert any(str(item.get("package_id") or "") == "pkg-visibility" for item in pending["payload"]["approval_ready_sends"])
        status = run_command("live_revenue_channel_status", project_path=str(tmp), n=20)
        assert status["status"] == "ok"
        assert "channel_readiness" in status["payload"]
        assert "lane_status_counts" in status["payload"]


def main():
    tests = [
        test_approved_send_path_persists_real_receipt,
        test_unapproved_send_is_blocked_and_receipt_backed,
        test_send_failure_marks_failed_and_visible,
        test_response_event_linkage_updates_lane_truth,
        test_outcome_verification_updates_pipeline_and_history,
        test_operator_visibility_commands_expose_lane_state,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
