"""
Phase 95 operator console + activity surface adapter tests.

Run: python tests/phase95_console_activity_surface_test.py
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


def _run(name: str, fn):
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except Exception as exc:
        print(f"FAIL: {name} - {exc}")
        return False


def _write_state(project_path: Path, package_id: str):
    from NEXUS.project_state import save_project_state

    save_project_state(
        project_path=str(project_path),
        active_project="phase95proj",
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
        run_id="run-phase95",
        autonomy_mode="supervised_build",
    )


def _write_package(project_path: Path, package_id: str):
    from NEXUS.execution_package_registry import write_execution_package_safe

    package = {
        "package_id": package_id,
        "package_version": "1.0",
        "package_kind": "review_only_execution_envelope",
        "project_name": "phase95proj",
        "project_path": str(project_path),
        "created_at": "2026-03-31T10:15:00Z",
        "package_status": "review_pending",
        "review_status": "review_pending",
        "decision_status": "pending",
        "release_status": "pending",
        "handoff_status": "pending",
        "execution_status": "pending",
        "evaluation_status": "pending",
        "local_analysis_status": "pending",
        "runtime_target_id": "windows_review_package",
        "expected_outputs": ["implementation_summary", "test_report"],
        "integrity_verification": {"integrity_status": "waiting_for_input"},
        "execution_receipt": {"result_status": "pending", "log_ref": "state/execution_runs/run.log"},
        "cost_tracking": {
            "cost_estimate": 0.42,
            "cost_unit": "usd_estimated",
            "cost_source": "model_execution",
            "cost_breakdown": {
                "model": "gpt-5.4-mini",
                "estimated_tokens": 5000,
                "estimated_cost": 0.42,
            },
        },
    }
    assert write_execution_package_safe(str(project_path), package)


def test_console_snapshot_and_message_surface_contract():
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_operator_console_snapshot, respond_to_operator_message

    with _local_test_dir() as tmp:
        package_id = "pkg-phase95"
        _write_package(tmp, package_id)
        _write_state(tmp, package_id)
        project_key = f"phase95_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 95 temp project"}
        try:
            result = build_operator_console_snapshot(project_key)
            assert result["status"] == "ok"
            payload = result["payload"]
            assert sorted(payload.keys()) == [
                "approvals",
                "context",
                "generated_at",
                "live_activity",
                "quick_actions",
                "selected_project_key",
                "system_awareness",
            ]
            assert payload["selected_project_key"] == project_key
            assert payload["context"]["active_project"]["project_name"] == project_key

            response = respond_to_operator_message(
                message="what are you doing right now",
                project_key=project_key,
            )
            assert response["status"] == "ok"
            reply_payload = response["payload"]
            assert reply_payload["reply"]
            assert isinstance(reply_payload["response_cards"], list)
            assert reply_payload["console_snapshot"]["selected_project_key"] == project_key
        finally:
            PROJECTS.pop(project_key, None)


def test_activity_snapshot_and_governed_action_gate():
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_activity_snapshot, respond_to_operator_message

    with _local_test_dir() as tmp:
        package_id = "pkg-phase95-action"
        _write_package(tmp, package_id)
        _write_state(tmp, package_id)
        project_key = f"phase95_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 95 temp project"}
        try:
            activity = build_activity_snapshot(project_key, limit=20)
            assert activity["status"] == "ok"
            payload = activity["payload"]
            assert sorted(payload.keys()) == [
                "approvals",
                "connector_posture",
                "generated_at",
                "live_feed",
                "mission_status",
                "outcomes",
                "queue_worker_visibility",
                "selected_project_key",
            ]
            assert isinstance(payload["mission_status"]["queued"], list)

            gated = respond_to_operator_message(
                message="",
                project_key=project_key,
                execute_action="complete_review",
                confirmed=False,
                confirmation_text="",
            )
            assert gated["status"] == "error"
            assert "Confirmation required" in str(gated.get("message") or "")
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_console_snapshot_and_message_surface_contract,
        test_activity_snapshot_and_governed_action_gate,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
