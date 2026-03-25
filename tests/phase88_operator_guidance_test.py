"""
Phase 88 operator guidance tests.

Run: python tests/phase88_operator_guidance_test.py
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
    path = base / f"phase88_{uuid.uuid4().hex[:8]}"
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
    except Exception as exc:
        print(f"FAIL: {name} - {exc}")
        return False


def _write_state(project_path: Path, package_id: str = ""):
    from NEXUS.project_state import save_project_state

    save_project_state(
        project_path=str(project_path),
        active_project="phase88proj",
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
        execution_package_id=package_id,
        execution_package_path=str(project_path / "state" / "execution_packages" / f"{package_id}.json") if package_id else "",
        dispatch_status="queued",
        governance_status="ok",
        enforcement_status="approval_required",
        project_lifecycle_status="active",
        autonomy_mode="supervised_build",
        run_id="run-phase88",
    )


def _write_package(project_path: Path, package_id: str):
    from NEXUS.execution_package_registry import write_execution_package_safe

    payload = {
        "package_id": package_id,
        "project_name": "phase88proj",
        "project_path": str(project_path),
        "run_id": "run-phase88",
        "package_status": "review_pending",
        "review_status": "pending",
        "decision_status": "pending",
        "release_status": "pending",
        "execution_status": "pending",
        "requires_human_approval": True,
        "expected_outputs": ["implementation_summary"],
        "runtime_artifacts": [{"artifact_type": "test_report"}],
    }
    assert write_execution_package_safe(str(project_path), payload)


def test_operator_guidance_fields_present_and_read_only():
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_project_snapshot

    with _local_test_dir() as tmp:
        package_id = "pkg-phase88"
        _write_package(tmp, package_id)
        _write_state(tmp, package_id)
        project_key = f"phase88_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 88 temp project"}
        try:
            state_path = tmp / "state" / "project_state.json"
            before = state_path.read_text(encoding="utf-8")
            snapshot = build_project_snapshot(project_key)
            after = state_path.read_text(encoding="utf-8")
            assert snapshot["status"] == "ok"
            payload = snapshot["payload"]
            assert payload["workflow_activity"]["last_action"]
            assert payload["workflow_activity"]["current_phase"] in {"planning", "routing", "execution", "review"}
            quick = payload["quick_actions"]
            assert quick["quick_actions_status"] in {"none", "available", "blocked"}
            assert isinstance(quick["available_actions"], list)
            assert before == after
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_operator_guidance_fields_present_and_read_only,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())

