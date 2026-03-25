"""
Phase 65 Forge Console client-safe view tests.

Run: python tests/phase65_forge_console_client_view_test.py
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
    path = base / f"phase65_{uuid.uuid4().hex[:8]}"
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
        active_project="phase65proj",
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
        run_id="run-phase65",
    )


def _write_package(project_path: Path, package_id: str):
    from NEXUS.execution_package_registry import write_execution_package_safe

    package = {
        "package_id": package_id,
        "package_version": "1.0",
        "package_kind": "review_only_execution_envelope",
        "project_name": "phase65proj",
        "project_path": str(project_path),
        "created_at": "2026-03-23T00:00:00Z",
        "package_status": "review_pending",
        "review_status": "reviewed",
        "decision_status": "approved",
        "release_status": "released",
        "execution_status": "succeeded",
        "runtime_target_id": "windows_review_package",
        "expected_outputs": ["implementation_summary", "test_report"],
        "runtime_artifacts": [
            {
                "artifact_type": "approved_summary",
                "artifact_summary": "Safe summary prepared.",
                "status": "artifact_recorded",
                "source_runtime": "cursor",
            }
        ],
        "cursor_bridge_artifacts": [
            {
                "artifact_type": "patch",
                "patch_summary": "Updated client-safe surface.",
                "changed_files": ["app/page.tsx"],
            }
        ],
        "routing_summary": {"runtime_node": "coder"},
        "execution_receipt": {"result_status": "succeeded", "log_ref": "state/execution_runs/run.log"},
        "integrity_verification": {"integrity_status": "verified"},
    }
    assert write_execution_package_safe(str(project_path), package)


def test_client_view_snapshot_is_allowlisted_and_shareable_only():
    from NEXUS.console_attachment_registry import ingest_console_attachment_safe
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_client_view_snapshot

    with _local_test_dir() as tmp:
        package_id = "pkg-phase65"
        _write_package(tmp, package_id)
        _write_state(tmp, package_id)

        hidden_doc = tmp / "internal.md"
        hidden_doc.write_text("Internal review notes only.\n", encoding="utf-8")
        safe_doc = tmp / "shared-summary.md"
        safe_doc.write_text("Approved summary for clients.\n", encoding="utf-8")

        ingest_console_attachment_safe(
            project_path=str(tmp),
            project_id="phase65proj",
            file_path=str(hidden_doc),
            file_name=hidden_doc.name,
            file_type="text/markdown",
            source="console_upload",
            purpose="supporting_context",
        )
        ingest_console_attachment_safe(
            project_path=str(tmp),
            project_id="phase65proj",
            file_path=str(safe_doc),
            file_name=safe_doc.name,
            file_type="text/markdown",
            source="console_upload",
            purpose="safe_to_share",
        )

        project_key = f"phase65_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 65 temp project"}
        try:
            result = build_client_view_snapshot(project_key)
            assert result["status"] == "ok"
            payload = result["payload"]
            assert payload["surface_mode"] == "client_safe"
            assert sorted(payload.keys()) == [
                "generated_at",
                "project",
                "projects",
                "selected_project_key",
                "surface_mode",
            ]

            project = payload["project"]
            assert sorted(project.keys()) == [
                "approved_attachments",
                "client_status",
                "current_phase",
                "delivery_summary",
                "deliverables",
                "description",
                "milestones",
                "progress_label",
                "progress_percent",
                "project_key",
                "project_name",
                "safe_summary",
                "timeline",
            ]
            assert all(item["safe_to_share"] is True for item in project["deliverables"])
            assert project["delivery_summary"]["delivery_progress_state"] == "client_safe_packaging_ready"
            assert len(project["approved_attachments"]) == 1
            assert project["approved_attachments"][0]["file_name"] == "shared-summary.md"
            assert project["approved_attachments"][0]["status"] == "safe_to_share"

            serialized = json.dumps(payload)
            for forbidden in [
                "governance_trace",
                "raw_storage_path",
                "allowed_consumers",
                "runtime_target_id",
                "execution_receipt",
                "routing_summary",
                "project_state",
                "package_json",
                "allowed_actions",
            ]:
                assert forbidden not in serialized

            labels = [item["label"] for item in project["timeline"]]
            assert "Approved Deliverables Shared" in labels
            assert "Review Ready" in labels
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_client_view_snapshot_is_allowlisted_and_shareable_only,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
