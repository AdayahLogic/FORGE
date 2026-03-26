"""
Phase 103-106 mission-based supervised autonomy tests.

Run: python tests/phase103_106_mission_supervised_autonomy_test.py
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
    path = base / f"phase103_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@contextmanager
def _registered_project(project_path: Path):
    from NEXUS.registry import PROJECTS

    project_key = f"phase103_{uuid.uuid4().hex[:8]}"
    PROJECTS[project_key] = {
        "name": project_key,
        "path": str(project_path),
        "description": "Phase 103 temp project",
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
    except Exception as exc:
        print(f"FAIL: {name} - {exc}")
        return False


def _write_state(project_path: Path):
    from NEXUS.project_state import save_project_state

    save_project_state(
        project_path=str(project_path),
        active_project="phase103proj",
        notes="phase103 fixture",
        architect_plan={"objective": "Implement bounded autonomy slice."},
        task_queue=[
            {
                "id": "task-1",
                "type": "implementation_step",
                "payload": {"description": "Implement mission packet."},
                "priority": 0,
                "status": "pending",
                "task": "Implement mission packet.",
            }
        ],
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
        execution_bridge_summary={
            "runtime_node": "coder",
            "selected_runtime_target": "local",
            "fallback_runtime_target": "local",
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
        run_id="run-phase103",
    )


def test_mission_packet_is_bounded_and_auditable():
    from NEXUS.mission_system import build_mission_packet

    mission = build_mission_packet(
        mission_id="msn-test",
        task={"type": "implementation_step", "payload": {"description": "Implement code path."}},
    )
    assert mission["mission_id"] == "msn-test"
    assert mission["mission_scope_boundary"]["scope_type"] == "bounded_task_packet"
    assert "auto_merge" in mission["mission_forbidden_actions"]
    assert "codex" in mission["mission_allowed_executors"]
    assert mission["mission_requires_initial_approval"] is True
    assert mission["mission_requires_final_approval"] is True


def test_executor_router_is_deterministic_and_openclaw_honest():
    from NEXUS.executor_router import route_executor

    code_route = route_executor(task_summary="Refactor code and run tests.")
    assert code_route["executor_task_type"] == "coding_repo_implementation"
    assert code_route["executor_route"] == "codex"

    browser_route = route_executor(task_summary="Open browser and click UI button.")
    assert browser_route["executor_task_type"] == "browser_ui_computer_use"
    assert browser_route["executor_route"] == "openclaw"
    assert browser_route["executor_route_status"] in {"routed", "readiness_limited"}
    if browser_route["executor_route_status"] == "readiness_limited":
        assert "not dispatch-ready" in browser_route["executor_route_reason"]


def test_stop_conditions_escalate_safely():
    from NEXUS.mission_system import evaluate_mission_stop_conditions

    result = evaluate_mission_stop_conditions(
        {
            "scope_expansion_required": False,
            "governance_hard_block": True,
            "credentials_required_unexpectedly": False,
            "executor_critical_failure": False,
            "risky_external_action_out_of_scope": False,
            "repo_safety_cannot_be_maintained": False,
        }
    )
    assert result["mission_stop_condition_hit"] is True
    assert result["mission_escalation_required"] is True
    assert result["mission_stop_condition_reason"] == "governance_hard_block"


def test_review_queue_mission_level_approval_shape():
    from NEXUS.review_queue import build_review_queue_entry_safe

    queued = build_review_queue_entry_safe(
        active_project="proj",
        run_id="run-1",
        mission_status="awaiting_initial_approval",
        mission_id="msn-1",
        mission_title="Bounded mission",
        mission_risk_level="high",
        mission_requires_initial_approval=True,
        mission_requires_final_approval=True,
    )
    assert queued["queue_type"] == "mission_initial_approval"
    assert queued["approval_queue_item_type"] == "mission_initial_approval"
    assert queued["approval_queue_requires_initial_approval"] is True
    assert queued["approval_queue_batchable"] is True


def test_execution_package_surfaces_include_mission_executor_fields():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import write_execution_package_safe

    with _local_test_dir() as tmp:
        _write_state(tmp)
        write_execution_package_safe(
            str(tmp),
            {
                "package_id": "pkg-phase103",
                "project_name": "phase103proj",
                "project_path": str(tmp),
                "created_at": "2026-03-26T00:00:00Z",
                "package_status": "review_pending",
                "review_status": "pending",
                "mission_id": "msn-42",
                "mission_type": "project_delivery",
                "mission_title": "Implement bounded feature",
                "mission_status": "awaiting_initial_approval",
                "mission_risk_level": "medium",
                "executor_route": "codex",
                "executor_route_status": "routed",
                "executor_task_type": "coding_repo_implementation",
                "approval_queue_item_type": "mission_initial_approval",
                "approval_queue_risk_class": "medium",
                "approval_queue_requires_initial_approval": True,
                "approval_queue_requires_final_approval": True,
                "autopilot_status": "awaiting_approval",
                "autopilot_loop_state": "awaiting_approval",
                "mission_stop_condition_hit": False,
            },
        )
        queue = run_command("execution_package_queue", project_path=str(tmp), n=10)
        assert queue["status"] == "ok"
        rows = queue["payload"]["packages"]
        assert rows and rows[0]["mission_id"] == "msn-42"
        assert rows[0]["executor_route"] == "codex"
        assert "mission_queue_summary" in queue["payload"]

        details = run_command("execution_package_details", project_path=str(tmp), execution_package_id="pkg-phase103")
        assert details["status"] == "ok"
        header = details["payload"]["review_header"]
        assert header["autopilot_status"] == "awaiting_approval"
        assert header["mission_status"] == "awaiting_initial_approval"
        assert header["executor_route"] == "codex"


def test_autopilot_toggle_state_is_safe_and_explicit():
    from NEXUS.command_surface import run_command
    from NEXUS.project_state import load_project_state

    with _local_test_dir() as tmp, _registered_project(tmp) as project_key:
        _write_state(tmp)
        started = run_command("project_autopilot_start", project_name=project_key, iteration_limit=1)
        assert started["status"] in {"ok", "error"}
        status = run_command("project_autopilot_status", project_name=project_key)
        assert status["status"] == "ok"
        autopilot = status["payload"]["autopilot"]
        assert "autopilot_enabled" in autopilot
        assert "autopilot_loop_state" in autopilot
        stopped = run_command("project_autopilot_stop", project_name=project_key)
        assert stopped["status"] == "ok"
        loaded = load_project_state(str(tmp))
        assert loaded.get("autopilot_enabled") is False
        assert loaded.get("autopilot_loop_state") in {"off", "idle"}


def main():
    tests = [
        test_mission_packet_is_bounded_and_auditable,
        test_executor_router_is_deterministic_and_openclaw_honest,
        test_stop_conditions_escalate_safely,
        test_review_queue_mission_level_approval_shape,
        test_execution_package_surfaces_include_mission_executor_fields,
        test_autopilot_toggle_state_is_safe_and_explicit,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
