"""
Phase 78 change value policy and ROI-gated self-improvement tests.

Run: python tests/phase78_change_value_roi_policy_test.py
"""

from __future__ import annotations

import shutil
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@contextmanager
def _local_test_dir():
    base = ROOT / ".tmp_test_runs"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"phase78_{uuid.uuid4().hex[:8]}"
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


def _window() -> dict:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return {
        "current_window_id": start.strftime("window-%Y%m%d"),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
    }


def _contract(
    *,
    change_id: str,
    target_files: list[str],
    change_type: str,
    strategic_intent_category: str = "governance_strengthening",
    executive_priority_match: bool = True,
    expected_value: str = "high",
    expected_cost: str = "medium",
    expected_complexity: str = "medium",
    expected_risk_burden: str = "medium",
    expected_maintenance_burden: str = "low",
    priority_value: str = "high",
    executive_review_required: bool = False,
    reason: str = "Phase 21 value policy evaluation.",
) -> dict:
    return {
        "change_id": change_id,
        "target_files": target_files,
        "change_type": change_type,
        "reason": reason,
        "expected_outcome": "Forge explicitly decides whether a self-change is worth current investment.",
        "validation_plan": {"summary": "Run tests and inspect value policy.", "checks": ["tests", "build", "regressions"]},
        "rollback_plan": {"summary": "Rollback if value assumptions or safety posture degrade.", "last_stable_state_ref": "stable-phase77"},
        "authority_trace": {"actor": "nexus", "requested_action": "propose_self_change", "authority_status": "authorized"},
        "governance_trace": {"origin": "phase78_test"},
        "approval_status": "approved",
        "executive_approval_status": "approved",
        "validation_outcome": "passed",
        "tests_status": "passed",
        "build_status": "passed",
        "regression_status": "passed",
        "release_lane": "stable",
        "stable_release_approved": True,
        "sandbox_status": "sandbox_passed",
        "sandbox_result": "sandbox_passed",
        "promotion_status": "promoted_to_stable",
        "baseline_reference": "stable-phase77",
        "candidate_reference": f"{change_id}-candidate",
        "baseline_evidence": {"tests_status": "passed", "build_status": "passed", "regression_status": "passed"},
        "candidate_evidence": {"tests_status": "passed", "build_status": "passed", "regression_status": "passed"},
        "comparison_dimensions": ["tests", "build", "regressions"],
        "promoted_at": "2026-03-23T00:00:00+00:00",
        "monitoring_window": "observation_window",
        "monitoring_status": "monitoring_passed",
        "observation_count": 5,
        "health_signals": {},
        "budgeting_window": _window(),
        "strategic_intent_category": strategic_intent_category,
        "executive_priority_match": executive_priority_match,
        "expected_value": expected_value,
        "expected_cost": expected_cost,
        "expected_complexity": expected_complexity,
        "expected_risk_burden": expected_risk_burden,
        "expected_maintenance_burden": expected_maintenance_burden,
        "priority_value": priority_value,
        "executive_review_required": executive_review_required,
    }


