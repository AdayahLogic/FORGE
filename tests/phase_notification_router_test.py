"""
Unified notification router validation tests.

Run:
  python tests/phase_notification_router_test.py
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
    path = base / f"phase_notify_{uuid.uuid4().hex[:8]}"
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


def test_event_normalization_and_priority_bounds():
    from NEXUS.notification_router import normalize_notification_event

    event = normalize_notification_event(
        event_type="approval_required",
        message="Approval needed for outbound email.",
        priority="INVALID",
        payload={"k": "v"},
        event_source="unit_test",
    )
    assert event["event_type"] == "approval_required"
    assert event["event_priority"] == "normal"
    assert event["event_message"] == "Approval needed for outbound email."
    assert event["event_source"] == "unit_test"
    assert isinstance(event["event_payload"], dict)
    assert event["event_id"]


def test_routing_rules_priority_and_event_overrides():
    from NEXUS.notification_router import resolve_notification_channels

    assert resolve_notification_channels("new_lead", "high") == ["telegram"]
    assert resolve_notification_channels("approval_required", "normal") == ["telegram", "pushover"]
    assert resolve_notification_channels("random_event", "info") == ["telegram"]
    assert resolve_notification_channels("random_event", "critical") == ["telegram", "pushover"]


def test_notify_operator_dedupes_and_does_not_spam():
    from NEXUS import notification_bridge
    from NEXUS.notification_router import notify_operator

    sent = {"telegram": 0, "pushover": 0}
    original_tg = notification_bridge.send_telegram_notification_safe
    original_po = notification_bridge.send_pushover_notification_safe

    def _fake_tg(*, event, project_path=None):
        del event, project_path
        sent["telegram"] += 1
        return {"channel": "telegram", "status": "sent", "reason": "ok"}

    def _fake_po(*, event, project_path=None):
        del event, project_path
        sent["pushover"] += 1
        return {"channel": "pushover", "status": "sent", "reason": "ok"}

    with _local_test_dir() as tmp:
        try:
            notification_bridge.send_telegram_notification_safe = _fake_tg
            notification_bridge.send_pushover_notification_safe = _fake_po
            first = notify_operator(
                "approval_required",
                "Approval needed.",
                priority="high",
                project_path=str(tmp),
                dedupe_key="dedupe-1",
            )
            second = notify_operator(
                "approval_required",
                "Approval needed.",
                priority="high",
                project_path=str(tmp),
                dedupe_key="dedupe-1",
            )
            assert first["event_delivery_status"]["overall"] in {"sent", "partial"}
            assert second["event_delivery_status"]["overall"] == "skipped_duplicate"
            assert sent["telegram"] == 1
            assert sent["pushover"] == 1
        finally:
            notification_bridge.send_telegram_notification_safe = original_tg
            notification_bridge.send_pushover_notification_safe = original_po


def test_safe_fallback_when_telegram_unconfigured():
    from NEXUS.notification_bridge import send_telegram_notification_safe

    result = send_telegram_notification_safe(
        event={
            "event_type": "new_lead",
            "event_priority": "normal",
            "event_title": "New Lead",
            "event_message": "Lead discovered.",
            "event_timestamp": "2026-01-01T00:00:00+00:00",
            "event_source": "test",
        },
        project_path=None,
    )
    assert result["channel"] == "telegram"
    assert result["status"] in {"skipped_unconfigured", "sent", "failed"}


def test_activity_feed_and_telegram_commands():
    from NEXUS import notification_bridge
    from NEXUS.notification_router import notify_operator
    from NEXUS.telegram_bridge import handle_telegram_command_safe

    original_tg = notification_bridge.send_telegram_notification_safe
    original_po = notification_bridge.send_pushover_notification_safe

    def _fake_channel(*, event, project_path=None):
        del event, project_path
        return {"status": "sent", "reason": "ok"}

    with _local_test_dir() as tmp:
        try:
            notification_bridge.send_telegram_notification_safe = _fake_channel
            notification_bridge.send_pushover_notification_safe = _fake_channel
            notify_operator("new_lead", "Lead from inbox.", priority="normal", project_path=str(tmp))
            notify_operator("approval_required", "Approval queue item pending.", priority="high", project_path=str(tmp))
            notify_operator("mission_failed", "Mission blocked by guardrail.", priority="critical", project_path=str(tmp))

            activity = handle_telegram_command_safe(command="activity", project_path=str(tmp), limit=5)
            assert activity["status"] == "ok"
            assert "Forge Activity Feed" in activity["response_text"]

            alerts = handle_telegram_command_safe(command="alerts", project_path=str(tmp), limit=5)
            assert alerts["status"] == "ok"
            assert "Forge Alerts" in alerts["response_text"]

            status = handle_telegram_command_safe(command="notifications status", project_path=str(tmp))
            assert status["status"] == "ok"
            assert "Notification Status" in status["response_text"]
        finally:
            notification_bridge.send_telegram_notification_safe = original_tg
            notification_bridge.send_pushover_notification_safe = original_po


def test_revenue_loop_integration_points_emit_events_safely():
    from NEXUS import notification_router
    from NEXUS.execution_package_registry import write_execution_package_safe
    from NEXUS.revenue_communication_loop import ingest_email_lead_safe, send_email_safe

    captured: list[dict] = []
    original_notify = notification_router.notify_operator_safe

    def _fake_notify_operator_safe(*args, **kwargs):
        del args
        captured.append(dict(kwargs))
        return {"event_delivery_status": {"overall": "sent"}}

    with _local_test_dir() as tmp:
        try:
            notification_router.notify_operator_safe = _fake_notify_operator_safe
            package_id = "pkg-notify-int"
            wrote = write_execution_package_safe(
                str(tmp),
                {
                    "package_id": package_id,
                    "project_name": "notifyproj",
                    "project_path": str(tmp),
                    "created_at": "2026-03-27T00:00:00+00:00",
                    "package_status": "review_pending",
                    "review_status": "pending",
                    "requires_human_approval": True,
                    "metadata": {},
                },
            )
            assert bool(wrote) is True

            lead = ingest_email_lead_safe(
                project_path=str(tmp),
                package_id=package_id,
                inbound_email={
                    "sender": "lead@example.com",
                    "subject": "Need a quote",
                    "body": "Please share pricing",
                    "timestamp": "2026-03-27T01:00:00+00:00",
                    "thread_id": "th-a",
                    "message_id": "msg-a",
                },
            )
            assert lead["status"] == "ok"

            blocked = send_email_safe(
                project_path=str(tmp),
                package_id=package_id,
                to_email="lead@example.com",
                subject="Re: Quote",
                body_text="Draft message",
                approval_granted=False,
            )
            assert blocked["status"] == "approval_required"
            assert len(captured) >= 2
            event_types = {str(item.get("event_type")) for item in captured}
            assert "new_lead" in event_types
            assert "approval_required" in event_types
        finally:
            notification_router.notify_operator_safe = original_notify


if __name__ == "__main__":
    tests = [
        ("event normalization and priority bounds", test_event_normalization_and_priority_bounds),
        ("routing rules by priority and event type", test_routing_rules_priority_and_event_overrides),
        ("dedupe avoids duplicate spam", test_notify_operator_dedupes_and_does_not_spam),
        ("telegram missing-config fallback", test_safe_fallback_when_telegram_unconfigured),
        ("activity feed and telegram commands", test_activity_feed_and_telegram_commands),
        ("revenue loop integration emits events", test_revenue_loop_integration_points_emit_events_safely),
    ]
    passed = sum(1 for name, fn in tests if _run(name, fn))
    total = len(tests)
    print(f"\n{passed}/{total} tests passed")
    raise SystemExit(0 if passed == total else 1)
