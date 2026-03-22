"""
Phase 53 project autopilot loop tests.

Run: python tests/phase53_project_autopilot_loop_test.py
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
    path = base / f"phase53_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@contextmanager
def _registered_project(project_path: Path):
    from NEXUS.registry import PROJECTS

    project_key = f"phase53_{uuid.uuid4().hex[:8]}"
    PROJECTS[project_key] = {
        "name": project_key,
        "path": str(project_path),
        "description": "Phase 53 temp project",
        "workspace_type": "internal",
        "agents": ["coder", "tester"],
    }
    try:
        yield project_key
    finally:
        PROJECTS.pop(project_key, None)


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


def _run(name: str, fn):
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except Exception as e:
        print(f"FAIL: {name} - {e}")
        return False


def _write_state(project_path: Path, tasks: list[str]):
    from NEXUS.project_state import save_project_state

    task_queue = []
    for index, description in enumerate(tasks):
        task_queue.append(
            {
                "id": f"task-{index + 1}",
                "type": "implementation_step",
                "payload": {"description": description},
                "priority": index,
                "status": "pending",
                "task": description,
            }
        )

    save_project_state(
        project_path=str(project_path),
        active_project="phase53proj",
        notes="",
        architect_plan={
            "objective": "Build the next bounded implementation slice.",
            "next_agent": "coder",
            "implementation_steps": list(tasks),
        },
        task_queue=task_queue,
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
        agent_routing_summary={
            "runtime_node": "coder",
            "agent_name": "coder",
            "tool_name": "cursor_agent",
        },
        execution_bridge_report_path=None,
        execution_bridge_summary={
            "runtime_node": "coder",
            "selected_runtime_target": "local",
            "fallback_runtime_target": "local",
            "human_review_required": False,
            "runtime_review_required": False,
            "runtime_selection_status": "selected",
        },
        autonomy_mode="assisted_autopilot",
        autonomy_mode_status="active",
        autonomy_mode_reason="Phase 53 fixture uses assisted mode for legacy continuation expectations.",
        allowed_actions=[
            "prepare_package",
            "recommend_next_step",
            "decision",
            "eligibility",
            "release",
            "handoff",
            "execute",
            "evaluate",
            "local_analysis",
            "project_switch",
        ],
        blocked_actions=["unbounded_loop", "policy_self_modification", "mode_self_escalation"],
        escalation_threshold="guarded",
        approval_required_actions=["release", "handoff", "execute", "project_switch"],
        project_routing_status="idle",
        project_routing_result={},
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
        task_queue_snapshot=task_queue,
        run_id="run-phase53",
    )


def _success_aegis(project_path: Path):
    from AEGIS.aegis_contract import build_aegis_result

    return build_aegis_result(
        aegis_decision="allow",
        aegis_reason="Allowed.",
        action_mode="execution",
        project_name="phase53proj",
        project_path=str(project_path),
        workspace_valid=True,
        file_guard_status="allow",
    )


def _approval_required_aegis(project_path: Path):
    from AEGIS.aegis_contract import build_aegis_result

    return build_aegis_result(
        aegis_decision="approval_required",
        aegis_reason="Human approval required.",
        action_mode="execution",
        project_name="phase53proj",
        project_path=str(project_path),
        workspace_valid=True,
        file_guard_status="allow",
        approval_required=True,
        requires_human_review=True,
    )


def _success_execution_result(project_path: Path):
    return {
        "execution_status": "succeeded",
        "execution_reason": {"code": "succeeded", "message": "Package executed successfully."},
        "execution_receipt": {
            "result_status": "succeeded",
            "exit_code": 0,
            "log_ref": str(project_path / "state" / "execution_runs" / "exec.log"),
            "files_touched_count": 0,
            "artifacts_written_count": 1,
            "failure_class": "",
        },
        "rollback_status": "not_needed",
        "rollback_timestamp": "",
        "rollback_reason": {"code": "", "message": ""},
        "runtime_artifact": {
            "artifact_type": "execution_log",
            "log_ref": str(project_path / "state" / "execution_runs" / "exec.log"),
        },
        "execution_finished_at": "2026-03-22T00:05:00Z",
    }


def test_autopilot_session_starts_cleanly_and_progress_persists():
    from NEXUS.command_surface import run_command
    from NEXUS.project_state import load_project_state

    with _local_test_dir() as tmp, _registered_project(tmp) as project_key:
        _write_state(tmp, ["Implement a bounded module slice."])
        with _patched_aegis(_success_aegis(tmp)), _patched_executor(_success_execution_result(tmp)):
            result = run_command("project_autopilot_start", project_name=project_key, iteration_limit=1)
        assert result["status"] == "ok"
        autopilot = result["payload"]["autopilot"]
        assert autopilot["autopilot_session_id"]
        assert autopilot["autopilot_status"] == "completed"
        assert autopilot["autopilot_last_package_id"]
        progress = autopilot["autopilot_progress_summary"]
        assert progress["project_objective_summary"] == "Build the next bounded implementation slice."
        assert progress["latest_execution_result"]["execution_status"] == "succeeded"
        assert progress["latest_evaluation_status"] == "completed"
        assert progress["latest_local_analysis_status"] == "completed"
        assert progress["operator_review_required"] is False
        state = load_project_state(str(tmp))
        assert state["autopilot_status"] == "completed"
        assert state["autopilot_progress_summary"]["latest_local_analysis_status"] == "completed"
        assert all(str(item.get("status")) == "completed" for item in state["task_queue"])


def test_autopilot_remains_bounded_by_iteration_limit():
    from NEXUS.command_surface import run_command
    from NEXUS.project_state import load_project_state

    with _local_test_dir() as tmp, _registered_project(tmp) as project_key:
        _write_state(tmp, ["Task one.", "Task two."])
        with _patched_aegis(_success_aegis(tmp)), _patched_executor(_success_execution_result(tmp)):
            result = run_command("project_autopilot_start", project_name=project_key, iteration_limit=1)
        assert result["status"] == "ok"
        autopilot = result["payload"]["autopilot"]
        assert autopilot["autopilot_iteration_count"] == 1
        assert autopilot["autopilot_status"] == "completed"
        assert autopilot["autopilot_stop_reason"] == "iteration_limit_reached"
        state = load_project_state(str(tmp))
        statuses = [item.get("status") for item in state.get("task_queue") or []]
        assert statuses == ["completed", "pending"]


def test_autopilot_escalates_on_governance_required_state_without_bypass():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import read_execution_package

    with _local_test_dir() as tmp, _registered_project(tmp) as project_key:
        _write_state(tmp, ["Task requiring approval."])
        with _patched_aegis(_approval_required_aegis(tmp)):
            result = run_command("project_autopilot_start", project_name=project_key, iteration_limit=1)
        assert result["status"] == "ok"
        autopilot = result["payload"]["autopilot"]
        assert autopilot["autopilot_status"] == "escalated"
        assert autopilot["autopilot_escalation_reason"] == "approval_required_unresolved"
        package = read_execution_package(str(tmp), autopilot["autopilot_last_package_id"])
        assert package
        assert package["decision_status"] == "pending"
        assert package["execution_status"] == "pending"
        assert package["evaluation_status"] == "pending"
        assert package["local_analysis_status"] == "pending"


def test_autopilot_stops_safely_when_no_valid_next_step_exists():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp, _registered_project(tmp) as project_key:
        _write_state(tmp, [])
        result = run_command("project_autopilot_start", project_name=project_key, iteration_limit=2)
        assert result["status"] == "ok"
        autopilot = result["payload"]["autopilot"]
        assert autopilot["autopilot_status"] == "completed"
        assert autopilot["autopilot_stop_reason"] == "no_next_bounded_task"


def test_autopilot_status_command_returns_stored_state():
    from NEXUS.command_surface import run_command
    from NEXUS.project_state import update_project_state_fields

    with _local_test_dir() as tmp, _registered_project(tmp) as project_key:
        _write_state(tmp, ["Stored status task."])
        update_project_state_fields(
            str(tmp),
            autopilot_status="paused",
            autopilot_session_id="sess-123",
            autopilot_project_key=project_key,
            autopilot_mode="supervised_bounded",
            autopilot_iteration_count=2,
            autopilot_iteration_limit=5,
            autopilot_started_at="2026-03-22T01:00:00Z",
            autopilot_updated_at="2026-03-22T01:05:00Z",
            autopilot_last_package_id="pkg-123",
            autopilot_last_result={"status": "paused"},
            autopilot_next_action="operator_review",
            autopilot_stop_reason="",
            autopilot_escalation_reason="manual_review_required",
            autopilot_progress_summary={"project_objective_summary": "Stored objective."},
        )
        result = run_command("project_autopilot_status", project_name=project_key)
        assert result["status"] == "ok"
        autopilot = result["payload"]["autopilot"]
        assert autopilot["autopilot_status"] == "paused"
        assert autopilot["autopilot_session_id"] == "sess-123"
        assert autopilot["autopilot_iteration_count"] == 2
        assert autopilot["autopilot_escalation_reason"] == "manual_review_required"


def test_pause_resume_stop_commands_behave_safely():
    from NEXUS.command_surface import run_command
    from NEXUS.project_state import load_project_state, update_project_state_fields

    with _local_test_dir() as tmp, _registered_project(tmp) as project_key:
        _write_state(tmp, ["Resume task."])
        update_project_state_fields(
            str(tmp),
            autopilot_status="ready",
            autopilot_session_id="sess-ready",
            autopilot_project_key=project_key,
            autopilot_iteration_limit=2,
            autopilot_mode="supervised_bounded",
        )
        paused = run_command("project_autopilot_pause", project_name=project_key)
        assert paused["status"] == "ok"
        assert paused["payload"]["autopilot"]["autopilot_status"] == "paused"

        with _patched_aegis(_success_aegis(tmp)), _patched_executor(_success_execution_result(tmp)):
            resumed = run_command("project_autopilot_resume", project_name=project_key)
        assert resumed["status"] == "ok"
        assert resumed["payload"]["autopilot"]["autopilot_status"] == "completed"

        update_project_state_fields(
            str(tmp),
            autopilot_status="paused",
            autopilot_session_id="sess-stop",
            autopilot_project_key=project_key,
            autopilot_iteration_limit=2,
            autopilot_mode="supervised_bounded",
        )
        stopped = run_command("project_autopilot_stop", project_name=project_key)
        assert stopped["status"] == "ok"
        state = load_project_state(str(tmp))
        assert state["autopilot_status"] == "completed"
        assert state["autopilot_stop_reason"] == "operator_requested_stop"


def test_dashboard_summary_reflects_autopilot_status():
    from NEXUS.project_state import update_project_state_fields
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    with _local_test_dir() as tmp1, _local_test_dir() as tmp2, _registered_project(tmp1) as project_one, _registered_project(tmp2) as project_two:
        _write_state(tmp1, ["Task one."])
        _write_state(tmp2, ["Task two."])
        update_project_state_fields(
            str(tmp1),
            autopilot_status="paused",
            autopilot_project_key=project_one,
            autopilot_iteration_count=1,
            autopilot_iteration_limit=3,
            autopilot_next_action="operator_review",
        )
        update_project_state_fields(
            str(tmp2),
            autopilot_status="escalated",
            autopilot_project_key=project_two,
            autopilot_iteration_count=2,
            autopilot_iteration_limit=4,
            autopilot_next_action="operator_review",
        )
        dashboard = build_registry_dashboard_summary()
        summary = dashboard.get("project_autopilot_summary") or {}
        assert summary.get("autopilot_surface_status") == "ok"
        assert project_one in summary.get("active_autopilot_projects", [])
        assert summary.get("autopilot_status_by_project", {}).get(project_one) == "paused"
        assert summary.get("autopilot_status_by_project", {}).get(project_two) == "escalated"
        assert summary.get("iteration_counts_by_project", {}).get(project_two, {}).get("iteration_count") == 2
        assert summary.get("paused_count_total", 0) >= 1
        assert summary.get("escalation_count_total", 0) >= 1
        assert summary.get("latest_autopilot_action_by_project", {}).get(project_one) == "operator_review"


def test_regression_dispatch_and_package_creation_semantics_remain_unchanged():
    from NEXUS.command_surface import run_command
    from NEXUS.runtime_dispatcher import dispatch

    plan = {
        "ready_for_dispatch": True,
        "project": {"project_name": "phase53proj", "project_path": "C:\\temp\\phase53"},
        "execution": {"runtime_target_id": "windows_review_package", "requires_human_approval": True},
    }
    baseline = dispatch(plan)
    with _local_test_dir() as tmp, _registered_project(tmp) as project_key:
        _write_state(tmp, ["Regression task."])
        with _patched_aegis(_success_aegis(tmp)), _patched_executor(_success_execution_result(tmp)):
            run_command("project_autopilot_start", project_name=project_key, iteration_limit=1)
        after = dispatch(plan)
    assert baseline["dispatch_status"] == after["dispatch_status"]
    assert baseline["dispatch_result"]["execution_status"] == after["dispatch_result"]["execution_status"]


def main():
    tests = [
        test_autopilot_session_starts_cleanly_and_progress_persists,
        test_autopilot_remains_bounded_by_iteration_limit,
        test_autopilot_escalates_on_governance_required_state_without_bypass,
        test_autopilot_stops_safely_when_no_valid_next_step_exists,
        test_autopilot_status_command_returns_stored_state,
        test_pause_resume_stop_commands_behave_safely,
        test_dashboard_summary_reflects_autopilot_status,
        test_regression_dispatch_and_package_creation_semantics_remain_unchanged,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
