"""
Phase 82 revenue response generation preview tests.

Run: python tests/phase82_revenue_response_generation_test.py
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
    path = base / f"phase82_{uuid.uuid4().hex[:8]}"
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
        active_project="phase82proj",
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
        run_id="run-phase82",
    )


def _base_lead_intake() -> dict[str, str]:
    return {
        "contact_name": "Jordan Lee",
        "contact_email": "jordan@example.com",
        "company_name": "HelixWorks",
        "contact_channel": "email",
        "lead_source": "referral",
        "problem_summary": "We need a governed automation path for engineering delivery.",
        "requested_outcome": "A recommendation with practical next steps.",
        "budget_context": "Budget has been approved.",
        "urgency_context": "Initiative is planned this quarter.",
    }


def _preview_for(project_key: str, qualification: dict[str, str], lead_intake: dict[str, str] | None = None):
    from ops.forge_console_bridge import build_intake_preview

    return build_intake_preview(
        request_kind="lead_intake",
        project_key=project_key,
        objective="Create a preview-safe response draft for this lead.",
        project_context="Revenue response generation preview test.",
        constraints_json=json.dumps(
            {
                "scope_boundaries": ["Preview only."],
                "risk_notes": ["No outbound communication."],
                "runtime_preferences": ["Keep authority in NEXUS."],
                "output_expectations": ["Generate offer and response summaries."],
                "review_expectations": ["Response remains operator-reviewable."],
            }
        ),
        requested_artifacts_json=json.dumps({"selected": ["implementation_plan"], "custom": []}),
        linked_attachment_ids_json=json.dumps([]),
        autonomy_mode="supervised_build",
        lead_intake_json=json.dumps(lead_intake or _base_lead_intake()),
        qualification_json=json.dumps(qualification),
    )


def test_response_ready_when_data_is_sufficient():
    from NEXUS.registry import PROJECTS

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase82_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 82 temp project"}
        try:
            preview = _preview_for(
                project_key,
                {
                    "budget_band": "medium",
                    "urgency": "medium",
                    "problem_clarity": "clear",
                    "decision_readiness": "ready",
                    "fit_notes": "Strong operational fit.",
                },
            )
            response = preview["payload"]["response_summary"]
            assert response["response_status"] == "response_ready"
            assert response["response_message"]
            assert "not sent" not in response["response_message"].lower()
        finally:
            PROJECTS.pop(project_key, None)


def test_needs_more_info_when_key_intake_fields_missing():
    from NEXUS.registry import PROJECTS

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase82_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 82 temp project"}
        try:
            partial_lead = {
                **_base_lead_intake(),
                "contact_name": "",
                "company_name": "",
            }
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
            response = preview["payload"]["response_summary"]
            assert response["response_status"] == "needs_more_info"
            assert response["response_message"]
        finally:
            PROJECTS.pop(project_key, None)


def test_high_touch_required_for_complex_high_risk_lead():
    from NEXUS.registry import PROJECTS

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase82_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 82 temp project"}
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
                    "fit_notes": "Security and compliance risk review required.",
                },
                lead_intake=complex_lead,
            )
            response = preview["payload"]["response_summary"]
            assert response["response_status"] == "high_touch_required"
            assert response["response_tone"] == "consultative"
        finally:
            PROJECTS.pop(project_key, None)


def test_no_response_when_qualification_is_not_ready():
    from NEXUS.registry import PROJECTS

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase82_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 82 temp project"}
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
            response = preview["payload"]["response_summary"]
            assert response["response_status"] == "no_response"
            assert response["response_message"] == ""
        finally:
            PROJECTS.pop(project_key, None)


def test_response_preview_has_no_execution_side_effects():
    from NEXUS.registry import PROJECTS

    with _local_test_dir() as tmp:
        _write_state(tmp)
        state_path = tmp / "state" / "project_state.json"
        before = json.loads(state_path.read_text(encoding="utf-8"))
        project_key = f"phase82_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 82 temp project"}
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
            assert payload["response_summary"]["response_status"] in {
                "no_response",
                "needs_more_info",
                "response_ready",
                "high_touch_required",
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
        test_response_ready_when_data_is_sufficient,
        test_needs_more_info_when_key_intake_fields_missing,
        test_high_touch_required_for_complex_high_risk_lead,
        test_no_response_when_qualification_is_not_ready,
        test_response_preview_has_no_execution_side_effects,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
