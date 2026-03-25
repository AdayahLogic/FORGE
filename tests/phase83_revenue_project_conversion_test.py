"""
Phase 83 revenue project conversion preview tests.

Run: python tests/phase83_revenue_project_conversion_test.py
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
    path = base / f"phase83_{uuid.uuid4().hex[:8]}"
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
        active_project="phase83proj",
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
        run_id="run-phase83",
    )


def _base_lead_intake() -> dict[str, str]:
    return {
        "contact_name": "Sam Carter",
        "contact_email": "sam@example.com",
        "company_name": "VectorForge",
        "contact_channel": "email",
        "lead_source": "website",
        "problem_summary": "Need governed automation and delivery controls for engineering operations.",
        "requested_outcome": "A scoped implementation plan and rollout approach.",
        "budget_context": "Budget approved for this initiative.",
        "urgency_context": "Target start is this quarter.",
    }


def _preview_for(project_key: str, qualification: dict[str, str], lead_intake: dict[str, str] | None = None):
    from ops.forge_console_bridge import build_intake_preview

    return build_intake_preview(
        request_kind="lead_intake",
        project_key=project_key,
        objective="Generate governed conversion preview.",
        project_context="Phase 83 project conversion validation.",
        constraints_json=json.dumps(
            {
                "scope_boundaries": ["No automatic project execution."],
                "risk_notes": ["No hidden side effects."],
                "runtime_preferences": ["Keep routing and execution governance explicit."],
                "output_expectations": ["Return conversion readiness and candidate fields."],
                "review_expectations": ["Operator can audit conversion reasoning."],
            }
        ),
        requested_artifacts_json=json.dumps({"selected": ["implementation_plan"], "custom": []}),
        linked_attachment_ids_json=json.dumps([]),
        autonomy_mode="supervised_build",
        lead_intake_json=json.dumps(lead_intake or _base_lead_intake()),
        qualification_json=json.dumps(qualification),
    )


def test_conversion_ready_when_upstream_data_is_sufficient():
    from NEXUS.registry import PROJECTS

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase83_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 83 temp project"}
        try:
            preview = _preview_for(
                project_key,
                {
                    "budget_band": "medium",
                    "urgency": "medium",
                    "problem_clarity": "clear",
                    "decision_readiness": "ready",
                    "fit_notes": "Strong fit for governed implementation.",
                },
            )
            conversion = preview["payload"]["conversion_summary"]
            assert conversion["conversion_status"] == "conversion_ready"
            assert conversion["proposed_project_name"]
            assert conversion["proposed_scope_summary"]
        finally:
            PROJECTS.pop(project_key, None)


def test_conversion_not_ready_when_upstream_data_incomplete():
    from NEXUS.registry import PROJECTS

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase83_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 83 temp project"}
        try:
            preview = _preview_for(
                project_key,
                {
                    "budget_band": "medium",
                    "urgency": "",
                    "problem_clarity": "",
                    "decision_readiness": "",
                    "fit_notes": "",
                },
            )
            conversion = preview["payload"]["conversion_summary"]
            assert conversion["conversion_status"] == "conversion_not_ready"
            assert conversion["proposed_project_name"] == ""
        finally:
            PROJECTS.pop(project_key, None)


def test_conversion_needs_review_when_readiness_is_partial():
    from NEXUS.registry import PROJECTS

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase83_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 83 temp project"}
        try:
            partial_lead = {**_base_lead_intake(), "contact_name": "", "company_name": ""}
            preview = _preview_for(
                project_key,
                {
                    "budget_band": "medium",
                    "urgency": "high",
                    "problem_clarity": "clear",
                    "decision_readiness": "ready",
                    "fit_notes": "",
                },
                lead_intake=partial_lead,
            )
            conversion = preview["payload"]["conversion_summary"]
            assert conversion["conversion_status"] == "conversion_needs_review"
            assert conversion["proposed_project_type"] != "undetermined"
        finally:
            PROJECTS.pop(project_key, None)


def test_high_touch_conversion_required_for_complex_lead():
    from NEXUS.registry import PROJECTS

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase83_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 83 temp project"}
        try:
            complex_lead = {
                **_base_lead_intake(),
                "problem_summary": "Enterprise multi-team migration in a regulated compliance environment.",
            }
            preview = _preview_for(
                project_key,
                {
                    "budget_band": "enterprise",
                    "urgency": "critical",
                    "problem_clarity": "very_clear",
                    "decision_readiness": "committed",
                    "fit_notes": "Complex integration and security constraints.",
                },
                lead_intake=complex_lead,
            )
            conversion = preview["payload"]["conversion_summary"]
            assert conversion["conversion_status"] == "high_touch_conversion_required"
            assert conversion["proposed_project_name"]
        finally:
            PROJECTS.pop(project_key, None)


def test_conversion_preview_has_no_execution_or_package_side_effects():
    from NEXUS.registry import PROJECTS

    with _local_test_dir() as tmp:
        _write_state(tmp)
        state_path = tmp / "state" / "project_state.json"
        before = json.loads(state_path.read_text(encoding="utf-8"))
        project_key = f"phase83_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 83 temp project"}
        try:
            preview = _preview_for(
                project_key,
                {
                    "budget_band": "high",
                    "urgency": "high",
                    "problem_clarity": "clear",
                    "decision_readiness": "ready",
                    "fit_notes": "",
                },
            )
            payload = preview["payload"]
            after = json.loads(state_path.read_text(encoding="utf-8"))
            assert payload["conversion_summary"]["conversion_status"] in {
                "conversion_not_ready",
                "conversion_needs_review",
                "conversion_ready",
                "high_touch_conversion_required",
            }
            assert payload["package_preview"]["package_creation_allowed"] is False
            assert payload["package_preview"]["routing_authority"] == "NEXUS"
            assert payload["package_preview"]["execution_authority"] == "package_governance_only"
            assert (after.get("execution_package_id") or "") == (before.get("execution_package_id") or "")
            assert (after.get("execution_package_path") or "") == (before.get("execution_package_path") or "")
            assert (after.get("runtime_execution_status") or "") == (before.get("runtime_execution_status") or "")
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_conversion_ready_when_upstream_data_is_sufficient,
        test_conversion_not_ready_when_upstream_data_incomplete,
        test_conversion_needs_review_when_readiness_is_partial,
        test_high_touch_conversion_required_for_complex_lead,
        test_conversion_preview_has_no_execution_or_package_side_effects,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
