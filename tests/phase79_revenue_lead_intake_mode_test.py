"""
Phase 79 revenue lead intake mode regression tests.

Run: python tests/phase79_revenue_lead_intake_mode_test.py
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
    path = base / f"phase79_{uuid.uuid4().hex[:8]}"
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
        active_project="phase79proj",
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
        run_id="run-phase79",
    )


def _set_lead_intake_mode(project_path: Path):
    state_path = project_path / "state" / "project_state.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload["intake_mode"] = "lead_intake"
    payload["request_kind"] = "lead_intake"
    state_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def test_revenue_lead_intake_preview_is_governed_and_separate_from_dev_intake():
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_intake_preview

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase79_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 79 temp project"}
        try:
            state_path = tmp / "state" / "project_state.json"
            before = state_path.read_text(encoding="utf-8")

            preview = build_intake_preview(
                request_kind="lead_intake",
                project_key=project_key,
                objective="Acquire a new client for governed implementation support.",
                project_context="Inbound website lead for Forge services.",
                constraints_json=json.dumps({}),
                requested_artifacts_json=json.dumps({"selected": [], "custom": []}),
                linked_attachment_ids_json=json.dumps([]),
                autonomy_mode="supervised_build",
                lead_intake_json=json.dumps(
                    {
                        "contact_name": "Ari Stone",
                        "contact_email": "ari@example.com",
                        "company_name": "Northwind Labs",
                        "contact_channel": "email",
                        "lead_source": "website",
                        "problem_summary": "Needs a governed automation workflow for internal build operations.",
                        "requested_outcome": "Proposal for implementation support.",
                        "budget_context": "Budget allocated this quarter.",
                        "urgency_context": "Wants kickoff in 2 weeks.",
                    }
                ),
                qualification_json=json.dumps({}),
            )

            after = state_path.read_text(encoding="utf-8")

            assert preview["status"] == "ok"
            payload = preview["payload"]
            assert payload["request_kind"] == "lead_intake"
            assert payload["intake_mode"] == "revenue_lead"
            assert payload["readiness"] == "ready_for_governed_request"
            assert payload["composition_status"]["is_complete"] is True
            assert payload["lead_intake_profile"]["company_name"] == "Northwind Labs"
            assert payload["qualification_summary"]["qualification_status"] == "needs_more_info"
            assert payload["package_preview"]["creation_mode"] == "lead_preview_only"
            assert payload["package_preview"]["package_creation_allowed"] is False
            assert payload["package_preview"]["routing_authority"] == "NEXUS"
            assert payload["package_preview"]["execution_authority"] == "package_governance_only"
            assert before == after
        finally:
            PROJECTS.pop(project_key, None)


def test_revenue_lead_intake_requires_core_lead_fields():
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_intake_preview

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase79_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 79 temp project"}
        try:
            preview = build_intake_preview(
                request_kind="lead_intake",
                project_key=project_key,
                objective="Capture lead.",
                project_context="Revenue intake test.",
                constraints_json=json.dumps({}),
                requested_artifacts_json=json.dumps({}),
                linked_attachment_ids_json=json.dumps([]),
                autonomy_mode="supervised_build",
                lead_intake_json=json.dumps(
                    {
                        "contact_name": "",
                        "contact_email": "",
                        "company_name": "",
                        "problem_summary": "",
                    }
                ),
                qualification_json=json.dumps({}),
            )
            assert preview["status"] == "ok"
            payload = preview["payload"]
            assert payload["intake_mode"] == "revenue_lead"
            assert payload["readiness"] == "needs_input"
            assert payload["composition_status"]["is_complete"] is False
            missing = set(payload["composition_status"]["missing_fields"])
            assert "lead_contact_name" in missing
            assert "lead_contact_email" in missing
            assert "lead_company_name" in missing
            assert "lead_problem_summary" in missing
        finally:
            PROJECTS.pop(project_key, None)


def test_lead_intake_mode_workspace_stays_preview_only():
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_project_snapshot

    with _local_test_dir() as tmp:
        _write_state(tmp)
        _set_lead_intake_mode(tmp)
        project_key = f"phase79_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 79 temp project"}
        try:
            snapshot = build_project_snapshot(project_key)
            assert snapshot["status"] == "ok"
            workspace = snapshot["payload"]["intake_workspace"]
            assert workspace["draft_seed"]["request_kind"] == "lead_intake"
            assert workspace["draft_seed"]["lead_qualification"]["budget_band"] == ""
            assert workspace["preview"]["qualification_summary"]["qualification_status"] == "needs_more_info"
            assert workspace["preview"]["package_preview"]["package_creation_allowed"] is False
        finally:
            PROJECTS.pop(project_key, None)


def test_existing_update_request_preview_behavior_remains_intact():
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_intake_preview

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase79_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 79 temp project"}
        try:
            preview = build_intake_preview(
                request_kind="update_request",
                project_key=project_key,
                objective="Keep existing intake preview behavior stable.",
                project_context="Regression check for phase 63/79 request preview.",
                constraints_json=json.dumps(
                    {
                        "scope_boundaries": ["No governance bypass."],
                        "risk_notes": ["No hidden package creation."],
                        "runtime_preferences": ["UI remains composition-only."],
                        "output_expectations": ["Preview payload remains explicit."],
                        "review_expectations": ["Review remains governed."],
                    }
                ),
                requested_artifacts_json=json.dumps(
                    {
                        "selected": ["implementation_plan"],
                        "custom": [],
                    }
                ),
                linked_attachment_ids_json=json.dumps([]),
                autonomy_mode="supervised_build",
                qualification_json=json.dumps({}),
            )
            assert preview["status"] == "ok"
            payload = preview["payload"]
            assert payload["request_kind"] == "update_request"
            assert payload["qualification_summary"] is None
            assert payload["package_preview"]["package_creation_allowed"] is False
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_revenue_lead_intake_preview_is_governed_and_separate_from_dev_intake,
        test_revenue_lead_intake_requires_core_lead_fields,
        test_lead_intake_mode_workspace_stays_preview_only,
        test_existing_update_request_preview_behavior_remains_intact,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
