"""
Phase 95 autonomous portfolio operator + continuous intelligence loop tests.

Run: python tests/phase95_autonomous_portfolio_operator_test.py
"""

from __future__ import annotations

import shutil
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@contextmanager
def _local_test_dir(prefix: str):
    base = ROOT / ".tmp_test_runs"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{prefix}_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@contextmanager
def _registered_projects(project_paths: dict[str, Path]):
    from NEXUS.registry import PROJECTS

    added_keys: list[str] = []
    for key, path in project_paths.items():
        project_key = str(key).strip().lower()
        PROJECTS[project_key] = {
            "name": project_key,
            "path": str(path),
            "description": f"Phase 95 temp project {project_key}",
            "workspace_type": "internal",
            "agents": ["coder", "tester", "operator"],
        }
        added_keys.append(project_key)
    try:
        yield added_keys
    finally:
        for key in added_keys:
            PROJECTS.pop(key, None)


def _run(name: str, fn):
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except Exception as exc:
        print(f"FAIL: {name} - {exc}")
        return False


def _write_state(project_path: Path, project_name: str, tasks: list[str]):
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
        active_project=project_name,
        notes="phase95 fixture",
        architect_plan={"objective": "exercise autonomous portfolio operator", "implementation_steps": list(tasks)},
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
        agent_routing_summary={"runtime_node": "coder", "agent_name": "coder", "tool_name": "cursor_agent"},
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
        governance_result={"governance_status": "ok", "resolution_state": "resolved", "routing_outcome": "continue"},
        enforcement_status="ok",
        enforcement_result={"enforcement_status": "ok"},
        guardrail_status="passed",
        guardrail_result={"guardrail_status": "passed", "launch_allowed": True},
        autonomy_mode="assisted_autopilot",
        autonomy_mode_status="active",
        autonomy_mode_reason="phase95 fixture",
        allowed_actions=["prepare_package", "decision", "execute", "project_switch"],
        blocked_actions=["unbounded_loop", "policy_self_modification", "mode_self_escalation"],
        escalation_threshold="guarded",
        approval_required_actions=["release", "handoff", "execute", "project_switch"],
        project_routing_status="idle",
        project_routing_result={},
        run_id=f"run-{project_name}",
    )


def _seed_autopilot_ready(project_path: Path, project_key: str):
    from NEXUS.autonomy_modes import get_mode_stop_rail_config
    from NEXUS.project_state import update_project_state_fields

    started = datetime.now(timezone.utc).isoformat()
    config = get_mode_stop_rail_config("assisted_autopilot")
    update_project_state_fields(
        str(project_path),
        autopilot_status="ready",
        autopilot_session_id=f"sess-{uuid.uuid4().hex[:6]}",
        autopilot_project_key=project_key,
        autopilot_mode="assisted_autopilot",
        autopilot_iteration_count=0,
        autopilot_iteration_limit=int(config.get("max_loops") or 3),
        autopilot_started_at=started,
        autopilot_updated_at=started,
        autopilot_last_package_id="",
        autopilot_last_result={},
        autopilot_next_action="run",
        autopilot_stop_reason="",
        autopilot_escalation_reason="",
        autopilot_progress_summary={},
        autopilot_retry_count=0,
        autopilot_retry_limit=int(config.get("max_retries") or 2),
        autopilot_operation_count=0,
        autopilot_operation_limit=int(config.get("max_operations") or 16),
        autopilot_runtime_started_at=started,
        autopilot_runtime_limit_seconds=int(config.get("max_runtime_seconds") or 1800),
        autonomy_stop_rail_config=config,
        autonomy_current_counts={"loops": 0, "retries": 0, "runtime_seconds": 0, "operations": 0, "budget_units": 0},
        autonomy_stop_rail_status="ok",
        autonomy_stop_rail_result={},
        autonomy_governance_trace={},
    )


def test_continuous_loop_stability_is_bounded_interruptible_observable():
    from NEXUS.autonomous_portfolio_operator import run_autonomous_portfolio_loop_safe, set_portfolio_kill_switch_safe

    set_portfolio_kill_switch_safe(enabled=False, reason="phase95_reset", source="test")
    with _local_test_dir("phase95_a") as p1, _local_test_dir("phase95_b") as p2:
        _write_state(p1, "phase95a", ["A1", "A2"])
        _write_state(p2, "phase95b", ["B1"])
        with _registered_projects({"phase95a": p1, "phase95b": p2}):
            result = run_autonomous_portfolio_loop_safe(
                max_ticks=2,
                max_runtime_seconds=30,
                max_operations=20,
                execute_actions=False,
                parallel_capacity=2,
                trigger="phase95_test",
            )
            assert result["bounded"] is True
            assert result["interruptible"] is True
            assert result["observable"] is True
            assert result["ticks_run"] == 2
            assert len(result["tick_results"]) == 2


