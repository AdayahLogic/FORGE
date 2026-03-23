"""
Phase 61 distributed execution foundations tests.

Run: python tests/phase61_distributed_execution_foundations_test.py
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
    path = base / f"phase61_{uuid.uuid4().hex[:8]}"
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
            "description": f"Phase 61 temp project {key}",
        }
        for key, path in projects.items()
    }
    with ExitStack() as stack:
        stack.enter_context(patch.dict("NEXUS.registry.PROJECTS", project_map, clear=True))
        stack.enter_context(patch.dict("NEXUS.project_routing.PROJECTS", project_map, clear=True))
        stack.enter_context(patch.dict("NEXUS.registry_dashboard.PROJECTS", project_map, clear=True))
        yield


def _write_state(project_path: Path, *, active_project: str, dispatch_status: str = "accepted", dispatch_result: dict | None = None):
    from NEXUS.project_state import save_project_state

    queue = [
        {
            "id": "task-1",
            "type": "implementation_step",
            "payload": {"description": "Runtime target test task."},
            "priority": 0,
            "status": "pending",
            "task": "Runtime target test task.",
        }
    ]

    save_project_state(
        project_path=str(project_path),
        active_project=active_project,
        notes="",
        architect_plan={"objective": "Phase 61 target-selection propagation test."},
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
        agent_routing_summary={"runtime_node": "coder", "agent_name": "coder", "tool_name": "diff_patch"},
        execution_bridge_report_path=None,
        execution_bridge_summary={
            "runtime_node": "coder",
            "selected_runtime_target": "cursor",
            "runtime_selection_status": "selected",
            "runtime_selection_reason": "Repo-aware code editing inferred; Cursor is the governed target.",
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
        dispatch_plan_summary={"dispatch_planning_status": "planned", "ready_for_dispatch": True, "runtime_target_id": "cursor", "runtime_node": "coder", "task_type": "coder"},
        dispatch_status=dispatch_status,
        dispatch_result=dispatch_result or {},
        runtime_execution_status=(dispatch_result or {}).get("execution_status"),
        governance_status="ok",
        governance_result={"governance_status": "ok", "resolution_state": "resolved", "routing_outcome": "continue"},
        enforcement_status="ok",
        enforcement_result={"enforcement_status": "ok"},
        project_lifecycle_status="active",
        project_lifecycle_result={"lifecycle_status": "active"},
        guardrail_status="passed",
        guardrail_result={"guardrail_status": "passed", "launch_allowed": True},
        autonomy_mode="assisted_autopilot",
        autonomy_mode_status="active",
        autonomy_mode_reason="Phase 61 fixture.",
        allowed_actions=["prepare_package"],
        blocked_actions=["unbounded_loop"],
        escalation_threshold="low",
        approval_required_actions=["project_switch"],
        project_routing_status="idle",
        project_routing_result={},
        run_id=f"run-{active_project}",
    )


def _dispatch_plan(project_path: str, runtime_target_id: str | None) -> dict:
    execution = {
        "execution_mode": "targeted_runtime",
        "runtime_target_name": runtime_target_id or "",
        "requires_human_approval": False,
        "can_execute": True,
    }
    if runtime_target_id is not None:
        execution["runtime_target_id"] = runtime_target_id
    return {
        "dispatch_version": "1.0",
        "dispatch_planning_status": "planned",
        "ready_for_dispatch": True,
        "project": {"project_name": "phase61proj", "project_path": project_path},
        "request": {"request_type": "user_request", "task_type": "coder", "summary": "Dispatch a governed action.", "priority": "normal"},
        "routing": {"runtime_node": "coder", "agent_name": "coder", "tool_name": "diff_patch", "selection_status": "selected", "selection_reason": "Phase 61 dispatch."},
        "execution": execution,
        "governance": {"approval_status": "not_required", "risk_level": "low"},
        "artifacts": {"expected_outputs": ["execution package"], "target_files": ["src/module.py"]},
        "timestamps": {"planned_at": "2026-03-23T00:00:00+00:00"},
    }


def test_single_eligible_target_selected():
    from NEXUS.runtime_target_selector import select_runtime_target

    result = select_runtime_target(agent_name="architect", task_type="planning")
    assert result["status"] == "selected"
    assert result["selected_target_id"] == "local"
    assert result["capability_match"] is True
    assert result["readiness_status"] == "ready"


def test_unavailable_target_denied_with_trace():
    from NEXUS.runtime_target_selector import select_runtime_target

    result = select_runtime_target(requested_target_id="remote_worker")
    assert result["status"] == "unavailable"
    assert result["selected_target_id"] == ""
    assert result["denial_reason"] == "target_not_active"
    assert result["governance_trace"]["target_evaluations"]["remote_worker"]["readiness_status"] == "planned_only"


def test_unsuitable_capability_target_denied():
    from NEXUS.runtime_target_selector import select_runtime_target

    result = select_runtime_target(requested_target_id="local", task_type="review_package", action_type="review_package")
    assert result["status"] == "denied"
    assert result["denial_reason"] == "capability_mismatch"
    assert result["capability_match"] is False


def test_multiple_eligible_targets_resolve_deterministically():
    from NEXUS.runtime_target_selector import select_runtime_target

    result = select_runtime_target(candidate_target_ids=["codex", "cursor"])
    assert result["status"] == "selected"
    assert result["selected_target_id"] == "cursor"
    assert result["candidate_target_ids"] == ["cursor", "codex"]


def test_dispatcher_never_silently_selects_invalid_target():
    from NEXUS.runtime_dispatcher import dispatch

    with _local_test_dir() as tmp:
        result = dispatch(_dispatch_plan(str(tmp), "remote_worker"))
    assert result["dispatch_status"] == "blocked"
    selection = result["dispatch_result"]["runtime_target_selection"]
    assert selection["status"] == "denied"
    assert selection["selected_target_id"] == ""
    assert selection["denial_reason"] == "capability_mismatch"
    assert result["runtime_target"] == "remote_worker"


def test_selection_propagates_to_routing_and_dashboard_summaries():
    from NEXUS.project_routing import build_project_routing_decision
    from NEXUS.project_state import load_project_state
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    with _local_test_dir() as tmp:
        alpha = tmp / "alpha"
        alpha.mkdir()
        dispatch_result = {
            "runtime": "cursor",
            "status": "accepted",
            "execution_status": "queued",
            "runtime_target_selection": {
                "status": "selected",
                "selected_target_id": "cursor",
                "candidate_target_ids": ["cursor"],
                "target_type": "ide",
                "capability_match": True,
                "readiness_status": "ready",
                "availability_status": "available",
                "denial_reason": "",
                "selection_reason": "Repo-aware code editing inferred; Cursor is the governed target.",
                "routing_outcome": "continue",
                "governance_trace": {"target_evaluations": {"cursor": {"eligible": True}}},
                "recorded_at": "2026-03-23T00:00:00",
            },
        }
        _write_state(alpha, active_project="alpha", dispatch_result=dispatch_result)
        with _patched_projects({"alpha": alpha}):
            state = load_project_state(str(alpha))
            routing = build_project_routing_decision(project_key="alpha", state=state)
            dashboard = build_registry_dashboard_summary()
    assert routing["runtime_target_selection"]["selected_target_id"] == "cursor"
    summary = dashboard["runtime_target_selection_summary"]
    assert summary["selected_target_by_project"]["alpha"] == "cursor"
    assert summary["readiness_status_by_project"]["alpha"] == "ready"
    assert summary["availability_status_by_project"]["alpha"] == "available"
    assert summary["last_selection_reason_by_project"]["alpha"]


def main():
    tests = [
        test_single_eligible_target_selected,
        test_unavailable_target_denied_with_trace,
        test_unsuitable_capability_target_denied,
        test_multiple_eligible_targets_resolve_deterministically,
        test_dispatcher_never_silently_selects_invalid_target,
        test_selection_propagates_to_routing_and_dashboard_summaries,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
