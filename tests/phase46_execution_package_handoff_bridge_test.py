"""
Phase 46 execution package handoff bridge tests.

Run: python tests/phase46_execution_package_handoff_bridge_test.py
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
    path = base / f"phase46_{uuid.uuid4().hex[:8]}"
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
    sealed: bool = True,
    decision_status: str = "approved",
    eligibility_status: str = "eligible",
    release_status: str = "released",
    execution_summary: dict | None = None,
    runtime_artifacts: list | None = None,
) -> str | None:
    from NEXUS.execution_package_registry import write_execution_package_safe

    package = {
        "package_id": package_id,
        "package_version": "1.0",
        "package_kind": "review_only_execution_envelope",
        "project_name": "phase46proj",
        "project_path": str(project_path),
        "created_at": "2026-03-22T00:00:00Z",
        "package_status": "review_pending",
        "review_status": "pending",
        "sealed": sealed,
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
        "execution_summary": execution_summary if execution_summary is not None else {"review_only": True, "can_execute": False},
        "command_request": {"summary": "Inspect package contents.", "task_type": "coder"},
        "candidate_paths": ["src/module.py"],
        "expected_outputs": ["execution package"],
        "review_checklist": ["Confirm package remains sealed."],
        "rollback_notes": ["Discard if incorrect."],
        "runtime_artifacts": runtime_artifacts if runtime_artifacts is not None else [],
        "metadata": {"openclaw_active": False},
        "decision_status": decision_status,
        "decision_timestamp": "2026-03-22T00:01:00Z" if decision_status != "pending" else "",
        "decision_actor": "operator_a" if decision_status != "pending" else "",
        "decision_notes": "Decision made." if decision_status != "pending" else "",
        "decision_id": str(uuid.uuid4()) if decision_status != "pending" else "",
        "eligibility_status": eligibility_status,
        "eligibility_timestamp": "2026-03-22T00:02:00Z" if eligibility_status != "pending" else "",
        "eligibility_reason": {"code": eligibility_status, "message": f"Eligibility {eligibility_status}."} if eligibility_status != "pending" else {"code": "", "message": ""},
        "eligibility_checked_by": "operator_b" if eligibility_status != "pending" else "",
        "eligibility_check_id": str(uuid.uuid4()) if eligibility_status != "pending" else "",
        "release_status": release_status,
        "release_timestamp": "2026-03-22T00:03:00Z" if release_status != "pending" else "",
        "release_actor": "operator_r" if release_status != "pending" else "",
        "release_notes": "Released." if release_status != "pending" else "",
        "release_id": str(uuid.uuid4()) if release_status != "pending" else "",
        "release_reason": {"code": release_status, "message": f"Release {release_status}."} if release_status != "pending" else {"code": "", "message": ""},
        "release_version": "v1",
    }
    return write_execution_package_safe(str(project_path), package)


def test_handoff_defaults_present():
    from NEXUS.execution_package_registry import normalize_execution_package

    normalized = normalize_execution_package({"package_id": "pkg-default"})
    assert normalized["handoff_status"] == "pending"
    assert normalized["handoff_timestamp"] == ""
    assert normalized["handoff_actor"] == ""
    assert normalized["handoff_notes"] == ""
    assert normalized["handoff_id"] == ""
    assert normalized["handoff_reason"] == {"code": "", "message": ""}
    assert normalized["handoff_version"] == "v1"
    assert normalized["handoff_executor_target_id"] == ""
    assert normalized["handoff_executor_target_name"] == ""
    assert normalized["handoff_aegis_result"] == {}


def test_handoff_request_marks_authorized_and_persists_full_aegis():
    from AEGIS.aegis_contract import build_aegis_result
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import read_execution_package

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-authorized")
        aegis = build_aegis_result(
            aegis_decision="approval_required",
            aegis_reason="Approval still required for remote runtime.",
            action_mode="execution",
            project_name="phase46proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="allow",
        )
        with _patched_aegis(aegis):
            result = run_command(
                "execution_package_handoff_request",
                project_path=str(tmp),
                execution_package_id="pkg-authorized",
                executor_target_id="remote_worker",
                handoff_actor="operator_h",
                handoff_notes="Authorized for future remote executor handoff.",
            )
        assert result["status"] == "ok"
        handoff = result["payload"]["handoff"]
        assert handoff["handoff_status"] == "authorized"
        assert handoff["handoff_timestamp"].endswith("Z")
        assert handoff["handoff_actor"] == "operator_h"
        assert handoff["handoff_notes"] == "Authorized for future remote executor handoff."
        assert handoff["handoff_id"]
        assert handoff["handoff_reason"]["code"] == "authorized"
        assert handoff["handoff_version"] == "v1"
        assert handoff["handoff_executor_target_id"] == "remote_worker"
        assert handoff["handoff_executor_target_name"] == "Remote Worker"
        assert handoff["handoff_aegis_result"]["aegis_decision"] == "approval_required"
        persisted = read_execution_package(str(tmp), "pkg-authorized")
        assert persisted is not None
        assert persisted["handoff_status"] == "authorized"
        assert persisted["handoff_aegis_result"]["workspace_valid"] is True


def test_handoff_request_blocks_for_invalid_conditions():
    from AEGIS.aegis_contract import build_aegis_result
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        allow = build_aegis_result(
            aegis_decision="allow",
            aegis_reason="Allowed.",
            action_mode="execution",
            project_name="phase46proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="allow",
        )
        with _patched_aegis(allow):
            _write_package(tmp, "pkg-unsealed", sealed=False)
            unsealed = run_command("execution_package_handoff_request", project_path=str(tmp), execution_package_id="pkg-unsealed", executor_target_id="remote_worker", handoff_actor="operator_h")
            assert unsealed["status"] == "ok"
            assert unsealed["payload"]["handoff"]["handoff_reason"]["code"] == "not_sealed"

            _write_package(tmp, "pkg-decision", decision_status="rejected")
            decision = run_command("execution_package_handoff_request", project_path=str(tmp), execution_package_id="pkg-decision", executor_target_id="remote_worker", handoff_actor="operator_h")
            assert decision["payload"]["handoff"]["handoff_reason"]["code"] == "decision_not_approved"

            _write_package(tmp, "pkg-eligibility-pending", eligibility_status="pending")
            eligibility_pending = run_command("execution_package_handoff_request", project_path=str(tmp), execution_package_id="pkg-eligibility-pending", executor_target_id="remote_worker", handoff_actor="operator_h")
            assert eligibility_pending["payload"]["handoff"]["handoff_reason"]["code"] == "eligibility_pending"

            _write_package(tmp, "pkg-eligibility-bad", eligibility_status="ineligible")
            eligibility_bad = run_command("execution_package_handoff_request", project_path=str(tmp), execution_package_id="pkg-eligibility-bad", executor_target_id="remote_worker", handoff_actor="operator_h")
            assert eligibility_bad["payload"]["handoff"]["handoff_reason"]["code"] == "eligibility_not_eligible"

            _write_package(tmp, "pkg-release", release_status="blocked")
            release = run_command("execution_package_handoff_request", project_path=str(tmp), execution_package_id="pkg-release", executor_target_id="remote_worker", handoff_actor="operator_h")
            assert release["payload"]["handoff"]["handoff_reason"]["code"] == "release_not_released"

            _write_package(tmp, "pkg-executed", execution_summary={"can_execute": True}, runtime_artifacts=[{"artifact": "ran"}])
            executed = run_command("execution_package_handoff_request", project_path=str(tmp), execution_package_id="pkg-executed", executor_target_id="remote_worker", handoff_actor="operator_h")
            assert executed["payload"]["handoff"]["handoff_reason"]["code"] == "execution_detected"

            _write_package(tmp, "pkg-bad-target")
            bad_target = run_command("execution_package_handoff_request", project_path=str(tmp), execution_package_id="pkg-bad-target", executor_target_id="windows_review_package", handoff_actor="operator_h")
            assert bad_target["payload"]["handoff"]["handoff_reason"]["code"] == "executor_target_invalid"

        _write_package(tmp, "pkg-aegis-deny")
        deny = build_aegis_result(
            aegis_decision="deny",
            aegis_reason="Denied.",
            action_mode="execution",
            project_name="phase46proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="allow",
        )
        with _patched_aegis(deny):
            denied = run_command("execution_package_handoff_request", project_path=str(tmp), execution_package_id="pkg-aegis-deny", executor_target_id="remote_worker", handoff_actor="operator_h")
            assert denied["payload"]["handoff"]["handoff_reason"]["code"] == "aegis_blocked"

        _write_package(tmp, "pkg-workspace")
        workspace_invalid = build_aegis_result(
            aegis_decision="allow",
            aegis_reason="Allowed.",
            action_mode="execution",
            project_name="phase46proj",
            project_path=str(tmp),
            workspace_valid=False,
            file_guard_status="allow",
        )
        with _patched_aegis(workspace_invalid):
            workspace = run_command("execution_package_handoff_request", project_path=str(tmp), execution_package_id="pkg-workspace", executor_target_id="remote_worker", handoff_actor="operator_h")
            assert workspace["payload"]["handoff"]["handoff_reason"]["code"] == "workspace_invalid"

        _write_package(tmp, "pkg-file-guard")
        file_guard = build_aegis_result(
            aegis_decision="allow",
            aegis_reason="Allowed.",
            action_mode="execution",
            project_name="phase46proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="deny",
        )
        with _patched_aegis(file_guard):
            guarded = run_command("execution_package_handoff_request", project_path=str(tmp), execution_package_id="pkg-file-guard", executor_target_id="remote_worker", handoff_actor="operator_h")
            assert guarded["payload"]["handoff"]["handoff_reason"]["code"] == "file_guard_blocked"


def test_handoff_input_validation_and_recompute_behavior():
    from AEGIS.aegis_contract import build_aegis_result
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import read_execution_package

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-recompute")
        missing_target = run_command("execution_package_handoff_request", project_path=str(tmp), execution_package_id="pkg-recompute", handoff_actor="operator_h")
        assert missing_target["status"] == "error"
        assert missing_target["payload"]["reason"] == "executor_target_id required."
        missing_actor = run_command("execution_package_handoff_request", project_path=str(tmp), execution_package_id="pkg-recompute", executor_target_id="remote_worker")
        assert missing_actor["status"] == "error"
        assert missing_actor["payload"]["reason"] == "handoff_actor required."

        allow = build_aegis_result(
            aegis_decision="allow",
            aegis_reason="Allowed.",
            action_mode="execution",
            project_name="phase46proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="allow",
        )
        with _patched_aegis(allow):
            first = run_command("execution_package_handoff_request", project_path=str(tmp), execution_package_id="pkg-recompute", executor_target_id="remote_worker", handoff_actor="operator_h1")
        deny = build_aegis_result(
            aegis_decision="deny",
            aegis_reason="Denied.",
            action_mode="execution",
            project_name="phase46proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="allow",
        )
        with _patched_aegis(deny):
            second = run_command("execution_package_handoff_request", project_path=str(tmp), execution_package_id="pkg-recompute", executor_target_id="remote_worker", handoff_actor="operator_h2")
        assert first["status"] == "ok"
        assert second["status"] == "ok"
        assert first["payload"]["handoff"]["handoff_status"] == "authorized"
        assert second["payload"]["handoff"]["handoff_status"] == "blocked"
        assert first["payload"]["handoff"]["handoff_id"] != second["payload"]["handoff"]["handoff_id"]
        persisted = read_execution_package(str(tmp), "pkg-recompute")
        assert persisted is not None
        assert persisted["handoff_actor"] == "operator_h2"
        assert persisted["handoff_status"] == "blocked"


def test_handoff_status_details_and_dashboard_include_summary_only_handoff():
    from AEGIS.aegis_contract import build_aegis_result
    from NEXUS.command_surface import run_command
    from NEXUS.registry import PROJECTS
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-dashboard")
        aegis = build_aegis_result(
            aegis_decision="allow",
            aegis_reason="Allowed.",
            action_mode="execution",
            project_name="phase46proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="allow",
        )
        with _patched_aegis(aegis):
            run_command(
                "execution_package_handoff_request",
                project_path=str(tmp),
                execution_package_id="pkg-dashboard",
                executor_target_id="remote_worker",
                handoff_actor="operator_h",
                handoff_notes="Summary check.",
            )
        status_result = run_command(
            "execution_package_handoff_status",
            project_path=str(tmp),
            execution_package_id="pkg-dashboard",
        )
        assert status_result["status"] == "ok"
        assert status_result["payload"]["handoff"]["handoff_status"] == "authorized"
        details = run_command(
            "execution_package_details",
            project_path=str(tmp),
            execution_package_id="pkg-dashboard",
        )
        assert details["status"] == "ok"
        assert details["payload"]["review_header"]["handoff_status"] == "authorized"
        assert details["payload"]["sections"]["handoff"]["handoff_executor_target_id"] == "remote_worker"
        assert details["payload"]["sections"]["handoff"]["handoff_aegis_result"]["aegis_decision"] == "allow"
        project_key = f"phase46_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp)}
        try:
            summary = build_registry_dashboard_summary()
            handoff_summary = summary.get("execution_package_handoff_summary") or {}
            assert handoff_summary.get("authorized_count_total", 0) >= 1
            assert handoff_summary.get("handoff_counts_by_project", {}).get(project_key, {}).get("authorized") == 1
            assert handoff_summary.get("latest_handoff_status_by_project", {}).get(project_key) == "authorized"
            assert handoff_summary.get("latest_executor_target_by_project", {}).get(project_key) == "remote_worker"
            rows = (summary.get("execution_package_review_summary") or {}).get("packages_by_project", {}).get(project_key) or []
            assert rows
            assert "handoff_notes" not in rows[0]
            assert "handoff_aegis_result" not in rows[0]
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_handoff_defaults_present,
        test_handoff_request_marks_authorized_and_persists_full_aegis,
        test_handoff_request_blocks_for_invalid_conditions,
        test_handoff_input_validation_and_recompute_behavior,
        test_handoff_status_details_and_dashboard_include_summary_only_handoff,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
