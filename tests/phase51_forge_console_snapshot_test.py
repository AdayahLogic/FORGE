"""
Phase 51 Forge Console snapshot tests.

Run: python tests/phase51_forge_console_snapshot_test.py
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
    path = base / f"phase51_{uuid.uuid4().hex[:8]}"
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


def _write_state(project_path: Path, package_id: str):
    from NEXUS.project_state import save_project_state

    save_project_state(
        project_path=str(project_path),
        active_project="phase51proj",
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
        execution_package_path=str(project_path / "state" / "execution_packages" / f"{package_id}.json"),
        dispatch_status="queued",
        project_lifecycle_status="active",
        governance_status="ok",
        enforcement_status="approval_required",
        system_health_summary={"overall_status": "watch"},
        run_id="run-phase51",
        review_queue_entry={
            "queue_status": "queued",
            "queue_type": "approval",
            "active_project": "phase51proj",
            "run_id": "run-phase51",
            "requires_human_action": True,
        },
    )


def _write_package(project_path: Path, package_id: str):
    from NEXUS.execution_package_registry import write_execution_package_safe

    package = {
        "package_id": package_id,
        "package_version": "1.0",
        "package_kind": "review_only_execution_envelope",
        "project_name": "phase51proj",
        "project_path": str(project_path),
        "created_at": "2026-03-22T00:00:00Z",
        "package_status": "review_pending",
        "review_status": "pending",
        "sealed": True,
        "seal_reason": "Review-only package.",
        "runtime_target_id": "windows_review_package",
        "runtime_target_name": "windows_review_package",
        "execution_mode": "manual_only",
        "requested_action": "adapter_dispatch_call",
        "requested_by": "workflow",
        "requires_human_approval": True,
        "approval_id_refs": ["appr-1"],
        "aegis_decision": "approval_required",
        "aegis_scope": "runtime_dispatch_only",
        "reason": "Human review required before any activation.",
        "dispatch_plan_summary": {"ready_for_dispatch": True},
        "routing_summary": {"runtime_node": "coder", "tool_name": "cursor_agent"},
        "execution_summary": {"review_only": True, "can_execute": False},
        "command_request": {"summary": "Execute reviewed package.", "task_type": "coder"},
        "candidate_paths": ["src/module.py"],
        "expected_outputs": ["execution package"],
        "review_checklist": ["Confirm package remains sealed."],
        "rollback_notes": ["Use rollback guidance if execution fails."],
        "runtime_artifacts": [{"artifact_type": "execution_log", "log_ref": "state/execution_runs/run.log"}],
        "metadata": {"openclaw_active": False},
        "decision_status": "approved",
        "eligibility_status": "eligible",
        "release_status": "released",
        "handoff_status": "authorized",
        "handoff_executor_target_id": "local",
        "handoff_executor_target_name": "Local",
        "execution_status": "succeeded",
        "execution_reason": {"code": "succeeded", "message": "Executed."},
        "execution_receipt": {"result_status": "succeeded", "exit_code": 0, "log_ref": "state/execution_runs/run.log"},
        "integrity_verification": {"integrity_status": "verified", "integrity_summary": {"log_ref_present": True}},
        "evaluation_status": "completed",
        "evaluation_actor": "abacus_operator",
        "evaluation_reason": {"code": "completed", "message": "Abacus evaluation completed."},
        "evaluation_basis": {"source_execution_status": "succeeded"},
        "evaluation_summary": {
            "execution_quality_score": 96,
            "integrity_score": 96,
            "rollback_quality": 90,
            "failure_risk_score": 10,
            "execution_quality_band": "excellent",
            "integrity_band": "excellent",
            "rollback_quality_band": "excellent",
            "failure_risk_band": "low",
            "evaluator_summary": "Execution succeeded.",
        },
        "local_analysis_status": "completed",
        "local_analysis_actor": "nemoclaw",
        "local_analysis_reason": {"code": "completed", "message": "NemoClaw completed."},
        "local_analysis_basis": {"source_execution_status": "succeeded"},
        "local_analysis_summary": {
            "recommendation_summary": "No action required.",
            "confidence_score": 94,
            "confidence_band": "high",
            "risk_interpretation": "Risk posture low.",
            "execution_evaluation_interpretation": "Execution succeeded.",
            "suggested_next_action": "no_action_required",
            "analysis_summary": "Stable package.",
        },
    }
    assert write_execution_package_safe(str(project_path), package)


def test_bridge_snapshots_are_read_only_and_shape_stable():
    from NEXUS.approval_registry import append_approval_record_safe, get_approval_journal_path
    from NEXUS.execution_package_registry import get_execution_package_journal_path
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import (
        build_package_snapshot,
        build_project_snapshot,
        build_studio_snapshot,
    )

    with _local_test_dir() as tmp:
        package_id = "pkg-phase51"
        _write_package(tmp, package_id)
        _write_state(tmp, package_id)
        append_approval_record_safe(
            project_path=str(tmp),
            record={
                "approval_id": "appr-1",
                "project_name": "phase51proj",
                "status": "pending",
                "approval_type": "aegis_policy",
                "reason": "Approval pending.",
            },
        )
        project_key = f"phase51_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 51 temp project"}
        try:
            state_path = tmp / "state" / "project_state.json"
            package_journal = Path(get_execution_package_journal_path(str(tmp)))
            approval_journal = Path(get_approval_journal_path(str(tmp)))
            before = {
                "state": state_path.read_text(encoding="utf-8"),
                "package": package_journal.read_text(encoding="utf-8"),
                "approval": approval_journal.read_text(encoding="utf-8"),
            }

            studio = build_studio_snapshot()
            project = build_project_snapshot(project_key)
            package = build_package_snapshot(package_id, project_key=project_key)

            after = {
                "state": state_path.read_text(encoding="utf-8"),
                "package": package_journal.read_text(encoding="utf-8"),
                "approval": approval_journal.read_text(encoding="utf-8"),
            }

            assert studio["overview"]["project_count"] >= 1
            assert studio["overview"]["system_status"]["label"] == "Forge Running"
            assert "approval_center" in studio
            assert project["status"] == "ok"
            assert project["payload"]["package_queue"]["count"] >= 1
            assert project["payload"]["system_status"]["label"] == "Forge Running"
            assert project["payload"]["workflow_activity"]["current_project"]
            assert package["status"] == "ok"
            assert package["payload"]["execution_feedback"]["package_created"] is True
            assert package["payload"]["evaluation"]["evaluation_status"] == "completed"
            assert package["payload"]["local_analysis"]["local_analysis_status"] == "completed"
            assert before == after
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_bridge_snapshots_are_read_only_and_shape_stable,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
