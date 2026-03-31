"""
Phase 10A portfolio autonomy hardening tests.

Run: python tests/phase10a_portfolio_autonomy_hardening_test.py
"""

from __future__ import annotations

import os
import shutil
import sys
import uuid
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@contextmanager
def _local_test_dir():
    base = ROOT / ".tmp_test_runs"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"phase10a_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@contextmanager
def _patched_projects(projects: dict[str, Path]):
    project_map = {
        key: {
            "name": key,
            "path": str(path),
            "workspace_type": "internal",
            "agents": ["coder", "tester"],
            "description": f"Phase 10A temp project {key}",
        }
        for key, path in projects.items()
    }
    with ExitStack() as stack:
        stack.enter_context(patch.dict("NEXUS.registry.PROJECTS", project_map, clear=True))
        stack.enter_context(patch.dict("NEXUS.project_routing.PROJECTS", project_map, clear=True))
        stack.enter_context(patch.dict("NEXUS.registry_dashboard.PROJECTS", project_map, clear=True))
        stack.enter_context(patch.dict("NEXUS.command_surface.PROJECTS", project_map, clear=True))
        yield


@contextmanager
def _portfolio_control_dir(control_dir: Path):
    previous = os.environ.get("FORGE_PORTFOLIO_CONTROL_DIR")
    os.environ["FORGE_PORTFOLIO_CONTROL_DIR"] = str(control_dir)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("FORGE_PORTFOLIO_CONTROL_DIR", None)
        else:
            os.environ["FORGE_PORTFOLIO_CONTROL_DIR"] = previous


def _run(name: str, fn):
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except Exception as exc:
        print(f"FAIL: {name} - {exc}")
        return False


def _write_state(project_path: Path, *, active_project: str, tasks: list[str], execution_package_id: str | None = None):
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
        active_project=active_project,
        notes="",
        architect_plan={"objective": "Phase 10A hardening fixture.", "implementation_steps": list(tasks)},
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
        agent_routing_summary={"runtime_node": "coder", "agent_name": "coder"},
        execution_bridge_report_path=None,
        execution_bridge_summary={"runtime_node": "coder", "selected_runtime_target": "local"},
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
        governance_result={"governance_status": "ok", "resolution_state": "resolved", "routing_outcome": "continue"},
        enforcement_status="ok",
        enforcement_result={"enforcement_status": "ok"},
        guardrail_status="passed",
        guardrail_result={"guardrail_status": "passed", "launch_allowed": True},
        autonomy_mode="assisted_autopilot",
        autonomy_mode_status="active",
        autonomy_mode_reason="Phase 10A fixture mode.",
        allowed_actions=["prepare_package", "decision", "eligibility", "release", "handoff", "execute", "evaluate", "local_analysis"],
        blocked_actions=["unbounded_loop"],
        escalation_threshold="guarded",
        approval_required_actions=["release", "handoff", "execute", "project_switch"],
        project_routing_status="idle",
        project_routing_result={},
        autopilot_status="idle",
        execution_package_id=execution_package_id,
        execution_package_path=str(project_path / "state" / "execution_packages" / f"{execution_package_id}.json") if execution_package_id else None,
        run_id=f"run-{active_project}",
    )


def _write_revenue_package(project_path: Path, package_id: str, *, score: float, workflow_priority: str):
    from NEXUS.execution_package_registry import write_execution_package_safe

    write_execution_package_safe(
        str(project_path),
        {
            "package_id": package_id,
            "project_name": project_path.name,
            "project_path": str(project_path),
            "pipeline_stage": "proposal_pending",
            "highest_value_next_action_score": score,
            "highest_value_next_action": "prioritize high-value opportunity",
            "highest_value_next_action_reason": "Revenue score indicates highest value.",
            "revenue_activation_status": "ready_for_revenue_action",
            "revenue_workflow_priority": workflow_priority,
            "execution_status": "pending",
        },
    )


def test_persistent_kill_switch_survives_reload():
    from NEXUS.portfolio_autonomy_controls import read_portfolio_kill_switch, set_portfolio_kill_switch

    with _local_test_dir() as tmp:
        control = tmp / "control"
        control.mkdir(parents=True, exist_ok=True)
        before = read_portfolio_kill_switch(base_path=str(control))
        assert before["enabled"] is False
        changed = set_portfolio_kill_switch(
            enabled=True,
            reason="Operator emergency stop.",
            changed_by="phase10a_test",
            scope="portfolio_autonomy",
            base_path=str(control),
        )
        after = read_portfolio_kill_switch(base_path=str(control))
        assert changed["enabled"] is True
        assert after["enabled"] is True
        assert after["reason"] == "Operator emergency stop."
        assert after["changed_by"] == "phase10a_test"


def test_kill_switch_blocks_selection_and_autopilot_execution():
    from NEXUS.command_surface import run_command
    from NEXUS.portfolio_autonomy_controls import set_portfolio_kill_switch
    from NEXUS.project_routing import evaluate_project_selection
    from NEXUS.project_state import load_project_state

    with _local_test_dir() as tmp:
        control = tmp / "control"
        project = tmp / "alpha"
        control.mkdir(parents=True, exist_ok=True)
        project.mkdir(parents=True, exist_ok=True)
        _write_state(project, active_project="alpha", tasks=["Bounded task."])
        with _portfolio_control_dir(control), _patched_projects({"alpha": project}):
            set_portfolio_kill_switch(enabled=True, reason="Hard stop test.", changed_by="phase10a_test")
            selection = evaluate_project_selection()
            assert selection["status"] == "blocked"
            assert selection["routing_outcome"] == "stop"
            started = run_command("project_autopilot_start", project_name="alpha", iteration_limit=1)
            assert started["status"] == "ok"
            autopilot = started["payload"]["autopilot"]
            assert autopilot["autopilot_stop_reason"] == "persistent_kill_switch_active"
            state = load_project_state(str(project))
            assert state["autopilot_stop_reason"] == "persistent_kill_switch_active"