def test_worth_pursuing_when_value_materially_outweighs_burden():
    from NEXUS.governance_layer import evaluate_self_change_value_policy_outcome_safe

    result = evaluate_self_change_value_policy_outcome_safe(
        self_change_contract=_contract(
            change_id="chg-phase78-worth",
            target_files=["C:/FORGE/NEXUS/governance_layer.py"],
            change_type="governance_update",
            expected_value="high",
            expected_cost="low",
            expected_complexity="medium",
            expected_risk_burden="medium",
            expected_maintenance_burden="low",
            priority_value="urgent",
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["status"] == "worth_pursuing"
    assert result["roi_band"] in {"medium_value", "high_value"}
    assert result["recommended_action"] in {"prioritize_change", "proceed_with_governed_change"}


def test_defer_for_later_when_value_is_real_but_not_current_priority():
    from NEXUS.governance_layer import evaluate_self_change_value_policy_outcome_safe

    result = evaluate_self_change_value_policy_outcome_safe(
        self_change_contract=_contract(
            change_id="chg-phase78-defer",
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="summary_refresh",
            strategic_intent_category="operator_experience",
            executive_priority_match=False,
            expected_value="medium",
            expected_cost="medium",
            expected_complexity="low",
            expected_risk_burden="low",
            expected_maintenance_burden="low",
            priority_value="low",
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["status"] == "defer_for_later"
    assert result["value_status"] in {"valuable_but_deferrable", "high_value_but_not_current_focus"}


def test_not_worth_it_when_burden_swamps_return():
    from NEXUS.governance_layer import evaluate_self_change_value_policy_outcome_safe

    result = evaluate_self_change_value_policy_outcome_safe(
        self_change_contract=_contract(
            change_id="chg-phase78-reject",
            target_files=["C:/FORGE/NEXUS/workflow.py"],
            change_type="workflow_extension",
            strategic_intent_category="operator_experience",
            executive_priority_match=False,
            expected_value="low",
            expected_cost="high",
            expected_complexity="high",
            expected_risk_burden="medium",
            expected_maintenance_burden="high",
            priority_value="low",
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["status"] == "not_worth_it"
    assert result["roi_band"] in {"low_value", "negative_value"}
    assert result["recommended_action"] in {"decline_change", "reject_change"}


def test_executive_value_review_required_for_sensitive_high_value_change():
    from NEXUS.governance_layer import evaluate_self_change_value_policy_outcome_safe

    result = evaluate_self_change_value_policy_outcome_safe(
        self_change_contract=_contract(
            change_id="chg-phase78-exec-review",
            target_files=["C:/FORGE/NEXUS/governance_layer.py"],
            change_type="governance_update",
            expected_value="high",
            expected_cost="high",
            expected_complexity="high",
            expected_risk_burden="high",
            expected_maintenance_burden="medium",
            priority_value="high",
            executive_review_required=True,
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["status"] == "executive_value_review_required"
    assert result["recommended_action"] == "request_executive_value_review"


def test_audit_trail_persists_value_policy_fields():
    from NEXUS.execution_package_registry import append_self_change_audit_record_safe, list_self_change_audit_entries

    with _local_test_dir() as tmp:
        write_result = append_self_change_audit_record_safe(
            project_path=str(tmp),
            contract=_contract(
                change_id="chg-phase78-audit",
                target_files=["C:/FORGE/NEXUS/governance_layer.py"],
                change_type="governance_update",
                expected_value="high",
                expected_cost="low",
                expected_complexity="medium",
                expected_risk_burden="medium",
                expected_maintenance_burden="low",
                priority_value="high",
            ),
            outcome_status="completed",
            approval_status="approved",
            validation_status="passed",
            build_status="passed",
            regression_status="passed",
            stable_state_ref="stable-phase77",
            release_lane="stable",
        )
        rows = list_self_change_audit_entries(str(tmp), n=10)

    assert write_result["status"] == "ok"
    assert rows
    assert rows[0]["roi_band"] in {"high_value", "medium_value", "low_value", "negative_value"}
    assert rows[0]["value_outcome"] in {
        "worth_pursuing",
        "defer_for_later",
        "not_worth_it",
        "executive_value_review_required",
    }
    assert rows[0]["expected_value"]
    assert rows[0]["recommended_action"]
    assert "change_value_policy" in rows[0]["governance_trace"]


def test_dashboard_summary_surfaces_value_policy_state():
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    sample_entry = {
        "change_id": "chg-phase78-dashboard",
        "recorded_at": "2026-03-24T12:00:00+00:00",
        "target_files": ["C:/FORGE/NEXUS/governance_layer.py"],
        "change_type": "governance_update",
        "risk_level": "high_risk",
        "protected_zones": ["governance_layer"],
        "protected_zone_hit": True,
        "reason": "Only pursue high-value self-change work.",
        "expected_outcome": "Value policy becomes visible and auditable.",
        "validation_plan": {"summary": "Run full checks.", "checks": ["tests", "build", "regressions"]},
        "rollback_plan": {"summary": "Rollback if needed."},
        "approval_requirement": "mandatory",
        "approval_required": True,
        "approval_status": "approved",
        "approved_by": "operator_alex",
        "outcome_status": "completed",
        "outcome_summary": "Value policy recorded.",
        "validation_status": "passed",
        "build_status": "passed",
        "regression_status": "passed",
        "gate_outcome": "release_ready",
        "release_lane": "stable",
        "sandbox_required": True,
        "sandbox_status": "sandbox_passed",
        "sandbox_result": "sandbox_passed",
        "promotion_status": "promoted_to_stable",
        "promotion_reason": "Already promoted.",
        "baseline_reference": "stable-phase77",
        "candidate_reference": "chg-phase78-dashboard",
        "comparison_dimensions": ["tests", "build", "regressions"],
        "observed_improvement": {},
        "observed_regression": {},
        "net_score": 1.0,
        "confidence_level": 0.9,
        "confidence_band": "strong",
        "comparison_status": "promote_ready",
        "promotion_confidence": "promote_ready",
        "recommendation": "promote",
        "comparison_reason": "Healthy candidate.",
        "promoted_at": "2026-03-23T00:00:00+00:00",
        "monitoring_window": "observation_window",
        "monitoring_status": "monitoring_passed",
        "observation_count": 5,
        "health_signals": {},
        "regression_detected": False,
        "rollback_triggered": False,
        "rollback_trigger_outcome": "no_action",
        "rollback_reason": "",
        "stable_status": "stable_confirmed",
        "rollback_required": False,
        "rollback_id": "",
        "rollback_scope": "protected_core_limited",
        "rollback_target_files": ["C:/FORGE/NEXUS/governance_layer.py"],
        "rollback_target_components": ["governance_layer"],
        "blast_radius_level": "high",
        "rollback_status": "rollback_pending",
        "rollback_result": "",
        "rollback_execution_eligible": False,
        "rollback_approval_required": True,
        "rollback_sequence": ["validate", "approve", "execute", "verify"],
        "rollback_follow_up_validation_required": True,
        "rollback_validation_status": "pending",
        "budgeting_window": _window(),
        "attempted_changes_in_window": 1,
        "successful_changes_in_window": 1,
        "failed_changes_in_window": 0,
        "rollbacks_in_window": 0,
        "protected_zone_changes_in_window": 1,
        "mutation_rate_status": "within_budget",
        "budget_remaining": 0,
        "cool_down_required": False,
        "control_outcome": "budget_available",
        "budget_reason": "",
        "stability_state": "stable",
        "turbulence_level": "low",
        "protected_zone_instability": False,
        "freeze_required": False,
        "freeze_scope": "protected_core_only",
        "recovery_only_mode": False,
        "escalation_required": False,
        "escalation_reason": "",
        "reentry_requirements": [],
        "checkpoint_required": True,
        "checkpoint_reason": "protected_core_high_risk_change",
        "checkpoint_scope": "protected_core_only",
        "checkpoint_status": "checkpoint_satisfied",
        "executive_approval_required": True,
        "manual_hold_active": False,
        "manual_hold_scope": "protected_core_only",
        "hold_reason": "",
        "hold_release_requirements": [],
        "override_status": "checkpoint_enforced",
        "rollout_stage": "limited_cohort",
        "rollout_scope": "protected_core_subset",
        "rollout_status": "rollout_advancing",
        "cohort_type": "protected_core_subset",
        "cohort_size": 3,
        "cohort_selection_reason": "Protected-core rollout remains narrow first.",
        "stage_promotion_required": True,
        "broader_rollout_blocked": True,
        "rollout_reason": "Healthy rollout can advance only one stage at a time.",
        "trust_status": "trusted_current",
        "confidence_age": "1d",
        "decay_state": "fresh",
        "revalidation_required": False,
        "revalidation_reason": "",
        "trust_window": {
            "window_start": "2026-03-23T00:00:00+00:00",
            "window_end": "2026-04-06T00:00:00+00:00",
            "policy": "standard_revalidation",
        },
        "last_validated_at": "2026-03-23T00:00:00+00:00",
        "last_revalidated_at": "",
        "drift_detected": False,
        "trust_outcome": "trust_retained",
        "strategic_intent_category": "governance_strengthening",
        "alignment_status": "aligned",
        "alignment_score": 0.9,
        "alignment_reason": "Aligned with mission.",
        "allowed_goal_class": "governance_strengthening",
        "prohibited_goal_hit": False,
        "executive_priority_match": True,
        "mission_scope": "core_mission",
        "strategic_outcome": "aligned_and_allowed",
        "expected_value": "high",
        "expected_cost": "medium",
        "expected_complexity": "medium",
        "expected_risk_burden": "high",
        "expected_maintenance_burden": "low",
        "roi_band": "high_value",
        "value_outcome": "worth_pursuing",
        "value_status": "high_value_priority_fit",
        "priority_value": "high",
        "value_reason": "High expected value outweighs burden.",
        "recommended_action": "prioritize_change",
        "validation_reasons": ["Value policy recorded."],
        "stable_state_ref": "stable-phase77",
        "success": True,
        "authority_trace": {"actor": "nexus", "authority_status": "authorized"},
        "governance_trace": {"origin": "phase78_test", "change_value_policy": {"status": "recorded"}},
        "contract_status": "valid",
    }

    with patch("NEXUS.registry_dashboard.PROJECTS", {}), patch(
        "NEXUS.execution_package_registry.list_self_change_audit_entries",
        return_value=[sample_entry],
    ):
        summary = build_registry_dashboard_summary()

    governance_summary = summary["self_evolution_governance_summary"]
    assert governance_summary["roi_band_count_total"]["high_value"] == 1
    assert governance_summary["value_outcome_count_total"]["worth_pursuing"] == 1
    assert governance_summary["priority_value_count_total"]["high"] == 1
    assert governance_summary["recommended_action_count_total"]["prioritize_change"] == 1


def main():
    tests = [
        test_worth_pursuing_when_value_materially_outweighs_burden,
        test_defer_for_later_when_value_is_real_but_not_current_priority,
        test_not_worth_it_when_burden_swamps_return,
        test_executive_value_review_required_for_sensitive_high_value_change,
        test_audit_trail_persists_value_policy_fields,
        test_dashboard_summary_surfaces_value_policy_state,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
