"""
Phase 84 cost tracking foundation tests.

Run: python tests/phase84_cost_tracking_test.py
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
    path = base / f"phase84_{uuid.uuid4().hex[:8]}"
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


def _write_state(project_path: Path):
    from NEXUS.project_state import save_project_state

    save_project_state(
        project_path=str(project_path),
        active_project="phase84proj",
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
        run_id="run-phase84",
    )


def _create_package(project_path: Path, project_key: str) -> str:
    from NEXUS.execution_package_registry import write_execution_package

    package_id = f"pkg-{uuid.uuid4().hex[:10]}"
    package = {
        "package_id": package_id,
        "project_name": project_key,
        "project_path": str(project_path),
        "run_id": "run-phase84",
        "package_status": "review_pending",
        "review_status": "pending",
        "execution_status": "pending",
        "expected_outputs": ["implementation_plan", "summary_report"],
        "execution_receipt": {
            "result_status": "",
            "exit_code": None,
            "log_ref": "",
            "files_touched_count": 1,
            "artifacts_written_count": 1,
            "failure_class": "",
        },
    }
    path = write_execution_package(str(project_path), package)
    assert path
    return package_id


def test_cost_attached_to_preview_operations():
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_intake_preview

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase84_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 84 temp project"}
        try:
            preview = build_intake_preview(
                request_kind="lead_intake",
                project_key=project_key,
                objective="Estimate and show cost visibility for intake preview.",
                project_context="Cost tracking foundation preview test.",
                constraints_json=json.dumps(
                    {
                        "scope_boundaries": ["Visibility only."],
                        "risk_notes": ["No execution blocking."],
                        "runtime_preferences": ["No budget enforcement."],
                        "output_expectations": ["Return estimated cost object."],
                        "review_expectations": ["Cost remains auditable."],
                    }
                ),
                requested_artifacts_json=json.dumps({"selected": ["implementation_plan"], "custom": []}),
                linked_attachment_ids_json=json.dumps([]),
                autonomy_mode="supervised_build",
                lead_intake_json=json.dumps(
                    {
                        "contact_name": "Taylor",
                        "contact_email": "taylor@example.com",
                        "company_name": "Costly Labs",
                        "problem_summary": "Need governed delivery",
                    }
                ),
                qualification_json=json.dumps(
                    {
                        "budget_band": "medium",
                        "urgency": "medium",
                        "problem_clarity": "clear",
                        "decision_readiness": "ready",
                        "fit_notes": "",
                    }
                ),
            )
            assert preview["status"] == "ok"
            cost = preview["payload"]["cost_tracking"]
            assert cost["cost_unit"] == "usd_estimated"
            assert cost["cost_source"] in {"model_execution", "composed_operation"}
            assert isinstance(cost["cost_estimate"], float)
            assert cost["cost_estimate"] >= 0
        finally:
            PROJECTS.pop(project_key, None)


def test_cost_aggregation_per_project_and_session():
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_project_snapshot

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase84_{uuid.uuid4().hex[:8]}"
        _create_package(tmp, project_key)
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 84 temp project"}
        try:
            snapshot = build_project_snapshot(project_key)
            assert snapshot["status"] == "ok"
            cost_summary = snapshot["payload"]["cost_summary"]
            assert "cost_per_operation" in cost_summary
            assert "cost_per_project" in cost_summary
            assert "session_cost_summary" in cost_summary
            assert cost_summary["cost_per_project"]["estimated_cost_total"] >= 0
            assert cost_summary["session_cost_summary"]["estimated_cost_total"] >= 0
        finally:
            PROJECTS.pop(project_key, None)


def test_cost_fields_present_in_package_output_shape():
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_package_snapshot

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase84_{uuid.uuid4().hex[:8]}"
        package_id = _create_package(tmp, project_key)
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 84 temp project"}
        try:
            snapshot = build_package_snapshot(package_id, project_key=project_key)
            assert snapshot["status"] == "ok"
            payload = snapshot["payload"]
            assert "cost_summary" in payload
            assert payload["cost_summary"]["operation_cost"]["cost_unit"] == "usd_estimated"
            assert payload["cost_summary"]["timeline_estimated_cost_total"] >= 0
        finally:
            PROJECTS.pop(project_key, None)


def test_cost_tracking_does_not_interfere_with_governance_or_execution():
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_intake_preview

    with _local_test_dir() as tmp:
        _write_state(tmp)
        state_path = tmp / "state" / "project_state.json"
        before = json.loads(state_path.read_text(encoding="utf-8"))
        project_key = f"phase84_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 84 temp project"}
        try:
            preview = build_intake_preview(
                request_kind="update_request",
                project_key=project_key,
                objective="Check cost is observational.",
                project_context="No behavior change expected.",
                constraints_json=json.dumps(
                    {
                        "scope_boundaries": ["No governance override."],
                        "risk_notes": ["No execution blocking."],
                        "runtime_preferences": ["No authority changes."],
                        "output_expectations": ["Cost visibility only."],
                        "review_expectations": ["Maintain preview-only behavior."],
                    }
                ),
                requested_artifacts_json=json.dumps({"selected": ["implementation_plan"], "custom": []}),
                linked_attachment_ids_json=json.dumps([]),
                autonomy_mode="supervised_build",
            )
            after = json.loads(state_path.read_text(encoding="utf-8"))
            payload = preview["payload"]
            assert payload["package_preview"]["package_creation_allowed"] is False
            assert payload["package_preview"]["routing_authority"] == "NEXUS"
            assert payload["package_preview"]["execution_authority"] == "package_governance_only"
            assert before == after
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_cost_attached_to_preview_operations,
        test_cost_aggregation_per_project_and_session,
        test_cost_fields_present_in_package_output_shape,
        test_cost_tracking_does_not_interfere_with_governance_or_execution,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
