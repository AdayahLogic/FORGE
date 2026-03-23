"""
Phase 59 autonomy stop-rails tests.

Run: python tests/phase59_autonomy_stop_rails_test.py
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
def _local_test_dir():
    base = ROOT / ".tmp_test_runs"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"phase59_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@contextmanager
def _registered_project(project_path: Path):
    from NEXUS.registry import PROJECTS

    project_key = f"phase59_{uuid.uuid4().hex[:8]}"
    PROJECTS[project_key] = {
        "name": project_key,
        "path": str(project_path),
        "description": "Phase 59 temp project",
        "workspace_type": "internal",
        "agents": ["coder", "tester"],
    }
    try:
        yield project_key
    finally:
        PROJECTS.pop(project_key, None)


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
        active_project="phase59proj",
        notes="",
        architect_plan={
            "objective": "Exercise stop-rails without unbounded continuation.",
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
        governance_result={"governance_status": "ok", "resolution_state": "resolved", "routing_outcome": "continue"},
        enforcement_status="ok",
        enforcement_result={"enforcement_status": "ok"},
        guardrail_status="passed",
        guardrail_result={"guardrail_status": "passed", "launch_allowed": True},
        autonomy_mode="supervised_build",
        autonomy_mode_status="active",
        autonomy_mode_reason="Phase 59 default fixture.",
        allowed_actions=["prepare_package", "recommend_next_step", "bounded_low_risk_step"],
        blocked_actions=["unbounded_loop", "policy_self_modification", "mode_self_escalation"],
        escalation_threshold="low",
        approval_required_actions=["decision", "release", "handoff", "execute", "project_switch"],
        project_routing_status="idle",
        project_routing_result={},
        run_id="run-phase59",
    )


def _seed_autopilot(
    project_path: Path,
    *,
    project_key: str,
    autonomy_mode: str,
    iteration_count: int = 0,
    iteration_limit: int = 1,
    retry_count: int = 0,
    retry_limit: int = 1,
    operation_count: int = 0,
    operation_limit: int = 8,
    runtime_started_at: str | None = None,
    runtime_limit_seconds: int = 900,
):
    from NEXUS.autonomy_modes import get_mode_stop_rail_config
    from NEXUS.project_state import update_project_state_fields

    config = get_mode_stop_rail_config(autonomy_mode)
    config["max_loops"] = iteration_limit
    config["max_retries"] = retry_limit
    config["max_runtime_seconds"] = runtime_limit_seconds
    config["max_operations"] = operation_limit
    config["max_budget_units"] = operation_limit
    counts = {
        "loops": iteration_count,
        "retries": retry_count,
        "runtime_seconds": 0,
        "operations": operation_count,
        "budget_units": operation_count,
    }
    runtime_anchor = runtime_started_at or datetime.now(timezone.utc).isoformat()
    update_project_state_fields(
        str(project_path),
        autopilot_status="paused",
        autopilot_session_id="sess-phase59",
        autopilot_project_key=project_key,
        autopilot_mode=autonomy_mode,
        autopilot_iteration_count=iteration_count,
        autopilot_iteration_limit=iteration_limit,
        autopilot_retry_count=retry_count,
        autopilot_retry_limit=retry_limit,
        autopilot_operation_count=operation_count,
        autopilot_operation_limit=operation_limit,
        autopilot_runtime_started_at=runtime_anchor,
        autopilot_runtime_limit_seconds=runtime_limit_seconds,
        autopilot_started_at=runtime_anchor,
        autopilot_updated_at=runtime_anchor,
        autopilot_next_action="resume",
        autonomy_mode=autonomy_mode,
        autonomy_mode_status="active",
        autonomy_stop_rail_config=config,
        autonomy_current_counts=counts,
        autonomy_stop_rail_status="ok",
        autonomy_stop_rail_result={},
        autonomy_governance_trace={},
    )


def test_mode_defaults_are_bounded_for_all_autonomy_modes():
    from NEXUS.autonomy_modes import AUTONOMY_MODES, build_autonomy_mode_state, get_mode_stop_rail_config

    for mode in sorted(AUTONOMY_MODES):
        config = get_mode_stop_rail_config(mode)
        state = build_autonomy_mode_state(mode=mode)
        assert config["max_loops"] > 0
        assert config["max_retries"] > 0
        assert config["max_runtime_seconds"] > 0
        assert config["max_operations"] > 0
        assert state["autonomy_stop_rail_config"]["autonomy_mode"] == mode


def test_loop_limit_reached_emits_explicit_pause_outcome():
    from NEXUS.project_autopilot import resume_project_autopilot
    from NEXUS.project_state import load_project_state
    from NEXUS.project_routing import build_project_routing_decision

    with _local_test_dir() as tmp, _registered_project(tmp) as project_key:
        _write_state(tmp, ["Task one.", "Task two."])
        _seed_autopilot(tmp, project_key=project_key, autonomy_mode="supervised_build", iteration_count=1, iteration_limit=1)
        result = resume_project_autopilot(project_path=str(tmp), project_name=project_key)
        assert result["status"] == "ok"
        session = result["session"]
        assert session["autonomy_stop_rail_result"]["rail_type"] == "loops"
        assert session["autonomy_stop_rail_result"]["status"] == "paused"
        assert session["autonomy_stop_rail_result"]["routing_outcome"] == "pause"
        assert session["autopilot_status"] == "paused"
        state = load_project_state(str(tmp))
        assert state["autonomy_stop_rail_status"] == "paused"
        routing = build_project_routing_decision(project_key=project_key, state=state)
        assert routing["selected_action"] == "pause"


def test_retry_limit_reached_emits_explicit_escalate_outcome():
    from NEXUS.project_autopilot import resume_project_autopilot

    with _local_test_dir() as tmp, _registered_project(tmp) as project_key:
        _write_state(tmp, ["Retry task."])
        _seed_autopilot(
            tmp,
            project_key=project_key,
            autonomy_mode="assisted_autopilot",
            retry_count=2,
            retry_limit=2,
            iteration_count=0,
            iteration_limit=3,
        )
        result = resume_project_autopilot(project_path=str(tmp), project_name=project_key)
        session = result["session"]
        assert session["autonomy_stop_rail_result"]["rail_type"] == "retries"
        assert session["autonomy_stop_rail_result"]["status"] == "escalated"
        assert session["autonomy_stop_rail_result"]["routing_outcome"] == "escalate"
        assert session["autopilot_status"] == "escalated"


def test_runtime_limit_reached_emits_explicit_stop_outcome_without_resetting_anchor():
    from NEXUS.project_autopilot import resume_project_autopilot

    with _local_test_dir() as tmp, _registered_project(tmp) as project_key:
        _write_state(tmp, ["Runtime task."])
        _seed_autopilot(
            tmp,
            project_key=project_key,
            autonomy_mode="low_risk_autonomous_development",
            runtime_started_at="2026-03-20T00:00:00+00:00",
            runtime_limit_seconds=60,
            iteration_limit=5,
        )
        result = resume_project_autopilot(project_path=str(tmp), project_name=project_key)
        session = result["session"]
        assert session["autonomy_stop_rail_result"]["rail_type"] == "runtime"
        assert session["autonomy_stop_rail_result"]["status"] == "stopped"
        assert session["autonomy_stop_rail_result"]["routing_outcome"] == "stop"
        assert session["autopilot_status"] == "completed"
        assert session["autopilot_runtime_started_at"] == "2026-03-20T00:00:00+00:00"


def test_operations_limit_reached_propagates_to_state_and_dashboard():
    from NEXUS.project_autopilot import resume_project_autopilot
    from NEXUS.project_state import load_project_state
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    with _local_test_dir() as tmp, _registered_project(tmp) as project_key:
        _write_state(tmp, ["Operation task."])
        _seed_autopilot(
            tmp,
            project_key=project_key,
            autonomy_mode="assisted_autopilot",
            operation_count=4,
            operation_limit=4,
            iteration_limit=3,
        )
        result = resume_project_autopilot(project_path=str(tmp), project_name=project_key)
        session = result["session"]
        assert session["autonomy_stop_rail_result"]["rail_type"] == "operations"
        state = load_project_state(str(tmp))
        assert state["autonomy_stop_rail_result"]["rail_type"] == "operations"
        dashboard = build_registry_dashboard_summary()
        summary = dashboard["project_autopilot_summary"]
        assert summary["stop_rail_status_by_project"][project_key] == "escalated"
        assert summary["stop_rail_type_by_project"][project_key] == "operations"


def test_no_silent_continuation_after_rail_hit_keeps_task_pending():
    from NEXUS.project_autopilot import resume_project_autopilot
    from NEXUS.project_state import load_project_state

    with _local_test_dir() as tmp, _registered_project(tmp) as project_key:
        _write_state(tmp, ["Pending task."])
        _seed_autopilot(tmp, project_key=project_key, autonomy_mode="supervised_build", iteration_count=1, iteration_limit=1)
        result = resume_project_autopilot(project_path=str(tmp), project_name=project_key)
        assert result["session"]["autopilot_status"] == "paused"
        state = load_project_state(str(tmp))
        assert state["task_queue"][0]["status"] == "pending"
        assert state["project_routing_result"]["selected_action"] == "pause"


def test_governance_conflict_outcome_keeps_priority_over_stop_rails():
    from NEXUS.project_routing import build_project_routing_decision

    decision = build_project_routing_decision(
        project_key="phase59proj",
        state={
            "autonomy_mode": "assisted_autopilot",
            "governance_status": "review_required",
            "governance_result": {
                "governance_status": "review_required",
                "resolution_state": "pause",
                "routing_outcome": "pause",
                "reason": "Governance pause required.",
            },
            "autonomy_stop_rail_status": "escalated",
            "autonomy_stop_rail_result": {
                "status": "escalated",
                "rail_type": "retries",
                "routing_outcome": "escalate",
                "stop_reason": "autonomy_retry_limit_reached",
            },
            "task_queue_snapshot": [{"id": "t1", "task": "do thing", "status": "pending"}],
        },
    )
    assert decision["selected_action"] == "pause"
    assert decision["routing_reason"] == "Governance pause required."


def main():
    tests = [
        test_mode_defaults_are_bounded_for_all_autonomy_modes,
        test_loop_limit_reached_emits_explicit_pause_outcome,
        test_retry_limit_reached_emits_explicit_escalate_outcome,
        test_runtime_limit_reached_emits_explicit_stop_outcome_without_resetting_anchor,
        test_operations_limit_reached_propagates_to_state_and_dashboard,
        test_no_silent_continuation_after_rail_hit_keeps_task_pending,
        test_governance_conflict_outcome_keeps_priority_over_stop_rails,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
