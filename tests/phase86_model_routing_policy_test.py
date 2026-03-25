"""
Phase 86 model routing policy tests.

Run: python tests/phase86_model_routing_policy_test.py
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
    path = base / f"phase86_{uuid.uuid4().hex[:8]}"
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
        active_project="phase86proj",
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
        run_id="run-phase86",
    )


def test_routine_low_cost_task_routes_to_low_cost_lane():
    from NEXUS.model_routing_policy import resolve_model_routing_policy

    routing = resolve_model_routing_policy(
        task_type="implementation",
        task_complexity="low",
        task_risk_level="medium",
        cost_sensitivity="high",
        budget_status="within_cap",
        is_routine_task=True,
    )
    assert routing["selected_model_lane"] == "low_cost_lane"
    assert routing["routing_outcome"] == "route_low_cost"


def test_normal_task_routes_to_balanced_lane():
    from NEXUS.model_routing_policy import resolve_model_routing_policy

    routing = resolve_model_routing_policy(
        task_type="implementation",
        task_complexity="medium",
        task_risk_level="medium",
        cost_sensitivity="medium",
        budget_status="within_cap",
    )
    assert routing["selected_model_lane"] == "balanced_lane"
    assert routing["routing_outcome"] == "route_balanced"


def test_complex_and_governance_sensitive_tasks_route_to_stricter_lanes():
    from NEXUS.model_routing_policy import resolve_model_routing_policy

    complex_routing = resolve_model_routing_policy(
        task_type="planning",
        task_complexity="high",
        task_risk_level="medium",
        cost_sensitivity="medium",
        budget_status="within_cap",
    )
    governed_routing = resolve_model_routing_policy(
        task_type="governance_sensitive_evaluation",
        task_complexity="medium",
        task_risk_level="high",
        cost_sensitivity="high",
        budget_status="within_cap",
    )
    assert complex_routing["selected_model_lane"] == "high_reasoning_lane"
    assert complex_routing["routing_outcome"] == "route_high_reasoning"
    assert governed_routing["selected_model_lane"] == "governed_high_sensitivity_lane"
    assert governed_routing["routing_outcome"] == "route_governed_high_sensitivity"


def test_approaching_cap_biases_to_lower_cost_when_safe():
    from NEXUS.model_routing_policy import resolve_model_routing_policy

    routing = resolve_model_routing_policy(
        task_type="implementation",
        task_complexity="medium",
        task_risk_level="medium",
        cost_sensitivity="medium",
        budget_status="approaching_cap",
    )
    assert routing["selected_model_lane"] == "low_cost_lane"
    assert routing["routing_outcome"] == "route_low_cost"


def test_kill_switch_and_cap_block_routing():
    from NEXUS.model_routing_policy import resolve_model_routing_policy

    blocked = resolve_model_routing_policy(
        task_type="implementation",
        task_complexity="low",
        task_risk_level="low",
        cost_sensitivity="high",
        budget_status="kill_switch_active",
    )
    deferred = resolve_model_routing_policy(
        task_type="governance_sensitive_evaluation",
        task_complexity="high",
        task_risk_level="critical",
        cost_sensitivity="high",
        budget_status="cap_exceeded",
    )
    assert blocked["routing_outcome"] == "route_blocked_by_budget"
    assert blocked["routing_status"] == "blocked_by_budget"
    assert deferred["routing_outcome"] == "route_deferred_for_review"
    assert deferred["routing_status"] == "deferred_for_review"


def test_no_governance_bypass_under_budget_pressure():
    from NEXUS.model_routing_policy import resolve_model_routing_policy

    routing = resolve_model_routing_policy(
        task_type="governance_sensitive_evaluation",
        task_complexity="medium",
        task_risk_level="high",
        cost_sensitivity="high",
        budget_status="approaching_cap",
    )
    assert routing["selected_model_lane"] == "governed_high_sensitivity_lane"
    assert routing["routing_outcome"] == "route_governed_high_sensitivity"


def test_phase84_and_revenue_preview_regressions_remain_compatible():
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_intake_preview

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase86_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 86 temp project"}
        try:
            preview = build_intake_preview(
                request_kind="lead_intake",
                project_key=project_key,
                objective="Validate revenue preview compatibility with model routing.",
                project_context="Regression path for phases 79-84.",
                constraints_json=json.dumps(
                    {
                        "scope_boundaries": ["Preview only"],
                        "risk_notes": ["No execution side effects"],
                        "runtime_preferences": ["Policy output visible"],
                        "output_expectations": ["Revenue summaries remain present"],
                        "review_expectations": ["Governance preserved"],
                    }
                ),
                requested_artifacts_json=json.dumps({"selected": ["implementation_plan"], "custom": []}),
                linked_attachment_ids_json=json.dumps([]),
                autonomy_mode="supervised_build",
                lead_intake_json=json.dumps(
                    {
                        "contact_name": "Riley",
                        "contact_email": "riley@example.com",
                        "company_name": "Forge Labs",
                        "problem_summary": "Need governed implementation help.",
                        "requested_outcome": "Offer and response preview.",
                        "budget_context": "Budget is medium.",
                        "urgency_context": "This quarter.",
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
            payload = preview["payload"]
            assert preview["status"] == "ok"
            assert payload["cost_tracking"]["cost_unit"] == "usd_estimated"
            assert payload["qualification_summary"] is not None
            assert payload["offer_summary"] is not None
            assert payload["response_summary"] is not None
            assert payload["conversion_summary"] is not None
            assert payload["package_preview"]["package_creation_allowed"] is False
            assert payload["package_preview"]["routing_authority"] == "NEXUS"
            assert payload["model_routing_policy"]["routing_status"] in {
                "routed",
                "blocked_by_budget",
                "deferred_for_review",
            }
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_routine_low_cost_task_routes_to_low_cost_lane,
        test_normal_task_routes_to_balanced_lane,
        test_complex_and_governance_sensitive_tasks_route_to_stricter_lanes,
        test_approaching_cap_biases_to_lower_cost_when_safe,
        test_kill_switch_and_cap_block_routing,
        test_no_governance_bypass_under_budget_pressure,
        test_phase84_and_revenue_preview_regressions_remain_compatible,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
