"""
Phase 48 execution package hardening and recovery tests.

Run: python tests/phase48_execution_package_hardening_recovery_test.py
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
    path = base / f"phase48_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@contextmanager
def _patched_aegis(result: dict):
    import AEGIS.aegis_core as aegis_core

    original = aegis_core.evaluate_action_safe
    aegis_core.evaluate_action_safe = lambda request=None: result
    try:
        yield
    finally:
        aegis_core.evaluate_action_safe = original


@contextmanager
def _patched_executor(result: dict):
    import NEXUS.execution_package_executor as executor_mod

    original = executor_mod.execute_execution_package_safe
    executor_mod.execute_execution_package_safe = lambda **kwargs: result
    try:
        yield
    finally:
        executor_mod.execute_execution_package_safe = original


@contextmanager
def _patched_openclaw_backend(result):
    import NEXUS.executor_backends as backends_mod

    original = backends_mod.EXECUTOR_BACKENDS["openclaw"]["executor"]
    if callable(result):
        backends_mod.EXECUTOR_BACKENDS["openclaw"]["executor"] = result
    else:
        backends_mod.EXECUTOR_BACKENDS["openclaw"]["executor"] = lambda **kwargs: result
    try:
        yield
    finally:
        backends_mod.EXECUTOR_BACKENDS["openclaw"]["executor"] = original


@contextmanager
def _patched_openclaw_status(status: str):
    import NEXUS.executor_backends.openclaw_executor as openclaw_mod

    original = openclaw_mod.ADAPTER_STATUS
    openclaw_mod.ADAPTER_STATUS = status
    try:
        yield
    finally:
        openclaw_mod.ADAPTER_STATUS = original


def _run(name: str, fn):
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except Exception as e:
        print(f"FAIL: {name} - {e}")
        return False


def _write_package(
    project_path: Path,
    package_id: str,
    *,
    handoff_target: str = "local",
    execution_status: str = "pending",
    retry_policy: dict | None = None,
    execution_id: str = "",
    executor_backend_id: str = "",
) -> str | None:
    from NEXUS.execution_package_registry import write_execution_package_safe

    metadata = {"openclaw_active": executor_backend_id == "openclaw"}
    if executor_backend_id:
        metadata["executor_backend_id"] = executor_backend_id
    package = {
        "package_id": package_id,
        "package_version": "1.0",
        "package_kind": "review_only_execution_envelope",
        "project_name": "phase48proj",
        "project_path": str(project_path),
        "created_at": "2026-03-22T00:00:00Z",
        "package_status": "review_pending",
        "review_status": "pending",
        "sealed": True,
        "seal_reason": "Review-only package.",
        "runtime_target_id": "windows_review_package",
        "runtime_target_name": "windows_review_package",
        "execution_mode": "manual_only",
        "requested_action": "adapter_dispatch_call",
        "requested_by": "workflow",
        "requires_human_approval": True,
        "approval_id_refs": ["appr-1"],
        "aegis_decision": "approval_required",
        "aegis_scope": "runtime_dispatch_only",
        "reason": "Human review required before any activation.",
        "dispatch_plan_summary": {"ready_for_dispatch": True},
        "routing_summary": {"runtime_node": "coder", "tool_name": "cursor_agent"},
        "execution_summary": {"review_only": True, "can_execute": False},
        "command_request": {"summary": "Execute reviewed package.", "task_type": "coder"},
        "candidate_paths": ["src/module.py"],
        "expected_outputs": ["execution package"],
        "review_checklist": ["Confirm package remains sealed."],
        "rollback_notes": ["Use rollback guidance if execution fails."],
        "runtime_artifacts": [],
        "metadata": metadata,
        "decision_status": "approved",
        "decision_timestamp": "2026-03-22T00:01:00Z",
        "decision_actor": "operator_a",
        "decision_notes": "Approved.",
        "decision_id": str(uuid.uuid4()),
        "eligibility_status": "eligible",
        "eligibility_timestamp": "2026-03-22T00:02:00Z",
        "eligibility_reason": {"code": "eligible", "message": "Eligible."},
        "eligibility_checked_by": "operator_b",
        "eligibility_check_id": str(uuid.uuid4()),
        "release_status": "released",
        "release_timestamp": "2026-03-22T00:03:00Z",
        "release_actor": "operator_r",
        "release_notes": "Released.",
        "release_id": str(uuid.uuid4()),
        "release_reason": {"code": "released", "message": "Released."},
        "release_version": "v1",
        "handoff_status": "authorized",
        "handoff_timestamp": "2026-03-22T00:04:00Z",
        "handoff_actor": "operator_h",
        "handoff_notes": "Authorized.",
        "handoff_id": str(uuid.uuid4()),
        "handoff_reason": {"code": "authorized", "message": "Authorized."},
        "handoff_version": "v1",
        "handoff_executor_target_id": handoff_target,
        "handoff_executor_target_name": handoff_target.title().replace("_", " "),
        "handoff_aegis_result": {},
        "execution_status": execution_status,
        "execution_id": execution_id,
        "retry_policy": retry_policy or {},
    }
    return write_execution_package_safe(str(project_path), package)


def test_hardening_defaults_and_idempotency_key_present():
    from NEXUS.execution_package_registry import normalize_execution_package

    normalized = normalize_execution_package(
        {
            "package_id": "pkg-default",
            "runtime_target_id": "local",
            "command_request": {"summary": "Execute reviewed package.", "task_type": "coder"},
        }
    )
    assert normalized["retry_policy"]["policy_status"] == "default_no_retry"
    assert normalized["retry_policy"]["retry_authorized"] is False
    assert normalized["idempotency"]["idempotency_key"]
    assert normalized["idempotency"]["idempotency_status"] == "active"
    assert normalized["failure_summary"]["failure_class"] == ""
    assert normalized["recovery_summary"]["recovery_status"] == "not_needed"
    assert normalized["rollback_repair"]["rollback_repair_status"] == "not_needed"
    assert normalized["integrity_verification"]["integrity_status"] == "not_verified"


def test_success_sets_integrity_verified_and_summary_safe_dashboard_counts():
    from AEGIS.aegis_contract import build_aegis_result
    from NEXUS.command_surface import run_command
    from NEXUS.registry import PROJECTS
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-success")
        aegis = build_aegis_result(
            aegis_decision="allow",
            aegis_reason="Allowed.",
            action_mode="execution",
            project_name="phase48proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="allow",
        )
        log_ref = str(tmp / "state" / "execution_runs" / "ok.log")
        exec_result = {
            "execution_status": "succeeded",
            "execution_reason": {"code": "succeeded", "message": "Executed."},
            "execution_receipt": {
                "result_status": "succeeded",
                "exit_code": 0,
                "log_ref": log_ref,
                "files_touched_count": 0,
                "artifacts_written_count": 1,
                "failure_class": "",
            },
            "rollback_status": "not_needed",
            "rollback_timestamp": "",
            "rollback_reason": {"code": "", "message": ""},
            "failure_summary": {"failure_stage": "", "failure_class": "", "failure_severity": "", "last_failure_at": ""},
            "rollback_repair": {"rollback_repair_status": "not_needed", "rollback_repair_timestamp": "", "rollback_repair_reason": {"code": "", "message": ""}},
            "runtime_artifact": {"artifact_type": "execution_log", "log_ref": log_ref},
            "execution_finished_at": "2026-03-22T00:05:00Z",
        }
        with _patched_aegis(aegis), _patched_executor(exec_result):
            result = run_command("execution_package_execute_request", project_path=str(tmp), execution_package_id="pkg-success", execution_actor="operator_x")
        execution = result["payload"]["execution"]
        assert execution["integrity_verification"]["integrity_status"] == "verified"
        assert execution["integrity_verification"]["integrity_summary"]["log_ref_present"] is True
        assert execution["failure_summary"]["failure_class"] == ""
        assert execution["recovery_summary"]["recovery_status"] == "not_needed"
        assert execution["idempotency"]["last_success_execution_id"] == execution["execution_id"]
        project_key = f"phase48_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp)}
        try:
            dash = build_registry_dashboard_summary()
            summary = dash.get("execution_package_execution_summary") or {}
            assert summary.get("integrity_verified_count_total", 0) >= 1
            assert summary.get("integrity_verified_count_by_project", {}).get(project_key) == 1
            rows = (dash.get("execution_package_review_summary") or {}).get("packages_by_project", {}).get(project_key) or []
            assert rows
            receipt = rows[0].get("execution_receipt") or {}
            assert "log_ref" not in receipt
            assert rows[0].get("integrity_verification", {}).get("integrity_status") == "verified"
        finally:
            PROJECTS.pop(project_key, None)


def test_duplicate_success_is_blocked_without_retry_authorization():
    from AEGIS.aegis_contract import build_aegis_result
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-dup", execution_status="succeeded", execution_id="exec-prev")
        aegis = build_aegis_result(
            aegis_decision="allow",
            aegis_reason="Allowed.",
            action_mode="execution",
            project_name="phase48proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="allow",
        )
        with _patched_aegis(aegis):
            result = run_command("execution_package_execute_request", project_path=str(tmp), execution_package_id="pkg-dup", execution_actor="operator_x")
        execution = result["payload"]["execution"]
        assert execution["execution_status"] == "blocked"
        assert execution["execution_reason"]["code"] == "duplicate_success_blocked"
        assert execution["failure_summary"]["failure_class"] == "duplicate_success_block"
        assert execution["idempotency"]["duplicate_success_blocked"] is True
        assert execution["recovery_summary"]["recovery_status"] == "retry_blocked"


def test_explicit_retry_policy_allows_future_retry_without_new_command():
    from AEGIS.aegis_contract import build_aegis_result
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_package(
            tmp,
            "pkg-retry",
            execution_status="succeeded",
            execution_id="exec-prev",
            retry_policy={
                "policy_status": "retry_authorized",
                "max_retry_attempts": 2,
                "retry_count": 0,
                "retry_authorized": True,
                "retry_authorization_id": "retry-1",
                "retry_reason": {"code": "operator_authorized", "message": "Authorized."},
            },
        )
        aegis = build_aegis_result(
            aegis_decision="allow",
            aegis_reason="Allowed.",
            action_mode="execution",
            project_name="phase48proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="allow",
        )
        log_ref = str(tmp / "state" / "execution_runs" / "retry.log")
        exec_result = {
            "execution_status": "succeeded",
            "execution_reason": {"code": "succeeded", "message": "Executed again."},
            "execution_receipt": {
                "result_status": "succeeded",
                "exit_code": 0,
                "log_ref": log_ref,
                "files_touched_count": 0,
                "artifacts_written_count": 1,
                "failure_class": "",
            },
            "rollback_status": "not_needed",
            "rollback_timestamp": "",
            "rollback_reason": {"code": "", "message": ""},
            "failure_summary": {"failure_stage": "", "failure_class": "", "failure_severity": "", "last_failure_at": ""},
            "rollback_repair": {"rollback_repair_status": "not_needed", "rollback_repair_timestamp": "", "rollback_repair_reason": {"code": "", "message": ""}},
            "runtime_artifact": {"artifact_type": "execution_log", "log_ref": log_ref},
            "execution_finished_at": "2026-03-22T00:06:00Z",
        }
        with _patched_aegis(aegis), _patched_executor(exec_result):
            result = run_command("execution_package_execute_request", project_path=str(tmp), execution_package_id="pkg-retry", execution_actor="operator_x")
        execution = result["payload"]["execution"]
        assert execution["execution_status"] == "succeeded"
        assert execution["retry_policy"]["retry_count"] == 1
        assert execution["integrity_verification"]["integrity_status"] == "verified"


def test_failure_and_rollback_repair_states_are_classified():
    from AEGIS.aegis_contract import build_aegis_result
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-fail")
        aegis = build_aegis_result(
            aegis_decision="approval_required",
            aegis_reason="Human controlled.",
            action_mode="execution",
            project_name="phase48proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="allow",
        )
        exec_result = {
            "execution_status": "failed",
            "execution_reason": {"code": "runtime_execution_failed", "message": "Runtime failed."},
            "execution_receipt": {
                "result_status": "failed",
                "exit_code": 2,
                "log_ref": str(tmp / "state" / "execution_runs" / "fail.log"),
                "files_touched_count": 1,
                "artifacts_written_count": 1,
                "failure_class": "rollback_failure",
                "rollback_summary": {"used_notes": True, "notes_count": 1},
            },
            "rollback_status": "failed",
            "rollback_timestamp": "2026-03-22T00:07:00Z",
            "rollback_reason": {"code": "rollback_failed", "message": "Rollback failed."},
            "failure_summary": {
                "failure_stage": "rollback",
                "failure_class": "rollback_failure",
                "failure_severity": "high",
                "last_failure_at": "2026-03-22T00:07:00Z",
            },
            "rollback_repair": {
                "rollback_repair_status": "pending",
                "rollback_repair_timestamp": "2026-03-22T00:07:00Z",
                "rollback_repair_reason": {"code": "rollback_repair_required", "message": "Manual repair required."},
            },
            "runtime_artifact": {"artifact_type": "execution_log", "log_ref": str(tmp / "state" / "execution_runs" / "fail.log")},
            "execution_finished_at": "2026-03-22T00:07:00Z",
        }
        with _patched_aegis(aegis), _patched_executor(exec_result):
            result = run_command("execution_package_execute_request", project_path=str(tmp), execution_package_id="pkg-fail", execution_actor="operator_x")
        execution = result["payload"]["execution"]
        assert execution["failure_summary"]["failure_stage"] == "rollback"
        assert execution["failure_summary"]["failure_class"] == "rollback_failure"
        assert execution["rollback_repair"]["rollback_repair_status"] == "pending"
        assert execution["recovery_summary"]["recovery_status"] == "repair_required"


def test_openclaw_adapter_failure_and_malformed_results_flow_into_existing_failure_classes():
    from AEGIS.aegis_contract import build_aegis_result
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        aegis = build_aegis_result(
            aegis_decision="allow",
            aegis_reason="Allowed.",
            action_mode="execution",
            project_name="phase48proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="allow",
        )

        _write_package(tmp, "pkg-openclaw-fail", handoff_target="openclaw", executor_backend_id="openclaw")
        backend_failure = {
            "status": "error",
            "result_status": "failed",
            "exit_code": 5,
            "stdout_summary": "",
            "stderr_summary": "adapter execution failed",
            "log_ref": str(tmp / "state" / "execution_runs" / "openclaw_fail.log"),
            "files_touched_count": 1,
            "artifacts_written_count": 1,
            "failure_class": "runtime_execution_failure",
            "runtime_artifact": {"artifact_type": "execution_log", "log_ref": str(tmp / "state" / "execution_runs" / "openclaw_fail.log")},
            "rollback_summary": {},
            "adapter_status": "active",
            "backend_id": "openclaw",
        }
        with _patched_aegis(aegis), _patched_openclaw_backend(backend_failure):
            failed = run_command("execution_package_execute_request", project_path=str(tmp), execution_package_id="pkg-openclaw-fail", execution_actor="operator_x")
        execution = failed["payload"]["execution"]
        assert execution["execution_status"] == "failed"
        assert execution["execution_executor_backend_id"] == "openclaw"
        assert execution["failure_summary"]["failure_class"] == "runtime_execution_failure"
        assert execution["failure_summary"]["failure_stage"] == "execution"
        assert execution["recovery_summary"]["recovery_status"] == "retry_blocked"

        _write_package(tmp, "pkg-openclaw-malformed", handoff_target="openclaw", executor_backend_id="openclaw")
        with _patched_aegis(aegis), _patched_openclaw_backend("not-a-dict"):
            malformed = run_command("execution_package_execute_request", project_path=str(tmp), execution_package_id="pkg-openclaw-malformed", execution_actor="operator_x")
        execution = malformed["payload"]["execution"]
        assert execution["execution_status"] == "failed"
        assert execution["execution_receipt"]["failure_class"] == "runtime_start_failure"
        assert execution["failure_summary"]["failure_class"] == "runtime_start_failure"
        assert execution["recovery_summary"]["recovery_status"] == "retry_blocked"


def test_openclaw_backend_inactive_fails_closed_without_fallback():
    from AEGIS.aegis_contract import build_aegis_result
    from NEXUS.command_surface import run_command

    called = {"value": False}

    def _backend(**kwargs):
        called["value"] = True
        return {"status": "ok", "result_status": "succeeded", "adapter_status": "active", "backend_id": "openclaw"}

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-openclaw-inactive", handoff_target="openclaw", executor_backend_id="openclaw")
        aegis = build_aegis_result(
            aegis_decision="allow",
            aegis_reason="Allowed.",
            action_mode="execution",
            project_name="phase48proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="allow",
        )
        with _patched_aegis(aegis), _patched_openclaw_backend(_backend), _patched_openclaw_status("inactive"):
            result = run_command("execution_package_execute_request", project_path=str(tmp), execution_package_id="pkg-openclaw-inactive", execution_actor="operator_x")
        execution = result["payload"]["execution"]
        assert execution["execution_status"] == "failed"
        assert execution["execution_receipt"]["failure_class"] == "runtime_start_failure"
        assert execution["failure_summary"]["failure_class"] == "runtime_start_failure"
        assert execution["execution_executor_backend_id"] == "openclaw"
        assert execution["execution_executor_target_id"] == "openclaw"
        assert called["value"] is False


def test_integrity_checker_sees_phase8_shape():
    from NEXUS.integrity_checker import check_execution_package_hardening_shape, check_execution_package_hardening_summary_shape

    record = {
        "retry_policy": {},
        "idempotency": {},
        "failure_summary": {},
        "recovery_summary": {},
        "rollback_repair": {},
        "integrity_verification": {},
    }
    summary = {
        "duplicate_success_blocked_count_total": 0,
        "retry_ready_count_total": 0,
        "repair_required_count_total": 0,
        "rollback_repair_failed_count_total": 0,
        "integrity_verified_count_total": 0,
        "integrity_issues_count_total": 0,
    }
    assert check_execution_package_hardening_shape(record)["valid"] is True
    assert check_execution_package_hardening_summary_shape(summary)["valid"] is True


def main():
    tests = [
        test_hardening_defaults_and_idempotency_key_present,
        test_success_sets_integrity_verified_and_summary_safe_dashboard_counts,
        test_duplicate_success_is_blocked_without_retry_authorization,
        test_explicit_retry_policy_allows_future_retry_without_new_command,
        test_failure_and_rollback_repair_states_are_classified,
        test_openclaw_adapter_failure_and_malformed_results_flow_into_existing_failure_classes,
        test_openclaw_backend_inactive_fails_closed_without_fallback,
        test_integrity_checker_sees_phase8_shape,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
