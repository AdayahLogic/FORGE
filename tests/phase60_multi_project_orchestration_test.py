"""
Phase 60 multi-project orchestration foundations tests.

Run: python tests/phase60_multi_project_orchestration_test.py
"""

from __future__ import annotations

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
    path = base / f"phase60_{uuid.uuid4().hex[:8]}"
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


@contextmanager
def _patched_projects(projects: dict[str, Path]):
    project_map = {
        key: {
            "name": key,
            "path": str(path),
            "workspace_type": "internal",
            "agents": ["coder", "tester"],
            "description": f"Phase 60 temp project {key}",
        }
        for key, path in projects.items()
    }
    with ExitStack() as stack:
        stack.enter_context(patch.dict("NEXUS.registry.PROJECTS", project_map, clear=True))
        stack.enter_context(patch.dict("NEXUS.project_routing.PROJECTS", project_map, clear=True))
        stack.enter_context(patch.dict("NEXUS.registry_dashboard.PROJECTS", project_map, clear=True))
        yield


def _write_state(
    project_path: Path,
    *,
    active_project: str,
    tasks: list[str] | None = None,
    governance_status: str = "ok",
    governance_result: dict | None = None,
    enforcement_status: str = "ok",
    enforcement_result: dict | None = None,
    project_routing_status: str = "idle",
    autopilot_status: str = "idle",
    autonomy_stop_rail_status: str = "ok",
    autonomy_stop_rail_result: dict | None = None,
    execution_package_id: str | None = None,
):
    from NEXUS.project_state import save_project_state

    queue: list[dict] = []
    for index, description in enumerate(tasks or []):
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
        architect_plan={"objective": "Phase 60 routing test.", "implementation_steps": list(tasks or [])},
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
        governance_status=governance_status,
        governance_result=governance_result or {"governance_status": governance_status, "resolution_state": "resolved", "routing_outcome": "continue"},
        project_selection_status=None,
        project_selection_result=None,
        enforcement_status=enforcement_status,
        enforcement_result=enforcement_result or {"enforcement_status": enforcement_status},
        project_lifecycle_status="active",
        project_lifecycle_result={"lifecycle_status": "active"},
        guardrail_status="passed",
        guardrail_result={"guardrail_status": "passed", "launch_allowed": True},
        autonomy_mode="assisted_autopilot",
        autonomy_mode_status="active",
        autonomy_mode_reason="Phase 60 fixture.",
        allowed_actions=["prepare_package", "decision"],
        blocked_actions=["unbounded_loop"],
        escalation_threshold="low",
        approval_required_actions=["project_switch"],
        autopilot_status=autopilot_status,
        autopilot_project_key=active_project,
        autonomy_stop_rail_status=autonomy_stop_rail_status,
        autonomy_stop_rail_result=autonomy_stop_rail_result or {},
        project_routing_status=project_routing_status,
        project_routing_result={},
        execution_package_id=execution_package_id,
        execution_package_path=str(project_path / "state" / "execution_packages" / f"{execution_package_id}.json") if execution_package_id else None,
        run_id=f"run-{active_project}",
    )


def test_single_eligible_project_selected():
    from NEXUS.project_routing import evaluate_project_selection

    with _local_test_dir() as tmp:
        alpha = tmp / "alpha"
        beta = tmp / "beta"
        alpha.mkdir()
        beta.mkdir()
        _write_state(alpha, active_project="alpha", tasks=["Do one bounded task."])
        _write_state(
            beta,
            active_project="beta",
            tasks=["Blocked task."],
            governance_status="review_required",
            governance_result={
                "governance_status": "review_required",
                "resolution_state": "pause",
                "routing_outcome": "pause",
            },
        )
        with _patched_projects({"alpha": alpha, "beta": beta}):
            result = evaluate_project_selection()
    assert result["status"] == "selected"
    assert result["selected_project_id"] == "alpha"
    assert result["eligible_projects"] == ["alpha"]
    assert "beta" in result["blocked_projects"]


def test_multiple_eligible_projects_contention_resolves_deterministically():
    from NEXUS.project_routing import evaluate_project_selection

    with _local_test_dir() as tmp:
        alpha = tmp / "alpha"
        beta = tmp / "beta"
        alpha.mkdir()
        beta.mkdir()
        _write_state(alpha, active_project="alpha", tasks=["Queued task."], execution_package_id="pkg-alpha")
        _write_state(beta, active_project="beta", tasks=["Another queued task."])
        with _patched_projects({"alpha": alpha, "beta": beta}):
            result = evaluate_project_selection()
    assert result["status"] == "selected"
    assert result["contention_detected"] is True
    assert result["selected_project_id"] == "alpha"
    assert result["priority_basis"].startswith("active_package")


