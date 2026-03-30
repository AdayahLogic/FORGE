"""
Phase 12: verified live execution lane + persistent global control plane.

Run: python tests/phase12_live_execution_control_plane_test.py
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
    path = base / f"phase12_{uuid.uuid4().hex[:8]}"
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
def _restore_global_control_state():
    from NEXUS.global_control_state import load_global_control_state, save_global_control_state

    snapshot = load_global_control_state()
    try:
        yield
    finally:
        save_global_control_state(snapshot, actor="phase12_test", reason="restore_snapshot")


def _run(name: str, fn):
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except Exception as e:
        print(f"FAIL: {name} - {e}")
        return False


def _write_state(project_path: Path):
    from NEXUS.project_state import save_project_state

    save_project_state(
        project_path=str(project_path),
        active_project="phase12proj",
        notes="",
        architect_plan={"objective": "Phase 12 test objective."},
        task_queue=[],
        coder_output_path=None,
        implementation_file_path=None,
        test_report_path=None,
        docs_output_path=None,
        execution_report_path=None,
        workspace_report_path=None,
        operator_log_path=None,
        supervisor_report_path=None,
        supervisor_decision=None,
        autonomous_cycle_report_path=None,
        autonomous_cycle_summary=None,
        computer_use_report_path=None,
        computer_use_summary=None,
        tool_execution_report_path=None,
        tool_execution_summary=None,
        file_modification_report_path=None,
        file_modification_summary=None,
        diff_patch_report_path=None,
        diff_patch_summary=None,
        agent_routing_report_path=None,
        agent_routing_summary={"runtime_node": "coder", "tool_name": "cursor_agent"},
        execution_bridge_report_path=None,
        execution_bridge_summary={"selected_runtime_target": "openclaw", "runtime_selection_status": "selected"},
        engine_registry_report_path=None,
        engine_registry_summary=None,
        capability_registry_report_path=None,
        capability_registry_summary=None,
        terminal_report_path=None,
        terminal_summary=None,
        browser_research_report_path=None,
        browser_research_summary=None,
        full_automation_report_path=None,
        full_automation_summary=None,
        task_queue_snapshot=[],
        governance_status="ok",
        governance_result={"governance_status": "ok", "routing_outcome": "continue", "resolution_state": "resolved"},
        enforcement_status="ok",
        enforcement_result={"enforcement_status": "ok"},
        project_lifecycle_status="active",
        project_lifecycle_result={"lifecycle_status": "active"},
        run_id="run-phase12",
    )


def _write_ready_package(project_path: Path, package_id: str):
    from NEXUS.execution_package_registry import write_execution_package_safe

    package = {
        "package_id": package_id,
        "project_name": "phase12proj",
        "project_path": str(project_path),
        "run_id": "run-phase12",
        "sealed": True,
        "decision_status": "approved",
        "eligibility_status": "eligible",
        "release_status": "released",
        "handoff_status": "authorized",
        "handoff_executor_target_id": "openclaw",
        "handoff_executor_target_name": "OpenClaw",
        "execution_status": "pending",
        "runtime_target_id": "openclaw",
        "runtime_target_name": "OpenClaw",
        "routing_summary": {"selection_status": "selected", "runtime_node": "coder", "tool_name": "cursor_agent"},
        "execution_receipt": {"result_status": "", "exit_code": None, "log_ref": "", "files_touched_count": 0, "artifacts_written_count": 0, "failure_class": ""},
        "metadata": {"executor_backend_id": "openclaw", "openclaw_active": True},
    }
    out = write_execution_package_safe(str(project_path), package)
    assert out


def _allow_aegis(project_path: Path):
    from AEGIS.aegis_contract import build_aegis_result

    return build_aegis_result(
        aegis_decision="allow",
        aegis_reason="Allowed.",
        action_mode="execution",
        project_name="phase12proj",
        project_path=str(project_path),
        workspace_valid=True,
        file_guard_status="allow",
    )


def _success_exec_result(project_path: Path):
    return {
        "execution_status": "succeeded",
        "execution_reason": {"code": "succeeded", "message": "Controlled execution succeeded."},
        "execution_receipt": {
            "result_status": "succeeded",
            "exit_code": 0,
            "log_ref": str(project_path / "state" / "execution_runs" / "phase12.log"),
            "files_touched_count": 0,
            "artifacts_written_count": 1,
            "failure_class": "",
        },
        "rollback_status": "not_needed",
        "rollback_timestamp": "",
        "rollback_reason": {"code": "", "message": ""},
        "runtime_artifact": {
            "artifact_type": "execution_log",
            "log_ref": str(project_path / "state" / "execution_runs" / "phase12.log"),
            "runtime_target_id": "openclaw",
        },
        "execution_finished_at": "2026-03-29T01:00:00Z",
    }


def test_persistent_global_control_state_survives_reload():
    from NEXUS.global_control_state import load_global_control_state, update_global_control_state

    with _restore_global_control_state():
        marker = uuid.uuid4().hex[:8]
        updated = update_global_control_state(
            updates={
                "global_system_mode": "degraded",
                "active_missions": {"phase12proj": {"status": "active", "mission_marker": marker}},
                "active_strategy_versions": {"phase12proj": {"promotion_state": "active", "strategy_version": "v12"}},
                "resource_limits": {"max_loops": 9, "max_operations": 21, "max_runtime_seconds": 600, "max_budget_units": 50},
                "autonomy_mode": "assisted_autopilot",
                "last_stop_reason": "phase12_test_marker",
                "degraded_mode_flags": {"control_plane_degraded": True, "routing_degraded": False, "execution_verification_degraded": False},
            },
            actor="phase12_test",
            reason="test_persistence",
        )
        loaded = load_global_control_state()
        assert updated["active_missions"]["phase12proj"]["mission_marker"] == marker
        assert loaded["active_missions"]["phase12proj"]["mission_marker"] == marker
        assert loaded["global_system_mode"] == "degraded"
        assert loaded["resource_limits"]["max_operations"] == 21


def test_persistent_kill_switch_blocks_execution():
    from NEXUS.execution_package_registry import record_execution_package_execution, read_execution_package
    from NEXUS.global_control_state import set_persistent_kill_switch

    with _restore_global_control_state(), _local_test_dir() as tmp:
        _write_state(tmp)
        _write_ready_package(tmp, "pkg-kill")
        set_persistent_kill_switch(active=True, actor="phase12_test", reason="kill switch for test")
        result = record_execution_package_execution(
            project_path=str(tmp),
            package_id="pkg-kill",
            execution_actor="operator_x",
        )
        package = read_execution_package(str(tmp), "pkg-kill") or {}
        assert result["status"] == "denied"
        assert package.get("execution_status") == "blocked"
        assert (package.get("execution_reason") or {}).get("code") == "routing_enforcement_denied"


def test_routing_hard_deny_behavior_blocks_execution():
    from NEXUS.execution_package_registry import record_execution_package_execution, read_execution_package
    from NEXUS.project_state import update_project_state_fields

    with _restore_global_control_state(), _local_test_dir() as tmp:
        _write_state(tmp)
        _write_ready_package(tmp, "pkg-routing-deny")
        update_project_state_fields(str(tmp), enforcement_status="blocked", enforcement_result={"enforcement_status": "blocked"})
        result = record_execution_package_execution(
            project_path=str(tmp),
            package_id="pkg-routing-deny",
            execution_actor="operator_x",
        )
        package = read_execution_package(str(tmp), "pkg-routing-deny") or {}
        assert result["status"] == "denied"
        assert package.get("execution_status") == "blocked"
        assert (package.get("execution_reason") or {}).get("code") == "routing_enforcement_denied"


def test_live_execution_lane_creates_receipt_and_verification_truth():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_receipt_registry import read_latest_execution_receipt
    from NEXUS.execution_verification_registry import read_latest_execution_verification
    from NEXUS.execution_truth import read_execution_truth

    with _restore_global_control_state(), _local_test_dir() as tmp:
        _write_state(tmp)
        _write_ready_package(tmp, "pkg-live")
        with _patched_aegis(_allow_aegis(tmp)), _patched_executor(_success_exec_result(tmp)):
            result = run_command(
                "execution_package_execute_request",
                project_path=str(tmp),
                execution_package_id="pkg-live",
                execution_actor="operator_x",
            )
        assert result["status"] == "ok"
        receipt = read_latest_execution_receipt(package_id="pkg-live")
        verification = read_latest_execution_verification(package_id="pkg-live")
        truth = read_execution_truth(package_id="pkg-live")
        assert receipt.get("execution_status") == "succeeded"
        assert verification.get("verification_status") == "verified"
        assert truth.get("truth_state") == "executed_verified"


def test_command_surface_control_visibility():
    from NEXUS.command_surface import run_command

    with _restore_global_control_state(), _local_test_dir() as tmp:
        _write_state(tmp)
        _write_ready_package(tmp, "pkg-command-status")
        with _patched_aegis(_allow_aegis(tmp)), _patched_executor(_success_exec_result(tmp)):
            run_command(
                "execution_package_execute_request",
                project_path=str(tmp),
                execution_package_id="pkg-command-status",
                execution_actor="operator_x",
            )
        control = run_command("global_control_state")
        lane = run_command("execution_lane_status")
        kill_switch = run_command("persistent_kill_switch_status")
        routing = run_command(
            "routing_enforcement_status",
            project_path=str(tmp),
            runtime_target_id="openclaw",
            allocation_status="selected",
            operation_type="execution",
        )
        live = run_command(
            "live_execution_status",
            project_path=str(tmp),
            execution_package_id="pkg-command-status",
        )
        assert control["status"] == "ok"
        assert lane["status"] == "ok"
        assert kill_switch["status"] == "ok"
        assert routing["status"] in ("ok", "blocked")
        assert live["status"] == "ok"
        assert "truth_record" in live["payload"]
        assert "verification_record" in live["payload"]


def main():
    tests = [
        test_persistent_global_control_state_survives_reload,
        test_persistent_kill_switch_blocks_execution,
        test_routing_hard_deny_behavior_blocks_execution,
        test_live_execution_lane_creates_receipt_and_verification_truth,
        test_command_surface_control_visibility,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