def test_trace_captures_conflict_defer_and_kill_switch_events():
    from NEXUS.portfolio_autonomy_controls import set_portfolio_kill_switch
    from NEXUS.portfolio_autonomy_trace import read_portfolio_trace_tail
    from NEXUS.project_routing import evaluate_project_selection
    from NEXUS.project_state import update_project_state_fields

    with _local_test_dir() as tmp:
        control = tmp / "control"
        alpha = tmp / "alpha"
        beta = tmp / "beta"
        control.mkdir(parents=True, exist_ok=True)
        alpha.mkdir(parents=True, exist_ok=True)
        beta.mkdir(parents=True, exist_ok=True)
        _write_state(alpha, active_project="alpha", tasks=["Task A."])
        _write_state(beta, active_project="beta", tasks=["Task B."])
        with _portfolio_control_dir(control), _patched_projects({"alpha": alpha, "beta": beta}):
            evaluate_project_selection()
            update_project_state_fields(
                str(alpha),
                enforcement_status="blocked",
                enforcement_result={"enforcement_status": "blocked"},
            )
            update_project_state_fields(
                str(beta),
                enforcement_status="blocked",
                enforcement_result={"enforcement_status": "blocked"},
            )
            evaluate_project_selection()
            set_portfolio_kill_switch(enabled=True, reason="Trace kill switch.", changed_by="phase10a_test")
            evaluate_project_selection()
            trace = read_portfolio_trace_tail(100)
            event_types = {str(item.get("event_type") or "") for item in trace}
            assert "conflict_detected" in event_types
            assert "project_selected" in event_types
            assert "mission_deferred" in event_types
            assert "kill_switch_stop" in event_types


def test_explainability_and_revenue_priority_influence_selection():
    from NEXUS.project_routing import evaluate_project_selection
    from NEXUS.project_state import update_project_state_fields

    with _local_test_dir() as tmp:
        control = tmp / "control"
        alpha = tmp / "alpha"
        beta = tmp / "beta"
        control.mkdir(parents=True, exist_ok=True)
        alpha.mkdir(parents=True, exist_ok=True)
        beta.mkdir(parents=True, exist_ok=True)
        _write_state(alpha, active_project="alpha", tasks=["Task A."])
        _write_state(beta, active_project="beta", tasks=["Task B."])
        update_project_state_fields(
            str(alpha),
            revenue_activation_status="ready_for_revenue_action",
            revenue_workflow_priority="low",
            highest_value_next_action_score=0.18,
            highest_value_next_action="delay low-value opportunity",
            highest_value_next_action_reason="Low conversion confidence.",
        )
        update_project_state_fields(
            str(beta),
            revenue_activation_status="ready_for_revenue_action",
            revenue_workflow_priority="high",
            highest_value_next_action_score=0.92,
            highest_value_next_action="prioritize high-value opportunity",
            highest_value_next_action_reason="High conversion and ROI signals.",
        )
        with _portfolio_control_dir(control), _patched_projects({"alpha": alpha, "beta": beta}):
            result = evaluate_project_selection()
            assert result["selected_project_id"] == "beta"
            assert result["why_selected"]
            assert isinstance(result["why_not_selected"], list)
            assert result["next_action"]
            revenue_summary = result["revenue_priority_summary"]
            assert revenue_summary["influence"] == "active"
            ranking = revenue_summary["ranking"]
            assert ranking and ranking[0]["project_id"] == "beta"


def test_command_surface_and_dashboard_expose_hardening_outputs():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        control = tmp / "control"
        alpha = tmp / "alpha"
        control.mkdir(parents=True, exist_ok=True)
        alpha.mkdir(parents=True, exist_ok=True)
        _write_state(alpha, active_project="alpha", tasks=["Task A."])
        with _portfolio_control_dir(control), _patched_projects({"alpha": alpha}):
            changed = run_command(
                "persistent_kill_switch_status",
                enabled=True,
                reason="Operator test toggle.",
                changed_by="phase10a_test",
            )
            assert changed["status"] == "ok"
            status = run_command("portfolio_autonomy_status")
            assert status["status"] == "ok"
            assert "persistent_kill_switch" in status["payload"]
            trace = run_command("portfolio_autonomy_trace", n=20)
            assert trace["status"] == "ok"
            revenue = run_command("portfolio_autonomy_revenue_priority")
            assert revenue["status"] == "ok"
            dashboard = run_command("dashboard_summary")
            assert dashboard["status"] == "ok"
            payload = dashboard["payload"]
            assert "portfolio_autonomy_hardening_summary" in payload
            assert "persistent_kill_switch" in payload["portfolio_autonomy_hardening_summary"]


def main():
    tests = [
        test_persistent_kill_switch_survives_reload,
        test_kill_switch_blocks_selection_and_autopilot_execution,
        test_trace_captures_conflict_defer_and_kill_switch_events,
        test_explainability_and_revenue_priority_influence_selection,
        test_command_surface_and_dashboard_expose_hardening_outputs,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
