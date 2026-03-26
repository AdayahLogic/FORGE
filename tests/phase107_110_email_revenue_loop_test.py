"""
Phase 107-110 real-world communication + revenue loop tests.

Run: python tests/phase107_110_email_revenue_loop_test.py
"""

from __future__ import annotations

import os
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
    path = base / f"phase107_{uuid.uuid4().hex[:8]}"
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


def _write_package(project_path: Path, package_id: str = "pkg-phase107") -> str:
    from NEXUS.execution_package_registry import write_execution_package_safe

    payload = {
        "package_id": package_id,
        "project_name": "phase107proj",
        "project_path": str(project_path),
        "created_at": "2026-03-26T00:00:00+00:00",
        "package_status": "review_pending",
        "review_status": "pending",
        "requires_human_approval": True,
        "metadata": {
            "last_outbound_email_at": "2026-03-20T00:00:00+00:00",
            "lead_qualification": {
                "budget_band": "medium",
                "urgency": "high",
                "problem_clarity": "clear",
                "decision_readiness": "ready",
            },
        },
    }
    assert write_execution_package_safe(str(project_path), payload)
    return package_id


def test_email_send_requires_approval_and_never_autosends():
    from NEXUS.execution_package_registry import read_execution_package
    from NEXUS.revenue_communication_loop import send_email_safe

    with _local_test_dir() as tmp:
        package_id = _write_package(tmp)
        result = send_email_safe(
            project_path=str(tmp),
            package_id=package_id,
            to_email="lead@example.com",
            subject="Draft response",
            body_text="Hello from Forge",
            thread_id="thread-1",
            approval_granted=False,
        )
        assert result["status"] == "approval_required"
        assert not result.get("email_message_id")
        package = read_execution_package(str(tmp), package_id)
        assert package is not None
        assert package["email_status"] == "approval_required"
        assert package["email_requires_approval"] is True
        assert package["approval_queue_item_type"] == "email_send_approval"


def test_inbound_email_normalization_and_lead_conversion():
    from NEXUS.execution_package_registry import read_execution_package
    from NEXUS.revenue_communication_loop import ingest_email_lead_safe

    with _local_test_dir() as tmp:
        package_id = _write_package(tmp)
        result = ingest_email_lead_safe(
            project_path=str(tmp),
            package_id=package_id,
            inbound_email={
                "sender": "alex@northwind.example",
                "subject": "Need pricing ASAP",
                "body": "Can you send a scoped pricing direction this week?",
                "timestamp": "2026-03-26T01:00:00+00:00",
                "thread_id": "th-22",
                "message_id": "msg-22",
            },
        )
        assert result["status"] == "ok"
        lead = result["lead"]
        assert lead["lead_source"] == "inbound_email"
        assert lead["lead_temperature"] in {"hot", "warm", "cold"}
        package = read_execution_package(str(tmp), package_id)
        assert package is not None
        assert package["lead_id"]
        assert package["email_thread_id"] == "th-22"
        assert package["email_status"] == "received"


def test_follow_up_scheduling_and_escalation():
    from NEXUS.execution_package_registry import read_execution_package, record_execution_package_revenue_loop_safe
    from NEXUS.revenue_communication_loop import schedule_follow_up_safe

    with _local_test_dir() as tmp:
        package_id = _write_package(tmp)
        scheduled = schedule_follow_up_safe(
            project_path=str(tmp),
            package_id=package_id,
            no_response_hours=1,
            max_attempts=3,
            now_iso="2026-03-26T12:00:00+00:00",
        )
        assert scheduled["status"] == "ok"
        assert scheduled["follow_up"]["follow_up_required"] is True
        assert scheduled["follow_up"]["follow_up_status"] == "scheduled"
        record_execution_package_revenue_loop_safe(
            project_path=str(tmp),
            package_id=package_id,
            updates={"follow_up_attempt_count": 3},
        )
        escalated = schedule_follow_up_safe(
            project_path=str(tmp),
            package_id=package_id,
            no_response_hours=1,
            max_attempts=3,
            now_iso="2026-03-26T12:10:00+00:00",
        )
        assert escalated["escalated"] is True
        package = read_execution_package(str(tmp), package_id)
        assert package is not None
        assert package["follow_up_status"] == "escalated"


