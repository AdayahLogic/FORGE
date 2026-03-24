"""
Phase 64 Forge Console review center tests.

Run: python tests/phase64_forge_console_review_center_test.py
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
    path = base / f"phase64_{uuid.uuid4().hex[:8]}"
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
        active_project="phase64proj",
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
        run_id="run-phase64",
    )


def _write_package(project_path: Path, package_id: str):
    from NEXUS.execution_package_registry import write_execution_package_safe

    package = {
        "package_id": package_id,
        "package_version": "1.0",
        "package_kind": "review_only_execution_envelope",
        "project_name": "phase64proj",
        "project_path": str(project_path),
        "created_at": "2026-03-23T00:00:00Z",
        "package_status": "review_pending",
        "review_status": "pending",
        "sealed": True,
        "seal_reason": "Review-only package.",
        "runtime_target_id": "windows_review_package",
        "requires_human_approval": True,
        "approval_id_refs": ["appr-64"],
        "decision_status": "approved",
        "release_status": "released",
        "execution_status": "succeeded",
        "execution_receipt": {"result_status": "succeeded", "exit_code": 0, "log_ref": "state/execution_runs/review.log"},
        "integrity_verification": {"integrity_status": "verified"},
        "candidate_paths": ["src/module.py"],
        "expected_outputs": ["diff_review", "test_report"],
        "review_checklist": ["Confirm package remains sealed."],
        "runtime_artifacts": [
            {"artifact_type": "execution_log", "log_ref": "state/execution_runs/review.log"},
            {
                "artifact_type": "cursor_bridge_artifact_return",
                "artifact_summary": "Returned governed patch output.",
                "status": "artifact_recorded",
                "source_runtime": "cursor",
            },
        ],
        "cursor_bridge_artifacts": [
            {
                "artifact_type": "patch",
                "artifact_summary": "Governed patch output.",
                "patch_summary": "Updated review surface.",
                "changed_files": ["src/module.py", "tests/test_module.py"],
            }
        ],
        "evaluation_status": "completed",
        "evaluation_summary": {
            "execution_quality_score": 91,
            "execution_quality_band": "excellent",
            "integrity_band": "excellent",
            "failure_risk_band": "low",
        },
        "local_analysis_status": "completed",
        "local_analysis_summary": {
            "suggested_next_action": "approve_for_release",
            "analysis_summary": "Stable.",
        },
    }
    assert write_execution_package_safe(str(project_path), package)


def test_review_center_snapshot_includes_artifacts_and_attachment_statuses():
    from NEXUS.console_attachment_registry import ingest_console_attachment_safe
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_package_snapshot

    with _local_test_dir() as tmp:
        package_id = "pkg-phase64"
        _write_package(tmp, package_id)
        _write_state(tmp, package_id)

        project_doc = tmp / "review.md"
        project_doc.write_text("Review context for the project.\n", encoding="utf-8")
        denied_bin = tmp / "large.bin"
        denied_bin.write_bytes(b"x" * (5 * 1024 * 1024 + 1))
        linked_doc = tmp / "package-review.md"
        linked_doc.write_text("Package-specific review notes.\n", encoding="utf-8")

        ingest_console_attachment_safe(
            project_path=str(tmp),
            project_id="phase64proj",
            file_path=str(project_doc),
            file_name=project_doc.name,
            file_type="text/markdown",
            source="console_upload",
            purpose="supporting_context",
        )
        ingest_console_attachment_safe(
            project_path=str(tmp),
            project_id="phase64proj",
            file_path=str(denied_bin),
            file_name=denied_bin.name,
            file_type="application/octet-stream",
            source="console_upload",
            purpose="evidence",
        )
        ingest_console_attachment_safe(
            project_path=str(tmp),
            project_id="phase64proj",
            file_path=str(linked_doc),
            file_name=linked_doc.name,
            file_type="text/markdown",
            source="console_upload",
            purpose="specification",
            package_id=package_id,
        )

        project_key = f"phase64_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 64 temp project"}
        try:
            package = build_package_snapshot(package_id, project_key=project_key)
            assert package["status"] == "ok"
            review = package["payload"]["review_center"]
            assert review["approval_ready_context"]["requires_human_approval"] is True
            assert review["returned_artifacts"]
            assert review["patch_context"]["patch_summary"]
            assert review["test_results"]["execution_result_status"] == "succeeded"
            assert review["execution_feedback"]["package_created"] is True
            assert review["execution_feedback"]["lifecycle_transitions"]
            assert review["evaluation_summary"]["execution_quality_band"] == "excellent"
            attachments = review["related_attachments"]
            assert len(attachments) >= 2
            assert any(item["review_relevance"] == "package_linked" for item in attachments)
            assert any(item["status"] == "denied" for item in attachments)
            assert any(item["status_reason"] for item in attachments)
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_review_center_snapshot_includes_artifacts_and_attachment_statuses,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