def test_blocked_project_excluded_from_selection():
    from NEXUS.project_routing import evaluate_project_selection

    with _local_test_dir() as tmp:
        blocked = tmp / "blocked"
        ready = tmp / "ready"
        blocked.mkdir()
        ready.mkdir()
        _write_state(
            blocked,
            active_project="blocked",
            tasks=["Should not run."],
            enforcement_status="blocked",
            enforcement_result={"enforcement_status": "blocked", "reason": "approval missing"},
        )
        _write_state(ready, active_project="ready", tasks=["Can run."])
        with _patched_projects({"blocked": blocked, "ready": ready}):
            result = evaluate_project_selection()
    assert result["selected_project_id"] == "ready"
    assert "blocked" in result["blocked_projects"]
    trace = result["governance_trace"]["project_evaluations"]["blocked"]
    assert trace["blocked_reason"] == "enforcement_blocked"


def test_paused_or_stopped_project_excluded_from_selection():
    from NEXUS.project_routing import evaluate_project_selection

    with _local_test_dir() as tmp:
        paused = tmp / "paused"
        active = tmp / "active"
        paused.mkdir()
        active.mkdir()
        _write_state(
            paused,
            active_project="paused",
            tasks=["Paused task."],
            autonomy_stop_rail_status="paused",
            autonomy_stop_rail_result={
                "status": "paused",
                "rail_type": "loops",
                "routing_outcome": "pause",
                "stop_reason": "autonomy_loop_limit_reached",
            },
            autopilot_status="paused",
        )
        _write_state(active, active_project="active", tasks=["Eligible task."])
        with _patched_projects({"paused": paused, "active": active}):
            result = evaluate_project_selection()
    assert result["selected_project_id"] == "active"
    assert "paused" in result["blocked_projects"]


def test_no_silent_selection_of_ineligible_requested_project():
    from NEXUS.project_routing import select_project_for_workflow

    with _local_test_dir() as tmp:
        blocked = tmp / "blocked"
        blocked.mkdir()
        _write_state(
            blocked,
            active_project="blocked",
            tasks=["Blocked task."],
            governance_status="review_required",
            governance_result={
                "governance_status": "review_required",
                "resolution_state": "pause",
                "routing_outcome": "pause",
                "reason": "Governance pause required.",
            },
        )
        with _patched_projects({"blocked": blocked}):
            result = select_project_for_workflow(requested_project_id="blocked", user_input="work on blocked")
    assert result["status"] == "blocked"
    assert result["selected_project_id"] == "blocked"
    assert result["routing_outcome"] == "defer"
    assert result["eligible_projects"] == []


def test_selection_propagates_to_state_and_dashboard_summaries():
    from NEXUS.project_routing import evaluate_project_selection
    from NEXUS.project_state import load_project_state, update_project_state_fields
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    with _local_test_dir() as tmp:
        alpha = tmp / "alpha"
        beta = tmp / "beta"
        alpha.mkdir()
        beta.mkdir()
        _write_state(alpha, active_project="alpha", tasks=["Alpha task."], execution_package_id="pkg-alpha")
        _write_state(
            beta,
            active_project="beta",
            tasks=["Beta task."],
            governance_status="review_required",
            governance_result={
                "governance_status": "review_required",
                "resolution_state": "pause",
                "routing_outcome": "pause",
                "reason": "Beta paused.",
            },
        )
        with _patched_projects({"alpha": alpha, "beta": beta}):
            selection = evaluate_project_selection()
            update_project_state_fields(
                str(alpha),
                project_selection_status=selection.get("status"),
                project_selection_result=selection,
            )
            state = load_project_state(str(alpha))
            dashboard = build_registry_dashboard_summary()
    assert state["project_selection_status"] == "selected"
    assert state["project_selection_result"]["selected_project_id"] == "alpha"
    summary = dashboard["project_selection_summary"]
    assert summary["selected_project_id"] == "alpha"
    assert summary["eligible_project_count"] == 1
    assert summary["blocked_project_count"] == 1
    assert summary["contention_detected"] is False
    assert dashboard["project_autonomy_routing_summary"]["last_project_selection_reason_by_project"]["alpha"]


def main():
    tests = [
        test_single_eligible_project_selected,
        test_multiple_eligible_projects_contention_resolves_deterministically,
        test_blocked_project_excluded_from_selection,
        test_paused_or_stopped_project_excluded_from_selection,
        test_no_silent_selection_of_ineligible_requested_project,
        test_selection_propagates_to_state_and_dashboard_summaries,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
