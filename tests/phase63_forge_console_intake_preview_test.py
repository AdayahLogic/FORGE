"""
Phase 63 Forge Console intake preview tests.

Run: python tests/phase63_forge_console_intake_preview_test.py
"""

from __future__ import annotations

import json
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
    path = base / f"phase63_{uuid.uuid4().hex[:8]}"
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


def _write_state(project_path: Path):
    from NEXUS.project_state import save_project_state

    save_project_state(
        project_path=str(project_path),
        active_project="phase63proj",
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
        governance_status="ok",
        enforcement_status="approval_required",
        project_lifecycle_status="active",
        autonomy_mode="supervised_build",
        allowed_actions=["prepare_package", "recommend_next_step"],
        blocked_actions=["unbounded_loop"],
        run_id="run-phase63",
    )


def test_intake_preview_keeps_attachments_governed_and_read_only():
    from NEXUS.console_attachment_registry import ingest_console_attachment_safe
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_intake_preview, build_project_snapshot

    with _local_test_dir() as tmp:
        _write_state(tmp)
        spec = tmp / "spec.md"
        spec.write_text("Build a safe intake surface.\nReturn approved outputs only.\n", encoding="utf-8")
        unsafe = tmp / "launcher.bat"
        unsafe.write_text("@echo off\n", encoding="utf-8")

        accepted = ingest_console_attachment_safe(
            project_path=str(tmp),
            project_id="phase63proj",
            file_path=str(spec),
            file_name=spec.name,
            file_type="text/markdown",
            source="console_upload",
            purpose="specification",
        )["attachment"]
        quarantined = ingest_console_attachment_safe(
            project_path=str(tmp),
            project_id="phase63proj",
            file_path=str(unsafe),
            file_name=unsafe.name,
            file_type="text/plain",
            source="console_upload",
            purpose="supporting_context",
        )["attachment"]

        project_key = f"phase63_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 63 temp project"}
        try:
            state_path = tmp / "state" / "project_state.json"
            before = state_path.read_text(encoding="utf-8")

            project_snapshot = build_project_snapshot(project_key)
            preview = build_intake_preview(
                project_key=project_key,
                objective="Improve Forge Console intake safely.",
                constraints_json=json.dumps(["Keep NEXUS as the only router."]),
                requested_artifacts_json=json.dumps(["diff_review", "approved_summary"]),
                linked_attachment_ids_json=json.dumps(
                    [accepted["attachment_id"], quarantined["attachment_id"]]
                ),
                autonomy_mode="supervised_build",
            )

            after = state_path.read_text(encoding="utf-8")

            assert project_snapshot["status"] == "ok"
            workspace = project_snapshot["payload"]["intake_workspace"]
            assert len(workspace["attachments"]) == 2
            assert workspace["governance_notes"]["routing_authority"] == "NEXUS"
            assert workspace["attachments"][0]["status_reason"]

            assert preview["status"] == "ok"
            payload = preview["payload"]
            assert payload["package_preview"]["package_creation_allowed"] is False
            assert payload["package_preview"]["routing_authority"] == "NEXUS"
            assert payload["readiness"] == "ready_with_attachment_limits"
            assert any("cannot inform request preview" in warning for warning in payload["warnings"])
            assert before == after
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_intake_preview_keeps_attachments_governed_and_read_only,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
