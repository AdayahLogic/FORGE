"""
Phase 52 Forge Console control gate tests.

Run: python tests/phase52_forge_console_control_gate_test.py
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
    path = base / f"phase52_{uuid.uuid4().hex[:8]}"
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


def _write_state(project_path: Path, queue_type: str):
    from NEXUS.project_state import save_project_state

    save_project_state(
        project_path=str(project_path),
        active_project="phase52proj",
        notes="",
        architect_plan=None,
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
        agent_routing_summary=None,
        execution_bridge_report_path=None,
        execution_bridge_summary=None,
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
        dispatch_status="queued",
        enforcement_status="approval_required",
        review_queue_entry={
            "queue_status": "queued",
            "queue_type": queue_type,
            "queue_reason": "Queued for test.",
            "active_project": "phase52proj",
            "run_id": "run-phase52",
            "requires_human_action": True,
        },
        run_id="run-phase52",
    )


def test_control_actions_fail_closed_and_allowed_actions_remain_explicit():
    from NEXUS.project_state import load_project_state
    from NEXUS.registry import PROJECTS
    from NEXUS.runtime_dispatcher import dispatch
    from ops.forge_console_bridge import ALLOWED_CONTROL_ACTIONS, execute_control_action

    with _local_test_dir() as tmp:
        project_key = f"phase52_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 52 temp project"}
        try:
            _write_state(tmp, "manual_review")
            denied = execute_control_action(
                action="execution_package_execute_request",
                project_key=project_key,
                confirmed=True,
                confirmation_text="CONFIRM COMPLETE REVIEW",
            )
            assert denied["status"] == "error"
            assert "allowed_actions" in denied["payload"]
            assert sorted(ALLOWED_CONTROL_ACTIONS.keys()) == ["complete_approval", "complete_review"]

            missing_confirmation = execute_control_action(
                action="complete_review",
                project_key=project_key,
                confirmed=False,
                confirmation_text="",
            )
            assert missing_confirmation["status"] == "error"

            mismatch = execute_control_action(
                action="complete_review",
                project_key=project_key,
                confirmed=True,
                confirmation_text="WRONG",
            )
            assert mismatch["status"] == "error"

            allowed = execute_control_action(
                action="complete_review",
                project_key=project_key,
                confirmed=True,
                confirmation_text="CONFIRM COMPLETE REVIEW",
            )
            assert allowed["status"] == "ok"
            state = load_project_state(str(tmp))
            assert (state.get("review_queue_entry") or {}).get("queue_status") == "cleared"

            _write_state(tmp, "approval")
            allowed_approval = execute_control_action(
                action="complete_approval",
                project_key=project_key,
                confirmed=True,
                confirmation_text="CONFIRM COMPLETE APPROVAL",
            )
            assert allowed_approval["status"] == "ok"
            state2 = load_project_state(str(tmp))
            assert (state2.get("review_queue_entry") or {}).get("queue_status") == "cleared"

            baseline_dispatch = dispatch(
                {
                    "ready_for_dispatch": True,
                    "project": {"project_name": "phase52proj", "project_path": str(tmp)},
                    "execution": {
                        "runtime_target_id": "windows_review_package",
                        "requires_human_approval": True,
                    },
                }
            )
            after_control_dispatch = dispatch(
                {
                    "ready_for_dispatch": True,
                    "project": {"project_name": "phase52proj", "project_path": str(tmp)},
                    "execution": {
                        "runtime_target_id": "windows_review_package",
                        "requires_human_approval": True,
                    },
                }
            )
            assert baseline_dispatch["dispatch_status"] == after_control_dispatch["dispatch_status"]
            assert baseline_dispatch["dispatch_result"]["execution_status"] == after_control_dispatch["dispatch_result"]["execution_status"]
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_control_actions_fail_closed_and_allowed_actions_remain_explicit,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