def test_notifications_trigger_and_are_retry_safe():
    from NEXUS.revenue_communication_loop import notify_operator_safe
    import NEXUS.revenue_communication_loop as loop

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"status":1,"request":"req-1"}'

    def _fake_urlopen(_req, timeout=0):
        assert timeout <= 4
        return _FakeResponse()

    with _local_test_dir() as tmp:
        previous_token = os.environ.get("PUSHOVER_API_TOKEN")
        previous_user = os.environ.get("PUSHOVER_USER_KEY")
        previous_urlopen = loop.request.urlopen
        try:
            os.environ["PUSHOVER_API_TOKEN"] = "test-token"
            os.environ["PUSHOVER_USER_KEY"] = "test-user"
            loop.request.urlopen = _fake_urlopen
            first = notify_operator_safe(
                project_path=str(tmp),
                notification_type="new_lead_received",
                notification_message="Lead requires response approval.",
                notification_priority="high",
                dedupe_key="notif-1",
            )
            assert first["status"] == "sent"
            second = notify_operator_safe(
                project_path=str(tmp),
                notification_type="new_lead_received",
                notification_message="Lead requires response approval.",
                notification_priority="high",
                dedupe_key="notif-1",
            )
            assert second["status"] == "skipped_duplicate"
        finally:
            loop.request.urlopen = previous_urlopen
            if previous_token is None:
                os.environ.pop("PUSHOVER_API_TOKEN", None)
            else:
                os.environ["PUSHOVER_API_TOKEN"] = previous_token
            if previous_user is None:
                os.environ.pop("PUSHOVER_USER_KEY", None)
            else:
                os.environ["PUSHOVER_USER_KEY"] = previous_user


def test_read_surfaces_include_revenue_loop_updates():
    from NEXUS.command_surface import run_command
    from NEXUS.revenue_communication_loop import ingest_email_lead_safe, schedule_follow_up_safe, send_email_safe

    with _local_test_dir() as tmp:
        package_id = _write_package(tmp)
        ingest_email_lead_safe(
            project_path=str(tmp),
            package_id=package_id,
            inbound_email={
                "sender": "alex@northwind.example",
                "subject": "Automation proposal",
                "body": "We need automation support.",
                "timestamp": "2026-03-26T01:00:00+00:00",
                "thread_id": "thread-surface",
                "message_id": "msg-surface",
            },
        )
        send_email_safe(
            project_path=str(tmp),
            package_id=package_id,
            to_email="alex@northwind.example",
            subject="Draft proposal follow-up",
            body_text="Draft reply",
            thread_id="thread-surface",
            approval_granted=False,
        )
        schedule_follow_up_safe(
            project_path=str(tmp),
            package_id=package_id,
            no_response_hours=1,
            now_iso="2026-03-26T12:00:00+00:00",
        )

        details = run_command("execution_package_details", project_path=str(tmp), execution_package_id=package_id)
        assert details["status"] == "ok"
        sections = details["payload"]["sections"]
        assert "communication" in sections
        assert "lead" in sections
        assert "follow_up" in sections

        queue = run_command("execution_package_queue", project_path=str(tmp), n=10)
        assert queue["status"] == "ok"
        revenue_summary = queue["payload"].get("revenue_loop_queue_summary") or {}
        assert revenue_summary.get("responses_awaiting_approval", 0) >= 1
        assert revenue_summary.get("follow_ups_pending", 0) >= 1


def main():
    tests = [
        test_email_send_requires_approval_and_never_autosends,
        test_inbound_email_normalization_and_lead_conversion,
        test_follow_up_scheduling_and_escalation,
        test_notifications_trigger_and_are_retry_safe,
        test_read_surfaces_include_revenue_loop_updates,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
