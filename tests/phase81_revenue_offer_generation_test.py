"""
Phase 81 revenue offer generation preview tests.

Run: python tests/phase81_revenue_offer_generation_test.py
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
    path = base / f"phase81_{uuid.uuid4().hex[:8]}"
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
        active_project="phase81proj",
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
        run_id="run-phase81",
    )


def _base_lead_intake() -> dict[str, str]:
    return {
        "contact_name": "Alex Rivera",
        "contact_email": "alex@example.com",
        "company_name": "SignalFoundry",
        "contact_channel": "email",
        "lead_source": "website",
        "problem_summary": "Needs a governed internal automation platform.",
        "requested_outcome": "Recommend the right offer direction for implementation.",
        "budget_context": "Leadership approved budget for this quarter.",
        "urgency_context": "Targeting kickoff in the next month.",
    }


def _preview_for(project_key: str, qualification: dict[str, str], lead_intake: dict[str, str] | None = None):
    from ops.forge_console_bridge import build_intake_preview

    return build_intake_preview(
        request_kind="lead_intake",
        project_key=project_key,
        objective="Assess this lead and frame a preview-safe offer direction.",
        project_context="Revenue intake preview for governed service recommendation.",
        constraints_json=json.dumps(
            {
                "scope_boundaries": ["Offer framing only. No package creation."],
                "risk_notes": ["No response generation in this phase."],
                "runtime_preferences": ["Keep routing authority in NEXUS."],
                "output_expectations": ["Return explicit offer and qualification summaries."],
                "review_expectations": ["Reasoning must remain auditable in preview."],
            }
        ),
        requested_artifacts_json=json.dumps({"selected": ["implementation_plan"], "custom": []}),
        linked_attachment_ids_json=json.dumps([]),
        autonomy_mode="supervised_build",
        lead_intake_json=json.dumps(lead_intake or _base_lead_intake()),
        qualification_json=json.dumps(qualification),
    )


def test_offer_ready_when_signals_are_sufficient():
    from NEXUS.registry import PROJECTS

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase81_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 81 temp project"}
        try:
            preview = _preview_for(
                project_key,
                {
                    "budget_band": "medium",
                    "urgency": "medium",
                    "problem_clarity": "clear",
                    "decision_readiness": "ready",
                    "fit_notes": "Strong fit for governed implementation support.",
                },
            )
            payload = preview["payload"]
            offer = payload["offer_summary"]
            assert payload["status"] if "status" in payload else True
            assert offer["offer_status"] == "offer_ready"
            assert offer["recommended_service_type"] in {"governed_implementation", "rapid_delivery_sprint"}
            assert offer["recommended_package_tier"] in {"growth", "scale"}
        finally:
            PROJECTS.pop(project_key, None)


def test_offer_needs_more_info_for_underqualified_signals():
    from NEXUS.registry import PROJECTS

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase81_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 81 temp project"}
        try:
            preview = _preview_for(
                project_key,
                {
                    "budget_band": "none",
                    "urgency": "low",
                    "problem_clarity": "unclear",
                    "decision_readiness": "exploring",
                    "fit_notes": "",
                },
            )
            offer = preview["payload"]["offer_summary"]
            assert offer["offer_status"] == "offer_needs_more_info"
            assert offer["recommended_service_type"] == "discovery_workshop"
        finally:
            PROJECTS.pop(project_key, None)


def test_high_touch_review_recommended_for_complex_high_priority_lead():
    from NEXUS.registry import PROJECTS

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase81_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 81 temp project"}
        try:
            complex_lead = {
                **_base_lead_intake(),
                "problem_summary": "Enterprise multi-team migration with compliance and security constraints.",
            }
            preview = _preview_for(
                project_key,
                {
                    "budget_band": "enterprise",
                    "urgency": "critical",
                    "problem_clarity": "very_clear",
                    "decision_readiness": "committed",
                    "fit_notes": "Complex integration and regulated environment.",
                },
                lead_intake=complex_lead,
            )
            offer = preview["payload"]["offer_summary"]
            assert offer["offer_status"] == "high_touch_review_recommended"
            assert offer["recommended_package_tier"] == "enterprise"
        finally:
            PROJECTS.pop(project_key, None)


def test_no_offer_yet_when_qualification_is_not_usable():
    from NEXUS.registry import PROJECTS

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase81_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 81 temp project"}
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
            offer = preview["payload"]["offer_summary"]
            assert offer["offer_status"] == "no_offer_yet"
            assert offer["pricing_direction"] == "qualification_required"
        finally:
            PROJECTS.pop(project_key, None)


def test_offer_preview_has_no_execution_or_package_side_effects():
    from NEXUS.registry import PROJECTS

    with _local_test_dir() as tmp:
        _write_state(tmp)
        state_path = tmp / "state" / "project_state.json"
        before = json.loads(state_path.read_text(encoding="utf-8"))
        project_key = f"phase81_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 81 temp project"}
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
            assert payload["offer_summary"]["offer_status"] in {
                "offer_ready",
                "high_touch_review_recommended",
                "offer_needs_more_info",
                "no_offer_yet",
            }
            assert payload["package_preview"]["package_creation_allowed"] is False
            assert payload["package_preview"]["routing_authority"] == "NEXUS"
            assert payload["package_preview"]["execution_authority"] == "package_governance_only"
            assert (after.get("execution_package_id") or "") == (before.get("execution_package_id") or "")
            assert (after.get("execution_package_path") or "") == (before.get("execution_package_path") or "")
            assert (after.get("runtime_execution_status") or "") == (before.get("runtime_execution_status") or "")
        finally:
            PROJECTS.pop(project_key, None)


def test_development_intake_has_no_offer_summary():
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_intake_preview

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase81_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 81 temp project"}
        try:
            preview = build_intake_preview(
                request_kind="update_request",
                project_key=project_key,
                objective="Regression check for development intake mode.",
                project_context="Standard development intake should not include offer framing.",
                constraints_json=json.dumps(
                    {
                        "scope_boundaries": ["Do not bypass governance."],
                        "risk_notes": ["No hidden submission behavior."],
                        "runtime_preferences": ["Preview only."],
                        "output_expectations": ["Return intake preview payload."],
                        "review_expectations": ["Keep review center behavior unchanged."],
                    }
                ),
                requested_artifacts_json=json.dumps({"selected": ["implementation_plan"], "custom": []}),
                linked_attachment_ids_json=json.dumps([]),
                autonomy_mode="supervised_build",
                qualification_json=json.dumps({}),
            )
            assert preview["status"] == "ok"
            assert preview["payload"]["offer_summary"] is None
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_offer_ready_when_signals_are_sufficient,
        test_offer_needs_more_info_for_underqualified_signals,
        test_high_touch_review_recommended_for_complex_high_priority_lead,
        test_no_offer_yet_when_qualification_is_not_usable,
        test_offer_preview_has_no_execution_or_package_side_effects,
        test_development_intake_has_no_offer_summary,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
