"""
Phase 95.5 email communication foundation + approval-send loop tests.

Run: python tests/phase95_5_email_communication_approval_send_loop_test.py
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
    path = base / f"phase95_5_{uuid.uuid4().hex[:8]}"
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


def test_normalize_execution_package_adds_communication_fields():
    from NEXUS.execution_package_registry import normalize_execution_package

    normalized = normalize_execution_package(
        {
            "project_name": "phase95_5proj",
            "project_path": "C:/phase95_5",
            "pipeline_stage": "proposal_pending",
            "execution_score": 0.88,
            "roi_estimate": 0.86,
            "conversion_probability": 0.82,
            "time_sensitivity": 0.74,
            "metadata": {
                "governance_status": "approved",
                "governance_routing_outcome": "continue",
                "enforcement_status": "continue",
            },
        }
    )
    assert normalized["communication_channel"] == "email"
    assert normalized["communication_intent"] in {
        "proposal_nudge",
        "revenue_follow_up",
        "reactivation_touchpoint",
        "negotiation_checkpoint",
        "onboarding_request",
    }
    assert normalized["communication_status"] in {"draft_ready", "awaiting_approval", "approved", "sent", "denied"}
    assert bool(normalized["draft_message_subject"])
    assert bool(normalized["draft_message_body"])
    assert normalized["communication_requires_approval"] is True
    assert normalized["communication_approval_status"] in {"pending", "approved", "denied"}
    assert normalized["communication_delivery_status"] in {"not_sent", "delivery_pending", "delivered", "failed"}
    assert "communication_send_eligible" in normalized
    assert "follow_up_status" in normalized


def test_hard_block_keeps_communication_not_send_eligible():
    from NEXUS.execution_package_registry import normalize_execution_package

    normalized = normalize_execution_package(
        {
            "project_name": "phase95_5proj",
            "project_path": "C:/phase95_5",
            "pipeline_stage": "proposal_pending",
            "metadata": {
                "governance_status": "blocked",
                "governance_routing_outcome": "stop",
                "enforcement_status": "blocked",
            },
        }
    )
    assert normalized["revenue_activation_status"] == "blocked_for_revenue_action"
    assert normalized["communication_send_eligible"] is False
    assert "block" in str(normalized["communication_block_reason"]).lower()
    assert normalized["communication_status"] == "not_prepared"


def test_command_surface_enforces_approval_before_mark_sent():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import write_execution_package_safe

    with _local_test_dir() as tmp:
        assert write_execution_package_safe(
            str(tmp),
            {
                "package_id": "pkg-email",
                "project_name": "phase95_5proj",
                "project_path": str(tmp),
                "pipeline_stage": "proposal_pending",
                "execution_score": 0.9,
                "roi_estimate": 0.9,
                "conversion_probability": 0.82,
                "time_sensitivity": 0.78,
                "metadata": {
                    "governance_status": "approved",
                    "governance_routing_outcome": "continue",
                    "enforcement_status": "continue",
                },
            },
        )
        pre_send = run_command(
            "execution_package_mark_email_sent",
            project_path=str(tmp),
            execution_package_id="pkg-email",
            send_actor="operator-alpha",
            delivery_status="delivery_pending",
        )
        assert pre_send["status"] == "error"
        assert "explicit approved" in str(pre_send["summary"]).lower()

        approve = run_command(
            "execution_package_approve_email_draft",
            project_path=str(tmp),
            execution_package_id="pkg-email",
            approval_actor="operator-alpha",
            approval_notes="Approved for outbound send.",
        )
        assert approve["status"] == "ok"
        assert approve["payload"]["communication"]["communication_approval_status"] == "approved"

        mark_sent = run_command(
            "execution_package_mark_email_sent",
            project_path=str(tmp),
            execution_package_id="pkg-email",
            send_actor="operator-alpha",
            delivery_status="delivery_pending",
        )
        assert mark_sent["status"] == "ok"
        communication = mark_sent["payload"]["communication"]
        assert communication["communication_status"] == "sent"
        assert communication["communication_delivery_status"] == "delivery_pending"
        assert bool(communication["communication_sent_at"])


def test_execution_package_queue_exposes_communication_segments():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import write_execution_package_safe

    with _local_test_dir() as tmp:
        assert write_execution_package_safe(
            str(tmp),
            {
                "package_id": "pkg-awaiting",
                "project_name": "phase95_5proj",
                "project_path": str(tmp),
                "pipeline_stage": "proposal_pending",
                "execution_score": 0.88,
                "roi_estimate": 0.84,
                "conversion_probability": 0.8,
                "time_sensitivity": 0.76,
                "metadata": {
                    "governance_status": "approved",
                    "governance_routing_outcome": "continue",
                    "enforcement_status": "continue",
                },
            },
        )
        assert write_execution_package_safe(
            str(tmp),
            {
                "package_id": "pkg-denied",
                "project_name": "phase95_5proj",
                "project_path": str(tmp),
                "pipeline_stage": "qualified",
                "communication_approval_status": "denied",
                "communication_denied_reason": "Needs legal review.",
                "metadata": {
                    "governance_status": "approved",
                    "governance_routing_outcome": "continue",
                    "enforcement_status": "continue",
                },
            },
        )

        approve = run_command(
            "execution_package_approve_email_draft",
            project_path=str(tmp),
            execution_package_id="pkg-awaiting",
            approval_actor="operator-beta",
        )
        assert approve["status"] == "ok"
        sent = run_command(
            "execution_package_mark_email_sent",
            project_path=str(tmp),
            execution_package_id="pkg-awaiting",
            send_actor="operator-beta",
        )
        assert sent["status"] == "ok"

        queue = run_command("execution_package_queue", project_path=str(tmp), n=20)
        assert queue["status"] == "ok"
        payload = queue["payload"]
        assert "awaiting_communication_approval" in payload
        assert "communication_sent_items" in payload
        assert "communication_blocked_items" in payload
        assert "communication_pending_delivery_items" in payload
        sent_ids = {str(item.get("package_id") or "") for item in payload["communication_sent_items"]}
        blocked_ids = {str(item.get("package_id") or "") for item in payload["communication_blocked_items"]}
        assert "pkg-awaiting" in sent_ids
        assert "pkg-denied" in blocked_ids


def main():
    tests = [
        test_normalize_execution_package_adds_communication_fields,
        test_hard_block_keeps_communication_not_send_eligible,
        test_command_surface_enforces_approval_before_mark_sent,
        test_execution_package_queue_exposes_communication_segments,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
