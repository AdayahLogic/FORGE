"""
Phase 47 runtime execution bridge tests.

Run: python tests/phase47_execution_package_runtime_execution_bridge_test.py
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
    path = base / f"phase47_{uuid.uuid4().hex[:8]}"
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


@contextmanager
def _patched_runtime_target_capabilities(target_id: str, capabilities: list[str]):
    from NEXUS.runtime_target_registry import RUNTIME_TARGET_REGISTRY

    target = RUNTIME_TARGET_REGISTRY[target_id]
    original = list(target.get("capabilities") or [])
    target["capabilities"] = list(capabilities)
    try:
        yield
    finally:
        target["capabilities"] = original


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
    handoff_status: str = "authorized",
    handoff_target: str = "local",
    execution_status: str = "pending",
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
        "project_name": "phase47proj",
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
        "execution_summary": {"review_only": True, "can_execute": False},
        "command_request": {"summary": "Execute the reviewed package.", "task_type": "coder"},
        "candidate_paths": ["src/module.py"],
        "expected_outputs": ["execution package"],
        "review_checklist": ["Confirm package remains sealed."],
        "rollback_notes": ["Revert touched files from the runtime log if execution fails."],
        "runtime_artifacts": [],
        "metadata": metadata,
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
        "handoff_status": handoff_status,
        "handoff_timestamp": "2026-03-22T00:04:00Z" if handoff_status != "pending" else "",
        "handoff_actor": "operator_h" if handoff_status != "pending" else "",
        "handoff_notes": "Authorized for execution." if handoff_status != "pending" else "",
        "handoff_id": str(uuid.uuid4()) if handoff_status != "pending" else "",
        "handoff_reason": {"code": handoff_status, "message": f"Handoff {handoff_status}."} if handoff_status != "pending" else {"code": "", "message": ""},
        "handoff_version": "v1",
        "handoff_executor_target_id": handoff_target if handoff_status != "pending" else "",
        "handoff_executor_target_name": handoff_target.title().replace("_", " ") if handoff_status != "pending" else "",
        "handoff_aegis_result": {},
        "execution_status": execution_status,
    }
    return write_execution_package_safe(str(project_path), package)


def test_execution_defaults_present():
    from NEXUS.execution_package_registry import normalize_execution_package

    normalized = normalize_execution_package({"package_id": "pkg-default"})
    assert normalized["execution_status"] == "pending"
    assert normalized["execution_timestamp"] == ""
    assert normalized["execution_actor"] == ""
    assert normalized["execution_id"] == ""
    assert normalized["execution_reason"] == {"code": "", "message": ""}
    assert normalized["execution_receipt"] == {
        "result_status": "",
        "exit_code": None,
        "log_ref": "",
        "files_touched_count": 0,
        "artifacts_written_count": 0,
        "failure_class": "",
        "stdout_summary": "",
        "stderr_summary": "",
        "rollback_summary": {},
    }
    assert normalized["execution_version"] == "v1"
    assert normalized["rollback_status"] == "not_needed"
    assert normalized["rollback_timestamp"] == ""
    assert normalized["rollback_reason"] == {"code": "", "message": ""}


def test_execution_request_marks_succeeded_and_persists_receipt():
    from AEGIS.aegis_contract import build_aegis_result
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import read_execution_package

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-success", handoff_target="local")
        aegis = build_aegis_result(
            aegis_decision="allow",
            aegis_reason="Allowed.",
            action_mode="execution",
            project_name="phase47proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="allow",
        )
        exec_result = {
            "execution_status": "succeeded",
            "execution_reason": {"code": "succeeded", "message": "Package executed successfully."},
            "execution_receipt": {
                "result_status": "succeeded",
                "exit_code": 0,
                "log_ref": str(tmp / "state" / "execution_runs" / "exec.log"),
                "files_touched_count": 0,
                "artifacts_written_count": 1,
                "failure_class": "",
            },
            "rollback_status": "not_needed",
            "rollback_timestamp": "",
            "rollback_reason": {"code": "", "message": ""},
            "runtime_artifact": {"artifact_type": "execution_log", "log_ref": "exec.log"},
            "execution_finished_at": "2026-03-22T00:05:00Z",
        }
        with _patched_aegis(aegis), _patched_executor(exec_result):
            result = run_command(
                "execution_package_execute_request",
                project_path=str(tmp),
                execution_package_id="pkg-success",
                execution_actor="operator_x",
            )
        assert result["status"] == "ok"
        execution = result["payload"]["execution"]
        assert execution["execution_status"] == "succeeded"
        assert execution["execution_actor"] == "operator_x"
        assert execution["execution_id"]
        assert execution["execution_reason"]["code"] == "succeeded"
        assert execution["execution_receipt"]["result_status"] == "succeeded"
        assert execution["execution_receipt"]["exit_code"] == 0
        assert execution["execution_receipt"]["log_ref"]
        assert execution["execution_receipt"]["files_touched_count"] == 0
        assert execution["execution_receipt"]["artifacts_written_count"] == 1
        assert execution["execution_aegis_result"]["aegis_decision"] == "allow"
        persisted = read_execution_package(str(tmp), "pkg-success")
        assert persisted is not None
        assert persisted["execution_status"] == "succeeded"
        assert persisted["execution_receipt"]["result_status"] == "succeeded"


def test_execution_request_blocks_for_invalid_conditions():
    from AEGIS.aegis_contract import build_aegis_result
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        allow = build_aegis_result(
            aegis_decision="allow",
            aegis_reason="Allowed.",
            action_mode="execution",
            project_name="phase47proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="allow",
        )
        with _patched_aegis(allow):
            _write_package(tmp, "pkg-unsealed", sealed=False)
            unsealed = run_command("execution_package_execute_request", project_path=str(tmp), execution_package_id="pkg-unsealed", execution_actor="operator_x")
            assert unsealed["payload"]["execution"]["execution_reason"]["code"] == "not_sealed"
            assert unsealed["payload"]["execution"]["execution_receipt"]["failure_class"] == "preflight_block"

            _write_package(tmp, "pkg-not-approved", decision_status="rejected")
            not_approved = run_command("execution_package_execute_request", project_path=str(tmp), execution_package_id="pkg-not-approved", execution_actor="operator_x")
            assert not_approved["payload"]["execution"]["execution_reason"]["code"] == "decision_not_approved"

            _write_package(tmp, "pkg-not-eligible", eligibility_status="ineligible")
            not_eligible = run_command("execution_package_execute_request", project_path=str(tmp), execution_package_id="pkg-not-eligible", execution_actor="operator_x")
            assert not_eligible["payload"]["execution"]["execution_reason"]["code"] == "eligibility_not_eligible"

            _write_package(tmp, "pkg-not-released", release_status="blocked")
            not_released = run_command("execution_package_execute_request", project_path=str(tmp), execution_package_id="pkg-not-released", execution_actor="operator_x")
            assert not_released["payload"]["execution"]["execution_reason"]["code"] == "release_not_released"

            _write_package(tmp, "pkg-not-authorized", handoff_status="blocked")
            not_authorized = run_command("execution_package_execute_request", project_path=str(tmp), execution_package_id="pkg-not-authorized", execution_actor="operator_x")
            assert not_authorized["payload"]["execution"]["execution_reason"]["code"] == "handoff_not_authorized"

            _write_package(tmp, "pkg-succeeded", execution_status="succeeded")
            already_succeeded = run_command("execution_package_execute_request", project_path=str(tmp), execution_package_id="pkg-succeeded", execution_actor="operator_x")
            assert already_succeeded["payload"]["execution"]["execution_reason"]["code"] == "duplicate_success_blocked"
            assert already_succeeded["payload"]["execution"]["execution_receipt"]["failure_class"] == "duplicate_success_block"

            _write_package(tmp, "pkg-bad-target", handoff_target="remote_worker")
            bad_target = run_command("execution_package_execute_request", project_path=str(tmp), execution_package_id="pkg-bad-target", execution_actor="operator_x")
            assert bad_target["payload"]["execution"]["execution_reason"]["code"] == "executor_target_invalid"

        _write_package(tmp, "pkg-aegis-deny")
        deny = build_aegis_result(
            aegis_decision="deny",
            aegis_reason="Denied.",
            action_mode="execution",
            project_name="phase47proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="allow",
        )
        with _patched_aegis(deny):
            denied = run_command("execution_package_execute_request", project_path=str(tmp), execution_package_id="pkg-aegis-deny", execution_actor="operator_x")
            assert denied["payload"]["execution"]["execution_reason"]["code"] == "aegis_blocked"
            assert denied["payload"]["execution"]["execution_receipt"]["failure_class"] == "aegis_block"


def test_execution_runtime_failure_and_rollback_states_persist():
    from AEGIS.aegis_contract import build_aegis_result
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-runtime-fail", handoff_target="local")
        aegis = build_aegis_result(
            aegis_decision="approval_required",
            aegis_reason="Still human controlled.",
            action_mode="execution",
            project_name="phase47proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="allow",
        )
        rolled_back = {
            "execution_status": "rolled_back",
            "execution_reason": {"code": "rolled_back", "message": "Runtime failed; rollback completed."},
            "execution_receipt": {
                "result_status": "failed",
                "exit_code": 1,
                "log_ref": str(tmp / "state" / "execution_runs" / "fail.log"),
                "files_touched_count": 1,
                "artifacts_written_count": 1,
                "failure_class": "runtime_execution_failure",
                "rollback_summary": {"used_notes": True, "notes_count": 1},
            },
            "rollback_status": "completed",
            "rollback_timestamp": "2026-03-22T00:06:00Z",
            "rollback_reason": {"code": "rollback_completed", "message": "Rollback guidance recorded."},
            "runtime_artifact": {"artifact_type": "execution_log", "log_ref": "fail.log"},
            "execution_finished_at": "2026-03-22T00:06:00Z",
        }
        with _patched_aegis(aegis), _patched_executor(rolled_back):
            rollback_result = run_command("execution_package_execute_request", project_path=str(tmp), execution_package_id="pkg-runtime-fail", execution_actor="operator_x")
        assert rollback_result["status"] == "ok"
        assert rollback_result["payload"]["execution"]["execution_status"] == "rolled_back"
        assert rollback_result["payload"]["execution"]["rollback_status"] == "completed"

        _write_package(tmp, "pkg-rollback-fail", handoff_target="local")
        rollback_failed = {
            "execution_status": "failed",
            "execution_reason": {"code": "runtime_execution_failed", "message": "Runtime failed and rollback failed."},
            "execution_receipt": {
                "result_status": "failed",
                "exit_code": 2,
                "log_ref": str(tmp / "state" / "execution_runs" / "rollback_fail.log"),
                "files_touched_count": 1,
                "artifacts_written_count": 1,
                "failure_class": "rollback_failure",
            },
            "rollback_status": "failed",
            "rollback_timestamp": "2026-03-22T00:07:00Z",
            "rollback_reason": {"code": "rollback_failed", "message": "Rollback logging failed."},
            "runtime_artifact": {"artifact_type": "execution_log", "log_ref": "rollback_fail.log"},
            "execution_finished_at": "2026-03-22T00:07:00Z",
        }
        with _patched_aegis(aegis), _patched_executor(rollback_failed):
            rollback_failed_result = run_command("execution_package_execute_request", project_path=str(tmp), execution_package_id="pkg-rollback-fail", execution_actor="operator_x")
        assert rollback_failed_result["payload"]["execution"]["execution_status"] == "failed"
        assert rollback_failed_result["payload"]["execution"]["execution_receipt"]["failure_class"] == "rollback_failure"
        assert rollback_failed_result["payload"]["execution"]["rollback_status"] == "failed"


def test_openclaw_execution_succeeds_and_persists_backend():
    from AEGIS.aegis_contract import build_aegis_result
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import read_execution_package

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-openclaw-success", handoff_target="openclaw", executor_backend_id="openclaw")
        aegis = build_aegis_result(
            aegis_decision="allow",
            aegis_reason="Allowed.",
            action_mode="execution",
            project_name="phase47proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="allow",
        )
        backend_result = {
            "status": "ok",
            "result_status": "succeeded",
            "exit_code": 0,
            "stdout_summary": "OpenClaw executed.",
            "stderr_summary": "",
            "log_ref": str(tmp / "state" / "execution_runs" / "openclaw.log"),
            "files_touched_count": 0,
            "artifacts_written_count": 1,
            "failure_class": "",
            "runtime_artifact": {"artifact_type": "execution_log", "log_ref": str(tmp / "state" / "execution_runs" / "openclaw.log")},
            "rollback_summary": {},
            "adapter_status": "active",
            "backend_id": "openclaw",
        }
        with _patched_aegis(aegis), _patched_openclaw_backend(backend_result):
            result = run_command(
                "execution_package_execute_request",
                project_path=str(tmp),
                execution_package_id="pkg-openclaw-success",
                execution_actor="operator_x",
            )
        execution = result["payload"]["execution"]
        assert execution["execution_status"] == "succeeded"
        assert execution["execution_executor_target_id"] == "openclaw"
        assert execution["execution_executor_backend_id"] == "openclaw"
        persisted = read_execution_package(str(tmp), "pkg-openclaw-success")
        assert persisted is not None
        assert persisted["execution_executor_target_id"] == "openclaw"
        assert persisted["execution_executor_backend_id"] == "openclaw"


def test_openclaw_target_and_capability_mismatch_block_before_backend():
    from AEGIS.aegis_contract import build_aegis_result
    from NEXUS.command_surface import run_command

    called = {"value": False}

    def _backend(**kwargs):
        called["value"] = True
        return {"status": "ok", "result_status": "succeeded", "adapter_status": "active", "backend_id": "openclaw"}

    with _local_test_dir() as tmp:
        aegis = build_aegis_result(
            aegis_decision="allow",
            aegis_reason="Allowed.",
            action_mode="execution",
            project_name="phase47proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="allow",
        )
        _write_package(tmp, "pkg-openclaw-mismatch", handoff_target="local", executor_backend_id="openclaw")
        with _patched_aegis(aegis), _patched_openclaw_backend(_backend):
            mismatch = run_command(
                "execution_package_execute_request",
                project_path=str(tmp),
                execution_package_id="pkg-openclaw-mismatch",
                execution_actor="operator_x",
            )
        execution = mismatch["payload"]["execution"]
        assert execution["execution_status"] == "blocked"
        assert execution["execution_reason"]["code"] == "executor_backend_target_mismatch"
        assert execution["execution_receipt"]["failure_class"] == "preflight_block"
        assert called["value"] is False

        _write_package(tmp, "pkg-openclaw-capability", handoff_target="openclaw", executor_backend_id="openclaw")
        with _patched_aegis(aegis), _patched_openclaw_backend(_backend), _patched_runtime_target_capabilities("openclaw", ["execute"]):
            capability = run_command(
                "execution_package_execute_request",
                project_path=str(tmp),
                execution_package_id="pkg-openclaw-capability",
                execution_actor="operator_x",
            )
        execution = capability["payload"]["execution"]
        assert execution["execution_status"] == "blocked"
        assert execution["execution_reason"]["code"] == "executor_capability_mismatch"
        assert execution["execution_receipt"]["failure_class"] == "preflight_block"
        assert called["value"] is False


def test_openclaw_does_not_create_dispatch_or_autonomy_path_and_gates_fire_first():
    from AEGIS.aegis_contract import build_aegis_result
    from NEXUS.command_surface import run_command
    from NEXUS.runtimes import RUNTIME_ADAPTERS
    from NEXUS.runtime_target_registry import RUNTIME_TARGET_REGISTRY

    assert "openclaw" not in RUNTIME_ADAPTERS
    assert "planning" not in (RUNTIME_TARGET_REGISTRY["openclaw"].get("capabilities") or [])
    assert "agent_routing" not in (RUNTIME_TARGET_REGISTRY["openclaw"].get("capabilities") or [])

    called = {"value": False}

    def _backend(**kwargs):
        called["value"] = True
        return {"status": "ok", "result_status": "succeeded", "adapter_status": "active", "backend_id": "openclaw"}

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-gate-unsealed", sealed=False, handoff_target="openclaw", executor_backend_id="openclaw")
        allow = build_aegis_result(
            aegis_decision="allow",
            aegis_reason="Allowed.",
            action_mode="execution",
            project_name="phase47proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="allow",
        )
        with _patched_aegis(allow), _patched_openclaw_backend(_backend):
            unsealed = run_command(
                "execution_package_execute_request",
                project_path=str(tmp),
                execution_package_id="pkg-gate-unsealed",
                execution_actor="operator_x",
            )
        assert unsealed["payload"]["execution"]["execution_reason"]["code"] == "not_sealed"
        assert called["value"] is False

        _write_package(tmp, "pkg-gate-aegis", handoff_target="openclaw", executor_backend_id="openclaw")
        deny = build_aegis_result(
            aegis_decision="deny",
            aegis_reason="Denied.",
            action_mode="execution",
            project_name="phase47proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="allow",
        )
        with _patched_aegis(deny), _patched_openclaw_backend(_backend):
            blocked = run_command(
                "execution_package_execute_request",
                project_path=str(tmp),
                execution_package_id="pkg-gate-aegis",
                execution_actor="operator_x",
            )
        assert blocked["payload"]["execution"]["execution_reason"]["code"] == "aegis_blocked"
        assert blocked["payload"]["execution"]["execution_receipt"]["failure_class"] == "aegis_block"
        assert called["value"] is False


def test_execution_status_details_and_dashboard_include_summary_only_execution():
    from AEGIS.aegis_contract import build_aegis_result
    from NEXUS.command_surface import run_command
    from NEXUS.registry import PROJECTS
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-dashboard", handoff_target="local")
        aegis = build_aegis_result(
            aegis_decision="allow",
            aegis_reason="Allowed.",
            action_mode="execution",
            project_name="phase47proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="allow",
        )
        exec_result = {
            "execution_status": "succeeded",
            "execution_reason": {"code": "succeeded", "message": "Executed."},
            "execution_receipt": {
                "result_status": "succeeded",
                "exit_code": 0,
                "log_ref": str(tmp / "state" / "execution_runs" / "dash.log"),
                "files_touched_count": 0,
                "artifacts_written_count": 1,
            },
            "rollback_status": "not_needed",
            "rollback_timestamp": "",
            "rollback_reason": {"code": "", "message": ""},
            "runtime_artifact": {"artifact_type": "execution_log", "log_ref": "dash.log"},
            "execution_finished_at": "2026-03-22T00:08:00Z",
        }
        with _patched_aegis(aegis), _patched_executor(exec_result):
            run_command("execution_package_execute_request", project_path=str(tmp), execution_package_id="pkg-dashboard", execution_actor="operator_x")
        status_result = run_command("execution_package_execute_status", project_path=str(tmp), execution_package_id="pkg-dashboard")
        assert status_result["status"] == "ok"
        assert status_result["payload"]["execution"]["execution_status"] == "succeeded"
        details = run_command("execution_package_details", project_path=str(tmp), execution_package_id="pkg-dashboard")
        assert details["status"] == "ok"
        assert details["payload"]["review_header"]["execution_status"] == "succeeded"
        assert details["payload"]["sections"]["execution"]["execution_receipt"]["result_status"] == "succeeded"
        project_key = f"phase47_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp)}
        try:
            summary = build_registry_dashboard_summary()
            execution_summary = summary.get("execution_package_execution_summary") or {}
            assert execution_summary.get("succeeded_count_total", 0) >= 1
            assert execution_summary.get("execution_counts_by_project", {}).get(project_key, {}).get("succeeded") == 1
            assert execution_summary.get("latest_execution_status_by_project", {}).get(project_key) == "succeeded"
            assert execution_summary.get("latest_execution_target_by_project", {}).get(project_key) == "local"
            rows = (summary.get("execution_package_review_summary") or {}).get("packages_by_project", {}).get(project_key) or []
            assert rows
            assert "execution_aegis_result" not in rows[0]
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_execution_defaults_present,
        test_execution_request_marks_succeeded_and_persists_receipt,
        test_execution_request_blocks_for_invalid_conditions,
        test_execution_runtime_failure_and_rollback_states_persist,
        test_openclaw_execution_succeeds_and_persists_backend,
        test_openclaw_target_and_capability_mismatch_block_before_backend,
        test_openclaw_does_not_create_dispatch_or_autonomy_path_and_gates_fire_first,
        test_execution_status_details_and_dashboard_include_summary_only_execution,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
