"""
Phase 54 autonomy modes and project routing tests.

Run: python tests/phase54_autonomy_modes_project_routing_test.py
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
    path = base / f"phase54_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@contextmanager
def _registered_project(project_path: Path):
    from NEXUS.registry import PROJECTS

    project_key = f"phase54_{uuid.uuid4().hex[:8]}"
    PROJECTS[project_key] = {
        "name": project_key,
        "path": str(project_path),
        "description": "Phase 54 temp project",
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

    queue = []
    for index, description in enumerate(tasks):
        queue.append(
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
        active_project="phase54proj",
        notes="",
        architect_plan={
            "objective": "Advance the next bounded package safely.",
            "next_agent": "coder",
            "implementation_steps": list(tasks),
        },
        task_queue=queue,
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
        task_queue_snapshot=queue,
        governance_status="ok",
        governance_result={"governance_status": "ok", "risk_level": "low"},
        enforcement_status="ok",
        enforcement_result={"enforcement_status": "ok"},
        guardrail_status="passed",
        guardrail_result={"guardrail_status": "passed", "launch_allowed": True},
        autonomy_mode="supervised_build",
        autonomy_mode_status="active",
        autonomy_mode_reason="Default safe mode.",
        allowed_actions=["prepare_package", "recommend_next_step", "bounded_low_risk_step"],
        blocked_actions=["unbounded_loop", "policy_self_modification", "mode_self_escalation"],
        escalation_threshold="low",
        approval_required_actions=["decision", "release", "handoff", "execute", "project_switch"],
        project_routing_status="idle",
        project_routing_result={},
        run_id="run-phase54",
    )


def _success_aegis(project_path: Path):
    from AEGIS.aegis_contract import build_aegis_result

    return build_aegis_result(
        aegis_decision="allow",
        aegis_reason="Allowed.",
        action_mode="execution",
        project_name="phase54proj",
        project_path=str(project_path),
        workspace_valid=True,
        file_guard_status="allow",
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


def test_autonomy_mode_assignment_persists_correctly():
    from NEXUS.command_surface import run_command
    from NEXUS.project_state import load_project_state

    with _local_test_dir() as tmp, _registered_project(tmp) as project_key:
        _write_state(tmp, ["Mode persistence task."])
        result = run_command(
            "project_autonomy_mode_set",
            project_name=project_key,
            autonomy_mode="assisted_autopilot",
            reason="Operator approved bounded assisted mode.",
        )
        assert result["status"] == "ok"
        state = load_project_state(str(tmp))
        assert state["autonomy_mode"] == "assisted_autopilot"
        assert state["autonomy_mode_status"] == "active"
        assert "project_switch" in (state.get("approval_required_actions") or [])


def test_supervised_build_pauses_where_expected():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import read_execution_package

    with _local_test_dir() as tmp, _registered_project(tmp) as project_key:
        _write_state(tmp, ["Prepare one bounded step."])
        with _patched_aegis(_success_aegis(tmp)), _patched_executor(_success_execution_result(tmp)):
            result = run_command("project_autopilot_start", project_name=project_key, iteration_limit=1)
        assert result["status"] == "ok"
        autopilot = result["payload"]["autopilot"]
        assert autopilot["autopilot_status"] == "paused"
        package = read_execution_package(str(tmp), autopilot["autopilot_last_package_id"])
        assert package
        assert package["decision_status"] == "pending"
        assert package["execution_status"] == "pending"


def test_assisted_autopilot_continues_only_within_allowed_scope():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp, _registered_project(tmp) as project_key:
        _write_state(tmp, ["Assist bounded package execution."])
        run_command("project_autonomy_mode_set", project_name=project_key, autonomy_mode="assisted_autopilot")
        with _patched_aegis(_success_aegis(tmp)), _patched_executor(_success_execution_result(tmp)):
            result = run_command("project_autopilot_start", project_name=project_key, iteration_limit=1)
        assert result["status"] == "ok"
        autopilot = result["payload"]["autopilot"]
        assert autopilot["autopilot_status"] in ("completed", "escalated")
        assert autopilot["autonomy_stop_rail_result"]["rail_type"] == "loops"
        assert autopilot["autonomy_stop_rail_result"]["routing_outcome"] == "escalate"
        assert autopilot["autopilot_stop_reason"] in ("autonomy_loop_limit_reached", "project_objective_completed")
        assert autopilot["autopilot_progress_summary"]["latest_local_analysis_status"] == "completed"


def test_low_risk_autonomous_development_still_escalates_on_risky_conditions():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import write_execution_package_safe
    from NEXUS.project_state import update_project_state_fields

    with _local_test_dir() as tmp, _registered_project(tmp) as project_key:
        _write_state(tmp, ["Risky follow-up task."])
        run_command("project_autonomy_mode_set", project_name=project_key, autonomy_mode="low_risk_autonomous_development")
        package_id = "pkg-risky"
        write_execution_package_safe(
            str(tmp),
            {
                "package_id": package_id,
                "package_version": "1.0",
                "package_kind": "review_only_execution_envelope",
                "project_name": "phase54proj",
                "project_path": str(tmp),
                "created_at": "2026-03-22T00:00:00Z",
                "package_status": "active",
                "review_status": "approved",
                "sealed": True,
                "seal_reason": "Bounded package.",
                "runtime_target_id": "local",
                "runtime_target_name": "local",
                "requires_human_approval": False,
                "aegis_decision": "allow",
                "decision_status": "approved",
                "eligibility_status": "eligible",
                "release_status": "released",
                "handoff_status": "authorized",
                "execution_status": "succeeded",
                "evaluation_status": "completed",
                "evaluation_summary": {"failure_risk_band": "high"},
                "local_analysis_status": "pending",
                "local_analysis_summary": {"suggested_next_action": "investigate_failure"},
                "routing_summary": {"runtime_node": "coder", "tool_name": "cursor_agent"},
                "execution_summary": {"review_only": False, "can_execute": True},
                "command_request": {"summary": "Risky bounded follow-up.", "task_type": "coder"},
            },
        )
        update_project_state_fields(str(tmp), execution_package_id=package_id, execution_package_path=str(tmp / "state" / "execution_packages" / f"{package_id}.json"))
        result = run_command("project_autopilot_start", project_name=project_key, iteration_limit=2)
        assert result["status"] == "ok"
        autopilot = result["payload"]["autopilot"]
        assert autopilot["autopilot_status"] == "escalated"
        assert "risk" in autopilot["autopilot_stop_reason"] or "investigate_failure" in autopilot["autopilot_stop_reason"]


def test_routing_chooses_bounded_next_steps_only():
    from NEXUS.project_routing import build_project_routing_decision

    decision = build_project_routing_decision(
        project_key="phase54proj",
        state={
            "autonomy_mode": "assisted_autopilot",
            "task_queue_snapshot": [{"id": "task-1", "priority": 0, "status": "pending", "task": "Implement safe step."}],
            "execution_bridge_summary": {"runtime_node": "coder", "selected_runtime_target": "local"},
            "governance_status": "ok",
            "enforcement_status": "ok",
            "guardrail_status": "passed",
        },
        active_package=None,
    )
    assert decision["selected_action"] == "prepare_package"
    assert decision["bounded"] is True
    assert decision["selected_backend_path"].startswith("execution_package_pipeline:")


def test_routing_never_bypasses_approvals_or_governance_gates():
    from NEXUS.project_routing import build_project_routing_decision

    decision = build_project_routing_decision(
        project_key="phase54proj",
        state={
            "autonomy_mode": "assisted_autopilot",
            "governance_status": "approval_required",
            "enforcement_status": "ok",
            "guardrail_status": "passed",
            "execution_bridge_summary": {"runtime_node": "coder", "selected_runtime_target": "local"},
        },
        active_package={"requires_human_approval": True, "aegis_decision": "approval_required"},
    )
    assert decision["selected_action"] == "escalate"
    assert decision["routing_status"] == "escalated"
    assert decision["requires_operator_review"] is True


def test_routing_status_is_persisted_and_surfaced_correctly():
    from NEXUS.command_surface import run_command
    from NEXUS.project_state import load_project_state

    with _local_test_dir() as tmp, _registered_project(tmp) as project_key:
        _write_state(tmp, ["Route status task."])
        run_command("project_autonomy_mode_set", project_name=project_key, autonomy_mode="assisted_autopilot")
        status = run_command("project_routing_status", project_name=project_key)
        assert status["status"] == "ok"
        assert status["payload"]["project_routing"]["selected_project_key"] == project_key
        state = load_project_state(str(tmp))
        assert state["project_routing_status"] in ("ready", "idle", "paused", "escalated", "stopped")
        assert isinstance(state.get("project_routing_result"), dict)


def test_dashboard_summary_reflects_autonomy_and_routing_state_correctly():
    from NEXUS.command_surface import run_command
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    with _local_test_dir() as tmp1, _local_test_dir() as tmp2, _registered_project(tmp1) as project_one, _registered_project(tmp2) as project_two:
        _write_state(tmp1, ["Task one."])
        _write_state(tmp2, ["Task two."])
        run_command("project_autonomy_mode_set", project_name=project_one, autonomy_mode="supervised_build")
        run_command("project_autonomy_mode_set", project_name=project_two, autonomy_mode="assisted_autopilot")
        dashboard = build_registry_dashboard_summary()
        summary = dashboard.get("project_autonomy_routing_summary") or {}
        selection_summary = dashboard.get("project_selection_summary") or {}
        assert summary.get("autonomy_mode_by_project", {}).get(project_one) == "supervised_build"
        assert summary.get("autonomy_mode_by_project", {}).get(project_two) == "assisted_autopilot"
        assert project_one in summary.get("routing_status_by_project", {})
        assert summary.get("supervised_mode_count_total", 0) >= 1
        assert summary.get("assisted_mode_count_total", 0) >= 1
        assert selection_summary.get("selected_project_id") in (project_one, project_two)
        assert selection_summary.get("eligible_project_count", 0) >= 1


def test_regression_project_autopilot_loop_behavior_remains_governed_and_bounded():
    from NEXUS.command_surface import run_command
    from NEXUS.project_state import load_project_state

    with _local_test_dir() as tmp, _registered_project(tmp) as project_key:
        _write_state(tmp, ["Task one.", "Task two."])
        run_command("project_autonomy_mode_set", project_name=project_key, autonomy_mode="assisted_autopilot")
        with _patched_aegis(_success_aegis(tmp)), _patched_executor(_success_execution_result(tmp)):
            result = run_command("project_autopilot_start", project_name=project_key, iteration_limit=1)
        assert result["status"] == "ok"
        state = load_project_state(str(tmp))
        statuses = [item.get("status") for item in state.get("task_queue") or []]
        assert statuses == ["completed", "pending"]
        assert state["project_routing_result"]["selected_action"] == "escalate"


def test_regression_dispatch_and_package_creation_semantics_remain_unchanged():
    from NEXUS.command_surface import run_command
    from NEXUS.runtime_dispatcher import dispatch

    plan = {
        "ready_for_dispatch": True,
        "project": {"project_name": "phase54proj", "project_path": "C:\\temp\\phase54"},
        "execution": {"runtime_target_id": "windows_review_package", "requires_human_approval": True},
    }
    baseline = dispatch(plan)
    with _local_test_dir() as tmp, _registered_project(tmp) as project_key:
        _write_state(tmp, ["Regression task."])
        run_command("project_autonomy_mode_set", project_name=project_key, autonomy_mode="assisted_autopilot")
        with _patched_aegis(_success_aegis(tmp)), _patched_executor(_success_execution_result(tmp)):
            run_command("project_autopilot_start", project_name=project_key, iteration_limit=1)
        after = dispatch(plan)
    assert baseline["dispatch_status"] == after["dispatch_status"]
    assert baseline["dispatch_result"]["execution_status"] == after["dispatch_result"]["execution_status"]


def main():
    tests = [
        test_autonomy_mode_assignment_persists_correctly,
        test_supervised_build_pauses_where_expected,
        test_assisted_autopilot_continues_only_within_allowed_scope,
        test_low_risk_autonomous_development_still_escalates_on_risky_conditions,
        test_routing_chooses_bounded_next_steps_only,
        test_routing_never_bypasses_approvals_or_governance_gates,
        test_routing_status_is_persisted_and_surfaced_correctly,
        test_dashboard_summary_reflects_autonomy_and_routing_state_correctly,
        test_regression_project_autopilot_loop_behavior_remains_governed_and_bounded,
        test_regression_dispatch_and_package_creation_semantics_remain_unchanged,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
