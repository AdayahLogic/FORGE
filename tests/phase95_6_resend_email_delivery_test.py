"""
Phase 95.6 real email delivery via Resend tests.

Run: python tests/phase95_6_resend_email_delivery_test.py
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
    path = base / f"phase95_6_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@contextmanager
def _temp_env(updates: dict[str, str | None]):
    original: dict[str, str | None] = {}
    for key in updates:
        original[key] = os.environ.get(key)
    try:
        for key, value in updates.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _run(name: str, fn):
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except Exception as exc:
        print(f"FAIL: {name} - {exc}")
        return False


def _write_package(project_path: Path, package: dict) -> str:
    from NEXUS.execution_package_registry import write_execution_package_safe

    package_id = str(package.get("package_id") or f"pkg-{uuid.uuid4().hex[:10]}")
    payload = {
        "package_id": package_id,
        "project_name": "phase95proj",
        "project_path": str(project_path),
        "run_id": "run-phase95",
        "package_status": "review_pending",
        "review_status": "pending",
        "decision_status": "approved",
        "release_status": "released",
        "execution_status": "pending",
        "metadata": {
            "governance_status": "approved",
            "governance_routing_outcome": "continue",
            "enforcement_status": "continue",
        },
        "communication_channel": "email",
        "recipient_email": "buyer@example.com",
        "recipient_name": "Buyer",
        "draft_message_subject": "Forge proposal follow-up",
        "draft_message_body": "Thanks for reviewing the package. Confirm next step?",
        "communication_approval_status": "approved",
        "communication_send_eligible": True,
        **package,
    }
    assert write_execution_package_safe(str(project_path), payload)
    return package_id


def test_successful_send_after_approval_via_explicit_command():
    from NEXUS.command_surface import run_command
    import NEXUS.resend_provider as resend_provider

    with _local_test_dir() as tmp:
        package_id = _write_package(tmp, {})
        original_send = resend_provider.send_email_via_resend
        resend_provider.send_email_via_resend = lambda **_: {
            "status": "ok",
            "provider": "resend",
            "provider_message_id": "re_msg_123",
            "error_code": "",
            "error_message": "",
        }
        try:
            with _temp_env({"RESEND_API_KEY": "unit-test-key", "RESEND_FROM_EMAIL": "forge@example.com"}):
                result = run_command(
                    "execution_package_email_send",
                    project_path=str(tmp),
                    execution_package_id=package_id,
                    send_actor="operator_phase95",
                )
            assert result["status"] == "ok"
            comm = result["payload"]["communication"]
            assert comm["communication_delivery_status"] == "delivered"
            assert comm["communication_provider_message_id"] == "re_msg_123"
            assert comm["communication_follow_up_ready"] is True
        finally:
            resend_provider.send_email_via_resend = original_send


def test_rejected_when_approval_missing():
    from NEXUS.execution_package_registry import record_execution_package_email_delivery_safe

    with _local_test_dir() as tmp:
        package_id = _write_package(tmp, {"communication_approval_status": "pending"})
        result = record_execution_package_email_delivery_safe(
            project_path=str(tmp),
            package_id=package_id,
            send_actor="operator_phase95",
            send_provider_email_fn=lambda **_: {"status": "ok", "provider_message_id": "unused"},
        )
        assert result["status"] == "blocked"
        pkg = result["package"] or {}
        assert pkg["communication_delivery_status"] == "failed"
        assert pkg["communication_delivery_last_event"] == "blocked"
        assert pkg["communication_delivery_error_code"] == "approval_not_approved"


def test_rejected_when_provider_config_missing():
    from NEXUS.execution_package_registry import record_execution_package_email_delivery_safe

    with _local_test_dir() as tmp:
        package_id = _write_package(tmp, {})
        with _temp_env({"RESEND_API_KEY": None, "RESEND_FROM_EMAIL": None}):
            result = record_execution_package_email_delivery_safe(
                project_path=str(tmp),
                package_id=package_id,
                send_actor="operator_phase95",
            )
        assert result["status"] == "failed"
        pkg = result["package"] or {}
        assert pkg["communication_delivery_status"] == "provider_not_configured"
        assert pkg["communication_delivery_error_code"] == "provider_not_configured"


def test_rejected_when_recipient_missing():
    from NEXUS.execution_package_registry import record_execution_package_email_delivery_safe

    with _local_test_dir() as tmp:
        package_id = _write_package(tmp, {"recipient_email": ""})
        result = record_execution_package_email_delivery_safe(
            project_path=str(tmp),
            package_id=package_id,
            send_actor="operator_phase95",
            send_provider_email_fn=lambda **_: {"status": "ok", "provider_message_id": "unused"},
        )
        assert result["status"] == "blocked"
        pkg = result["package"] or {}
        assert pkg["communication_delivery_status"] == "failed"
        assert pkg["communication_delivery_error_code"] == "recipient_email_missing"


def test_provider_failure_is_persisted_auditably():
    from NEXUS.execution_package_registry import record_execution_package_email_delivery_safe

    with _local_test_dir() as tmp:
        package_id = _write_package(tmp, {})
        result = record_execution_package_email_delivery_safe(
            project_path=str(tmp),
            package_id=package_id,
            send_actor="operator_phase95",
            send_provider_email_fn=lambda **_: {
                "status": "rejected",
                "provider_message_id": "",
                "error_code": "http_422",
                "error_message": "Domain not verified.",
            },
        )
        assert result["status"] == "failed"
        pkg = result["package"] or {}
        assert pkg["communication_delivery_status"] == "rejected_by_provider"
        assert pkg["communication_delivery_last_event"] == "rejected_by_provider"
        assert pkg["communication_delivery_error_code"] == "http_422"
        assert pkg["communication_follow_up_ready"] is False


def test_no_auto_send_behavior_until_explicit_command():
    from NEXUS.execution_package_registry import read_execution_package

    with _local_test_dir() as tmp:
        package_id = _write_package(tmp, {})
        package = read_execution_package(str(tmp), package_id) or {}
        assert package["communication_delivery_status"] == "not_attempted"
        assert package["communication_delivery_attempted_at"] == ""
        assert package["communication_provider_message_id"] == ""
        assert package["communication_follow_up_ready"] is False


def test_backward_compatibility_defaults_for_existing_packages():
    from NEXUS.execution_package_registry import normalize_execution_package

    normalized = normalize_execution_package(
        {
            "package_id": "pkg-phase95-defaults",
            "project_name": "phase95proj",
            "project_path": "C:/phase95",
            "pipeline_stage": "qualified",
        }
    )
    assert normalized["pipeline_stage"] == "qualified"
    assert normalized["communication_channel"] == ""
    assert normalized["communication_approval_status"] == "pending"
    assert normalized["communication_send_eligible"] is False
    assert normalized["communication_delivery_status"] == "not_attempted"
    assert normalized["communication_provider"] == "resend"


def main():
    tests = [
        test_successful_send_after_approval_via_explicit_command,
        test_rejected_when_approval_missing,
        test_rejected_when_provider_config_missing,
        test_rejected_when_recipient_missing,
        test_provider_failure_is_persisted_auditably,
        test_no_auto_send_behavior_until_explicit_command,
        test_backward_compatibility_defaults_for_existing_packages,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
