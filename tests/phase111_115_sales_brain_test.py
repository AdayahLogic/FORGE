"""
Phase 111-115 sales brain + conversation engine tests.

Run: python tests/phase111_115_sales_brain_test.py
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
    path = base / f"phase111_{uuid.uuid4().hex[:8]}"
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


def _write_package(project_path: Path, package_id: str = "pkg-phase111") -> str:
    from NEXUS.execution_package_registry import write_execution_package_safe

    payload = {
        "package_id": package_id,
        "project_name": "phase111proj",
        "project_path": str(project_path),
        "created_at": "2026-03-26T00:00:00+00:00",
        "package_status": "review_pending",
        "review_status": "pending",
        "requires_human_approval": True,
        "lead_id": "lead-fixed-1",
        "lead_status": "new",
        "lead_priority": "medium",
        "lead_intent": "pricing_request",
        "lead_business_type": "general_business",
        "email_thread_id": "thread-phase111",
    }
    assert write_execution_package_safe(str(project_path), payload)
    return package_id


def test_qualification_logic_consistency():
    from NEXUS.revenue_communication_loop import evaluate_sales_brain_safe

    with _local_test_dir() as tmp:
        package_id = _write_package(tmp, "pkg-consistency")
        inbound = {
            "subject": "Need proposal this week",
            "body": "We are ready to review pricing and timeline this week.",
            "thread_id": "thread-phase111",
        }
        first = evaluate_sales_brain_safe(project_path=str(tmp), package_id=package_id, inbound_email=inbound)
        second = evaluate_sales_brain_safe(project_path=str(tmp), package_id=package_id, inbound_email=inbound)
        a = first["sales_brain"]
        b = second["sales_brain"]
        assert a["qualification_status"] == b["qualification_status"]
        assert a["qualification_score"] == b["qualification_score"]
        assert 0.0 <= float(a["qualification_score"]) <= 1.0
        assert a["qualification_reason"]


def test_offer_generation_structure_is_bounded():
    from NEXUS.revenue_communication_loop import evaluate_sales_brain_safe

    with _local_test_dir() as tmp:
        package_id = _write_package(tmp, "pkg-offer")
        result = evaluate_sales_brain_safe(
            project_path=str(tmp),
            package_id=package_id,
            inbound_email={
                "subject": "Requesting pricing estimate",
                "body": "Please share a scoped pricing estimate for automation rollout.",
                "thread_id": "thread-phase111",
            },
        )
        offer = result["sales_brain"]
        assert offer["offer_type"]
        assert offer["offer_summary"]
        assert "estimate" in str(offer["offer_price_estimate"]).lower()
        assert 0.0 <= float(offer["offer_confidence"]) <= 1.0
        assert offer["offer_customization_reason"]


def test_objection_detection_correctness():
    from NEXUS.revenue_communication_loop import evaluate_sales_brain_safe

    with _local_test_dir() as tmp:
        package_id = _write_package(tmp, "pkg-objection")
        result = evaluate_sales_brain_safe(
            project_path=str(tmp),
            package_id=package_id,
            inbound_email={
                "subject": "Concern about cost",
                "body": "This might be too expensive for our budget right now.",
                "thread_id": "thread-phase111",
            },
        )
        sales = result["sales_brain"]
        assert sales["objection_detected"] is True
        assert sales["objection_type"] == "price"
        assert sales["objection_response_strategy"]
        assert sales["objection_response_draft"]


def test_closing_signal_detection_and_recommendation():
    from NEXUS.revenue_communication_loop import evaluate_sales_brain_safe

    with _local_test_dir() as tmp:
        package_id = _write_package(tmp, "pkg-closing")
        result = evaluate_sales_brain_safe(
            project_path=str(tmp),
            package_id=package_id,
            inbound_email={
                "subject": "Ready to proceed",
                "body": "Looks good. We are ready to sign and move forward.",
                "thread_id": "thread-phase111",
            },
        )
        closing = result["sales_brain"]
        assert closing["closing_signal_detected"] is True
        assert closing["closing_signal_type"] in {"confirmation", "readiness"}
        assert 0.0 <= float(closing["closing_confidence"]) <= 1.0
        assert closing["recommended_closing_action"]
        assert closing["closing_message_draft"]


def test_conversation_memory_persists_across_interactions():
    from NEXUS.execution_package_registry import read_execution_package
    from NEXUS.revenue_communication_loop import ingest_email_lead_safe, send_email_safe

    with _local_test_dir() as tmp:
        package_id = _write_package(tmp, "pkg-convo")
        ingested = ingest_email_lead_safe(
            project_path=str(tmp),
            package_id=package_id,
            inbound_email={
                "sender": "alex@northwind.example",
                "subject": "Need proposal",
                "body": "Can we move quickly on this?",
                "timestamp": "2026-03-26T01:00:00+00:00",
                "thread_id": "thread-convo",
                "message_id": "msg-convo-1",
            },
        )
        assert ingested["status"] == "ok"
        blocked_send = send_email_safe(
            project_path=str(tmp),
            package_id=package_id,
            to_email="alex@northwind.example",
            subject="Draft next step",
            body_text="Thanks for the context. I can send a scoped next-step plan.",
            thread_id="thread-convo",
            approval_granted=False,
        )
        assert blocked_send["status"] == "approval_required"
        package = read_execution_package(str(tmp), package_id) or {}
        assert package.get("conversation_id") in {"thread-convo", "thread-phase111"}
        assert len(list(package.get("conversation_history") or [])) >= 2
        assert package.get("last_user_message")
        assert package.get("last_forge_message")
        assert package.get("conversation_stage") in {"lead", "qualified", "negotiating", "closing", "closed", "lost"}


def test_no_auto_send_behavior_preserved():
    from NEXUS.revenue_communication_loop import send_email_safe

    with _local_test_dir() as tmp:
        package_id = _write_package(tmp, "pkg-approval")
        result = send_email_safe(
            project_path=str(tmp),
            package_id=package_id,
            to_email="lead@example.com",
            subject="Sales draft",
            body_text="Proposed next step.",
            thread_id="thread-approval",
            approval_granted=False,
        )
        assert result["status"] == "approval_required"
        assert not result.get("email_message_id")


def test_read_surfaces_include_sales_brain_sections():
    from NEXUS.command_surface import run_command
    from NEXUS.revenue_communication_loop import ingest_email_lead_safe

    with _local_test_dir() as tmp:
        package_id = _write_package(tmp, "pkg-surfaces")
        ingest_email_lead_safe(
            project_path=str(tmp),
            package_id=package_id,
            inbound_email={
                "sender": "jamie@example.com",
                "subject": "Ready for a scoped offer",
                "body": "Interested and ready to review next steps.",
                "thread_id": "thread-surfaces",
                "message_id": "msg-surfaces",
            },
        )
        details = run_command("execution_package_details", project_path=str(tmp), execution_package_id=package_id)
        assert details["status"] == "ok"
        sections = details["payload"]["sections"]
        assert "qualification" in sections
        assert "offer" in sections
        assert "closing" in sections
        assert "conversation" in sections

        queue = run_command("execution_package_queue", project_path=str(tmp), n=10)
        assert queue["status"] == "ok"
        sales_summary = queue["payload"].get("sales_queue_summary") or {}
        assert "leads_needing_qualification" in sales_summary
        assert "deals_in_progress" in sales_summary
        assert "closing_opportunities" in sales_summary
        assert "high_value_leads" in sales_summary


def main():
    tests = [
        test_qualification_logic_consistency,
        test_offer_generation_structure_is_bounded,
        test_objection_detection_correctness,
        test_closing_signal_detection_and_recommendation,
        test_conversation_memory_persists_across_interactions,
        test_no_auto_send_behavior_preserved,
        test_read_surfaces_include_sales_brain_sections,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
