"""
Phase 49 execution package evaluation tests.

Run: python tests/phase49_execution_package_evaluation_test.py
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
    path = base / f"phase49_{uuid.uuid4().hex[:8]}"
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
    except Exception as e:
        print(f"FAIL: {name} - {e}")
        return False


def _base_package(project_path: Path, package_id: str, **overrides):
    package = {
        "package_id": package_id,
        "package_version": "1.0",
        "package_kind": "review_only_execution_envelope",
        "project_name": "phase49proj",
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
        "runtime_artifacts": [{"artifact_type": "execution_log", "log_ref": "state/execution_runs/run.log"}],
        "metadata": {"openclaw_active": False},
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
        "handoff_executor_target_id": "local",
        "handoff_executor_target_name": "Local",
        "handoff_aegis_result": {},
        "execution_status": "succeeded",
        "execution_timestamp": "2026-03-22T00:05:00Z",
        "execution_actor": "operator_x",
        "execution_id": str(uuid.uuid4()),
        "execution_reason": {"code": "succeeded", "message": "Executed."},
        "execution_receipt": {
            "result_status": "succeeded",
            "exit_code": 0,
            "log_ref": str(project_path / "state" / "execution_runs" / "run.log"),
            "files_touched_count": 1,
            "artifacts_written_count": 1,
            "failure_class": "",
        },
        "execution_version": "v1",
        "execution_executor_target_id": "local",
        "execution_executor_target_name": "Local",
        "execution_executor_backend_id": "",
        "execution_aegis_result": {},
        "execution_started_at": "2026-03-22T00:04:30Z",
        "execution_finished_at": "2026-03-22T00:05:00Z",
        "rollback_status": "not_needed",
        "rollback_timestamp": "",
        "rollback_reason": {"code": "", "message": ""},
        "retry_policy": {"policy_status": "default_no_retry", "retry_authorized": False},
        "idempotency": {"idempotency_status": "active", "duplicate_success_blocked": False},
        "failure_summary": {"failure_stage": "", "failure_class": "", "failure_severity": "", "last_failure_at": ""},
        "recovery_summary": {"recovery_status": "not_needed", "recovery_reason": {"code": "", "message": ""}, "retry_permitted": False, "repair_required": False},
        "rollback_repair": {"rollback_repair_status": "not_needed", "rollback_repair_timestamp": "", "rollback_repair_reason": {"code": "", "message": ""}},
        "integrity_verification": {"integrity_status": "verified", "integrity_summary": {"log_ref_present": True}, "integrity_checked_at": "2026-03-22T00:05:00Z"},
    }
    package.update(overrides)
    return package


def _write_package(project_path: Path, package_id: str, **overrides):
    from NEXUS.execution_package_registry import write_execution_package_safe

    package = _base_package(project_path, package_id, **overrides)
    written = write_execution_package_safe(str(project_path), package)
    assert written
    return written


def test_normalization_adds_default_evaluation_fields_and_preserves_old_packages():
    from NEXUS.execution_package_registry import normalize_execution_package, read_execution_package, write_execution_package_safe

    normalized = normalize_execution_package({"package_id": "pkg-default", "runtime_target_id": "local"})
    assert normalized["evaluation_status"] == "pending"
    assert normalized["evaluation_timestamp"] == ""
    assert normalized["evaluation_actor"] == ""
    assert normalized["evaluation_id"] == ""
    assert normalized["evaluation_version"] == "v1"
    assert normalized["evaluation_reason"] == {"code": "", "message": ""}
    assert normalized["evaluation_basis"]["source_execution_status"] == ""
    assert normalized["evaluation_summary"]["execution_quality_score"] == 0

    with _local_test_dir() as tmp:
        old_package = {
            "package_id": "pkg-old",
            "project_name": "phase49proj",
            "project_path": str(tmp),
            "runtime_target_id": "local",
        }
        assert write_execution_package_safe(str(tmp), old_package)
        loaded = read_execution_package(str(tmp), "pkg-old")
        assert loaded
        assert loaded["evaluation_status"] == "pending"
        assert loaded["evaluation_summary"]["failure_risk_score"] == 0


def test_execution_package_evaluate_persists_fields_to_package_and_journal():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import read_execution_package, read_execution_package_journal_tail

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-eval")
        result = run_command("execution_package_evaluate", project_path=str(tmp), execution_package_id="pkg-eval", evaluation_actor="abacus_operator")
        assert result["status"] == "ok"
        evaluation = result["payload"]["evaluation"]
        assert evaluation["evaluation_status"] == "completed"
        assert evaluation["evaluation_actor"] == "abacus_operator"
        assert evaluation["evaluation_reason"]["code"] == "completed"
        assert evaluation["evaluation_summary"]["execution_quality_score"] >= 90
        assert evaluation["evaluation_summary"]["integrity_band"] == "excellent"

        package = read_execution_package(str(tmp), "pkg-eval")
        assert package
        assert package["evaluation_status"] == "completed"
        assert package["evaluation_actor"] == "abacus_operator"
        assert package["evaluation_id"]
        journal = read_execution_package_journal_tail(str(tmp), n=5)
        assert journal
        latest = journal[-1]
        assert latest["evaluation_status"] == "completed"
        assert latest["evaluation_summary"]["failure_risk_band"] == "low"


def test_evaluation_uses_package_local_fields_only():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_package(
            tmp,
            "pkg-local-only",
            execution_status="failed",
            rollback_status="failed",
            failure_summary={
                "failure_stage": "rollback",
                "failure_class": "rollback_failure",
                "failure_severity": "high",
                "last_failure_at": "2026-03-22T00:07:00Z",
            },
            recovery_summary={
                "recovery_status": "repair_required",
                "recovery_reason": {"code": "rollback_repair_required", "message": "Repair required."},
                "retry_permitted": False,
                "repair_required": True,
            },
            rollback_repair={
                "rollback_repair_status": "pending",
                "rollback_repair_timestamp": "2026-03-22T00:07:00Z",
                "rollback_repair_reason": {"code": "rollback_repair_required", "message": "Manual repair required."},
            },
            integrity_verification={
                "integrity_status": "verification_failed",
                "integrity_summary": {"log_ref_present": False},
                "integrity_checked_at": "2026-03-22T00:07:00Z",
            },
        )
        result = run_command("execution_package_evaluate", project_path=str(tmp), execution_package_id="pkg-local-only", evaluation_actor="abacus_operator")
        evaluation = result["payload"]["evaluation"]
        basis = evaluation["evaluation_basis"]
        assert basis["source_execution_status"] == "failed"
        assert basis["source_failure_class"] == "rollback_failure"
        assert basis["source_integrity_status"] == "verification_failed"
        assert evaluation["evaluation_reason"]["code"] == "integrity_failed"
        assert evaluation["evaluation_summary"]["failure_risk_band"] in ("high", "critical")
        assert evaluation["evaluation_summary"]["rollback_quality_band"] == "critical"


def test_preterminal_execution_state_returns_blocked_safely():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-pending", execution_status="pending", rollback_status="not_needed")
        result = run_command("execution_package_evaluate", project_path=str(tmp), execution_package_id="pkg-pending", evaluation_actor="abacus_operator")
        assert result["status"] == "ok"
        evaluation = result["payload"]["evaluation"]
        assert evaluation["evaluation_status"] == "blocked"
        assert evaluation["evaluation_reason"]["code"] == "execution_not_complete"
        assert evaluation["evaluation_summary"]["execution_quality_score"] == 0


def test_execution_package_evaluation_status_returns_stored_values_only():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import write_execution_package_safe

    with _local_test_dir() as tmp:
        package = _base_package(
            tmp,
            "pkg-status",
            evaluation_status="completed",
            evaluation_timestamp="2026-03-22T01:00:00Z",
            evaluation_actor="saved_actor",
            evaluation_id=str(uuid.uuid4()),
            evaluation_version="v1",
            evaluation_reason={"code": "completed", "message": "Stored value."},
            evaluation_basis={
                "source_execution_status": "succeeded",
                "source_rollback_status": "not_needed",
                "source_integrity_status": "verified",
                "source_recovery_status": "not_needed",
                "source_failure_class": "",
                "source_failure_stage": "",
            },
            evaluation_summary={
                "execution_quality_score": 77,
                "integrity_score": 66,
                "rollback_quality": 55,
                "failure_risk_score": 22,
                "execution_quality_band": "strong",
                "integrity_band": "strong",
                "rollback_quality_band": "mixed",
                "failure_risk_band": "guarded",
                "evaluator_summary": "Stored summary only.",
            },
        )
        assert write_execution_package_safe(str(tmp), package)
        result = run_command("execution_package_evaluation_status", project_path=str(tmp), execution_package_id="pkg-status")
        assert result["status"] == "ok"
        evaluation = result["payload"]["evaluation"]
        assert evaluation["evaluation_actor"] == "saved_actor"
        assert evaluation["evaluation_summary"]["execution_quality_score"] == 77
        assert evaluation["evaluation_summary"]["evaluator_summary"] == "Stored summary only."


def test_dashboard_includes_summary_only_evaluation_counts_and_bands():
    from NEXUS.command_surface import run_command
    from NEXUS.registry import PROJECTS
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-dashboard")
        run_command("execution_package_evaluate", project_path=str(tmp), execution_package_id="pkg-dashboard", evaluation_actor="abacus_operator")
        project_key = f"phase49_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp)}
        try:
            dash = build_registry_dashboard_summary()
            summary = dash.get("execution_package_evaluation_summary") or {}
            assert summary.get("completed_count_total", 0) >= 1
            assert summary.get("evaluation_counts_by_project", {}).get(project_key, {}).get("completed") == 1
            assert summary.get("latest_evaluation_status_by_project", {}).get(project_key) == "completed"
            assert "packages_by_project" not in summary
            assert "log_ref" not in str(summary)
            assert summary.get("execution_quality_band_count_total", {}).get("excellent", 0) >= 1
        finally:
            PROJECTS.pop(project_key, None)


def test_integrity_checker_validates_evaluation_shapes():
    from NEXUS.command_surface import run_command
    from NEXUS.integrity_checker import (
        check_execution_package_evaluation_shape,
        check_execution_package_evaluation_summary_shape,
        run_integrity_check_safe,
    )
    from NEXUS.registry import PROJECTS
    from NEXUS.registry_dashboard import build_registry_dashboard_summary
    from NEXUS.execution_package_registry import read_execution_package

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-integrity")
        run_command("execution_package_evaluate", project_path=str(tmp), execution_package_id="pkg-integrity", evaluation_actor="abacus_operator")
        pkg = read_execution_package(str(tmp), "pkg-integrity")
        assert pkg
        assert check_execution_package_evaluation_shape(pkg)["valid"] is True
        project_key = f"phase49_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp)}
        try:
            dash = build_registry_dashboard_summary()
            summary = dash.get("execution_package_evaluation_summary") or {}
            assert check_execution_package_evaluation_summary_shape(summary)["valid"] is True
            integrity = run_integrity_check_safe()
            assert integrity["all_valid"] is True
        finally:
            PROJECTS.pop(project_key, None)


def test_regression_existing_execution_commands_and_dispatch_guards_unchanged():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-regression")
        execute_status = run_command("execution_package_execute_status", project_path=str(tmp), execution_package_id="pkg-regression")
        assert execute_status["status"] == "ok"
        assert execute_status["payload"]["execution"]["execution_status"] == "succeeded"
        evaluate_result = run_command("execution_package_evaluate", project_path=str(tmp), execution_package_id="pkg-regression", evaluation_actor="abacus_operator")
        assert evaluate_result["status"] == "ok"
        details = run_command("execution_package_details", project_path=str(tmp), execution_package_id="pkg-regression")
        assert details["status"] == "ok"
        assert details["payload"]["review_header"]["execution_status"] == "succeeded"
        assert details["payload"]["review_header"]["evaluation_status"] == "completed"


def main():
    tests = [
        test_normalization_adds_default_evaluation_fields_and_preserves_old_packages,
        test_execution_package_evaluate_persists_fields_to_package_and_journal,
        test_evaluation_uses_package_local_fields_only,
        test_preterminal_execution_state_returns_blocked_safely,
        test_execution_package_evaluation_status_returns_stored_values_only,
        test_dashboard_includes_summary_only_evaluation_counts_and_bands,
        test_integrity_checker_validates_evaluation_shapes,
        test_regression_existing_execution_commands_and_dispatch_guards_unchanged,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
