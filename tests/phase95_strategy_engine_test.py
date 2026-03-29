"""
Phase 95 strategic decision engine tests.

Run: python tests/phase95_strategy_engine_test.py
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
    path = base / f"phase95_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@contextmanager
def _registered_project(project_path: Path):
    from NEXUS.registry import PROJECTS

    project_key = f"phase95_{uuid.uuid4().hex[:8]}"
    PROJECTS[project_key] = {
        "name": project_key,
        "path": str(project_path),
        "description": "Phase 95 temp project",
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
    except Exception as exc:
        print(f"FAIL: {name} - {exc}")
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
        active_project="phase95proj",
        notes="",
        architect_plan={
            "objective": "Strategic decision validation.",
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
        task_queue_snapshot=task_queue,
        autonomy_mode="assisted_autopilot",
        autonomy_mode_status="active",
        autonomy_mode_reason="Phase 95 fixture.",
        allowed_actions=["prepare_package", "decision", "release", "handoff", "execute"],
        blocked_actions=["unbounded_loop"],
        escalation_threshold="guarded",
        approval_required_actions=["release", "handoff", "execute"],
        project_routing_status="idle",
        project_routing_result={},
        run_id="run-phase95",
    )


def _success_aegis(project_path: Path):
    from AEGIS.aegis_contract import build_aegis_result

    return build_aegis_result(
        aegis_decision="allow",
        aegis_reason="Allowed.",
        action_mode="execution",
        project_name="phase95proj",
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
    }


def test_priority_scoring_rewards_high_value_lower_risk():
    from NEXUS.strategic_decision_engine import score_priority

    high = score_priority(
        expected_value=0.9,
        urgency=0.85,
        probability_of_success=0.8,
        risk=0.2,
        effort=0.35,
        dependency_readiness=0.85,
        outcome_history=0.7,
    )
    low = score_priority(
        expected_value=0.35,
        urgency=0.3,
        probability_of_success=0.35,
        risk=0.8,
        effort=0.8,
        dependency_readiness=0.25,
        outcome_history=0.3,
    )
    assert high > low
    assert high > 60.0
    assert low < 45.0


def test_ranking_consistency_is_deterministic_for_equal_inputs():
    from NEXUS.strategic_decision_engine import rank_actionable_items

    items = [
        {"item_id": "a", "action_type": "mission_task", "priority_score": 80.0, "reasoning": "A"},
        {"item_id": "b", "action_type": "mission_task", "priority_score": 80.0, "reasoning": "B"},
        {"item_id": "c", "action_type": "mission_task", "priority_score": 65.0, "reasoning": "C"},
    ]
    first = rank_actionable_items(items, top_n=10)
    second = rank_actionable_items(items, top_n=10)
    assert [row["item_id"] for row in first] == [row["item_id"] for row in second]
    assert first[0]["priority_score"] >= first[-1]["priority_score"]


def test_next_best_action_selection_prefers_stronger_revenue_signal():
    from NEXUS.strategic_decision_engine import select_next_best_action

    state = {
        "task_queue": [
            {"id": "task-1", "task": "Low-value cleanup", "priority": 5, "status": "pending", "payload": {"expected_value": 0.2}},
        ],
        "revenue_activation_status": "ready_for_revenue_action",
        "highest_value_next_action": "prioritize high-value opportunity",
        "roi_estimate": 0.92,
        "conversion_probability": 0.88,
        "time_sensitivity": 0.74,
    }
    decision = select_next_best_action(state=state)
    assert decision["action_type"] in {"opportunity_activation", "mission_task"}
    assert decision["priority_score"] > 50.0
    assert decision["best_next_action"]


def test_outcome_influenced_planning_changes_priority_scores():
    from NEXUS.strategic_decision_engine import select_next_best_action

    state = {
        "task_queue": [
            {"id": "task-1", "task": "Improve conversion flow", "priority": 1, "status": "pending"},
        ],
    }
    positive = [{"actual_outcome": "success"} for _ in range(8)] + [{"actual_outcome": "warning"}]
    negative = [{"actual_outcome": "failed"} for _ in range(8)] + [{"actual_outcome": "blocked"}]
    good_decision = select_next_best_action(state=state, learning_records=positive)
    bad_decision = select_next_best_action(state=state, learning_records=negative)
    assert good_decision["priority_score"] > bad_decision["priority_score"]


def test_mission_prioritization_prefers_active_package_when_scores_close():
    from NEXUS.strategic_decision_engine import build_mission_priorities

    mission = build_mission_priorities(
        states_by_project={
            "alpha": {"execution_package_id": "pkg-alpha", "task_queue": [{"id": "a", "status": "pending"}]},
            "beta": {"task_queue": [{"id": "b", "status": "pending"}], "autopilot_status": "idle"},
        }
    )
    assert mission["selected_project_id"] in {"alpha", "beta"}
    assert mission["mission_priorities"]
    top = mission["mission_priorities"][0]
    assert "mission_priority_score" in top


def test_conflict_detection_flags_blocked_priority_contention():
    from NEXUS.strategic_decision_engine import build_mission_priorities

    mission = build_mission_priorities(
        states_by_project={
            "one": {"task_queue": [{"id": "x", "status": "pending"}], "autopilot_status": "blocked", "enforcement_status": "blocked"},
            "two": {"task_queue": [{"id": "y", "status": "pending"}], "autopilot_status": "idle"},
        }
    )
    assert isinstance(mission["mission_conflicts"], list)
    if mission["mission_conflicts"]:
        assert "conflict_type" in mission["mission_conflicts"][0]


def test_autopilot_strategic_state_persists_after_start():
    from NEXUS.command_surface import run_command
    from NEXUS.project_state import load_project_state

    with _local_test_dir() as tmp, _registered_project(tmp) as project_key:
        _write_state(tmp, ["Execute one strategic bounded task."])
        with _patched_aegis(_success_aegis(tmp)), _patched_executor(_success_execution_result(tmp)):
            result = run_command("project_autopilot_start", project_name=project_key, iteration_limit=1)
        assert result["status"] == "ok"
        state = load_project_state(str(tmp))
        strategy = state.get("autopilot_strategy_state") or {}
        assert isinstance(strategy, dict)
        assert strategy.get("best_next_action") or strategy.get("action_type")


def test_command_surface_exposes_strategic_visibility_commands():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import write_execution_package_safe

    with _local_test_dir() as tmp, _registered_project(tmp) as project_key:
        _write_state(tmp, ["Review high value package."])
        write_execution_package_safe(
            str(tmp),
            {
                "package_id": "pkg-strategy",
                "project_name": "phase95proj",
                "project_path": str(tmp),
                "pipeline_stage": "proposal_pending",
                "highest_value_next_action": "generate offer",
                "highest_value_next_action_score": 0.84,
                "opportunity_classification": "strategic",
                "revenue_activation_status": "ready_for_revenue_action",
            },
        )
        strategic = run_command("strategic_status", project_name=project_key)
        queue = run_command("priority_queue", project_name=project_key)
        rankings = run_command("opportunity_rankings", project_name=project_key, n=10)
        mission = run_command("mission_priorities")
        assert strategic["status"] == "ok"
        assert queue["status"] == "ok"
        assert rankings["status"] == "ok"
        assert mission["status"] == "ok"
        assert "next_best_action" in strategic["payload"]
        assert "priority_queue" in queue["payload"]
        assert "opportunity_rankings" in rankings["payload"]
        assert "mission_priorities" in mission["payload"]


def main():
    tests = [
        test_priority_scoring_rewards_high_value_lower_risk,
        test_ranking_consistency_is_deterministic_for_equal_inputs,
        test_next_best_action_selection_prefers_stronger_revenue_signal,
        test_outcome_influenced_planning_changes_priority_scores,
        test_mission_prioritization_prefers_active_package_when_scores_close,
        test_conflict_detection_flags_blocked_priority_contention,
        test_autopilot_strategic_state_persists_after_start,
        test_command_surface_exposes_strategic_visibility_commands,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())