def test_mission_generation_and_allocation_prioritizes_high_value_work():
    from NEXUS.autonomous_portfolio_operator import run_autonomous_portfolio_tick_safe

    with _local_test_dir("phase95_c") as p1, _local_test_dir("phase95_d") as p2:
        _write_state(p1, "phase95c", ["high value task"])
        _write_state(p2, "phase95d", [])
        with _registered_projects({"phase95c": p1, "phase95d": p2}):
            result = run_autonomous_portfolio_tick_safe(
                execute_actions=False,
                parallel_capacity=1,
                intelligence_signals={"high_value_projects": ["phase95c"], "low_value_projects": ["phase95d"]},
                trigger="phase95_allocation",
            )
            alloc = result["allocation_result"]["allocations_by_project"]
            assert alloc.get("phase95c") == 1
            assert alloc.get("phase95d") == 0
            executable = result["conflict_result"]["executable_missions"]
            assert len(executable) <= 1
            assert executable and executable[0]["project_id"] == "phase95c"


def test_parallel_execution_respects_capacity_and_defers_overflow():
    from NEXUS.autonomous_portfolio_operator import run_autonomous_portfolio_tick_safe

    with _local_test_dir("phase95_e") as p1, _local_test_dir("phase95_f") as p2, _local_test_dir("phase95_g") as p3:
        _write_state(p1, "phase95e", ["E1"])
        _write_state(p2, "phase95f", ["F1"])
        _write_state(p3, "phase95g", ["G1"])
        with _registered_projects({"phase95e": p1, "phase95f": p2, "phase95g": p3}):
            result = run_autonomous_portfolio_tick_safe(
                execute_actions=False,
                parallel_capacity=2,
                intelligence_signals={"high_value_projects": ["phase95e", "phase95f", "phase95g"]},
                trigger="phase95_parallel",
            )
            executable = result["conflict_result"]["executable_missions"]
            deferred = result["conflict_result"]["deferred_missions"]
            assert len(executable) <= 2
            assert len(deferred) >= 1


def test_conflict_resolution_resolves_collisions_and_reports_conflicts():
    from NEXUS.autonomous_portfolio_operator import resolve_mission_conflicts_safe

    missions = [
        {
            "mission_id": "m1",
            "project_id": "phase95h",
            "priority_score": 0.7,
            "strategy_group": "throughput",
        },
        {
            "mission_id": "m2",
            "project_id": "phase95h",
            "priority_score": 0.9,
            "strategy_group": "risk_mitigation",
        },
    ]
    result = resolve_mission_conflicts_safe(
        missions=missions,
        allocation_result={"allocations_by_project": {"phase95h": 1}},
        parallel_capacity=1,
    )
    assert result["conflict_status"] in {"resolved_with_conflicts", "ok"}
    assert len(result["executable_missions"]) == 1
    assert result["executable_missions"][0]["mission_id"] == "m2"
    assert len(result["conflicts"]) >= 1


def test_escalation_and_kill_switch_behavior_are_explicit():
    from NEXUS.autonomous_portfolio_operator import run_autonomous_portfolio_tick_safe

    result = run_autonomous_portfolio_tick_safe(
        execute_actions=False,
        operator_controls={"kill_switch_enabled": True, "kill_switch_reason": "phase95_test_stop"},
        trigger="phase95_escalation",
    )
    assert result["tick_status"] == "stopped"
    assert result["stop_reason"] == "kill_switch_enabled"
    assert len(result["escalations"]) >= 1
    assert "kill switch" in str(result["escalations"][0]["what_happened"]).lower()


def test_allocation_enforcement_applies_real_pause_behavior():
    from NEXUS.autonomous_portfolio_operator import enforce_portfolio_allocations_safe
    from NEXUS.project_state import load_project_state

    with _local_test_dir("phase95_h") as p1:
        _write_state(p1, "phase95h", ["active task"])
        with _registered_projects({"phase95h": p1}):
            _seed_autopilot_ready(p1, "phase95h")
            loaded_before = load_project_state(str(p1))
            assert loaded_before.get("autopilot_status") == "ready"
            enforcement = enforce_portfolio_allocations_safe(
                states_by_project={"phase95h": loaded_before},
                allocation_result={"allocations_by_project": {"phase95h": 0}},
                execute_actions=True,
            )
            loaded_after = load_project_state(str(p1))
            assert enforcement["enforcement_status"] in {"enforced", "simulated"}
            assert loaded_after.get("autopilot_status") == "paused"


def test_kill_switch_halts_continuous_loop_immediately():
    from NEXUS.autonomous_portfolio_operator import run_autonomous_portfolio_loop_safe, set_portfolio_kill_switch_safe

    set_portfolio_kill_switch_safe(enabled=True, reason="phase95_loop_halt", source="test")
    try:
        result = run_autonomous_portfolio_loop_safe(
            max_ticks=4,
            max_runtime_seconds=60,
            execute_actions=False,
            trigger="phase95_kill_loop",
        )
        assert result["loop_status"] == "stopped"
        assert result["stop_reason"] == "kill_switch_enabled"
        assert result["ticks_run"] == 0
    finally:
        set_portfolio_kill_switch_safe(enabled=False, reason="phase95_cleanup", source="test")


def main():
    tests = [
        test_continuous_loop_stability_is_bounded_interruptible_observable,
        test_mission_generation_and_allocation_prioritizes_high_value_work,
        test_parallel_execution_respects_capacity_and_defers_overflow,
        test_conflict_resolution_resolves_collisions_and_reports_conflicts,
        test_escalation_and_kill_switch_behavior_are_explicit,
        test_allocation_enforcement_applies_real_pause_behavior,
        test_kill_switch_halts_continuous_loop_immediately,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
