"""
Phase 77 strategic intent charter and goal-bound self-change policy tests.

Run: python tests/phase77_strategic_intent_charter_test.py
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
    path = base / f"phase77_{uuid.uuid4().hex[:8]}"
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
    strategic_intent_category: str | None = None,
    executive_priorities: list[str] | None = None,
    mission_scope: str | None = None,
    executive_priority_match: bool | None = None,
    prohibited_goal_hit: bool = False,
    executive_review_required: bool = False,
    reason: str = "Phase 20 strategic intent evaluation.",
    expected_outcome: str = "Forge keeps self-change aligned to mission.",
) -> dict:
    contract = {
        "change_id": change_id,
        "target_files": target_files,
        "change_type": change_type,
        "reason": reason,
        "expected_outcome": expected_outcome,
        "validation_plan": {"summary": "Run tests and inspect governance.", "checks": ["tests", "build", "regressions"]},
        "rollback_plan": {"summary": "Rollback if governance or alignment degrades.", "last_stable_state_ref": "stable-phase76"},
        "authority_trace": {"actor": "nexus", "requested_action": "propose_self_change", "authority_status": "authorized"},
        "governance_trace": {"origin": "phase77_test"},
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
        "baseline_reference": "stable-phase76",
        "candidate_reference": f"{change_id}-candidate",
        "baseline_evidence": {"tests_status": "passed", "build_status": "passed", "regression_status": "passed"},
        "candidate_evidence": {"tests_status": "passed", "build_status": "passed", "regression_status": "passed"},
        "comparison_dimensions": ["tests", "build", "regressions"],
        "promoted_at": "2026-03-23T00:00:00+00:00",
        "last_validated_at": "2026-03-23T00:00:00+00:00",
        "monitoring_window": "observation_window",
        "monitoring_status": "monitoring_passed",
        "observation_count": 5,
        "health_signals": {},
        "budgeting_window": _window(),
    }
    if strategic_intent_category is not None:
        contract["strategic_intent_category"] = strategic_intent_category
    if executive_priorities is not None:
        contract["executive_priorities"] = executive_priorities
    if mission_scope is not None:
        contract["mission_scope"] = mission_scope
    if executive_priority_match is not None:
        contract["executive_priority_match"] = executive_priority_match
    if prohibited_goal_hit:
        contract["prohibited_goal_hit"] = True
    if executive_review_required:
        contract["executive_review_required"] = True
    return contract


def test_aligned_and_allowed_for_mission_consistent_safety_or_governance_work():
    from NEXUS.governance_layer import evaluate_self_change_strategic_intent_outcome_safe

    result = evaluate_self_change_strategic_intent_outcome_safe(
        self_change_contract=_contract(
            change_id="chg-phase77-aligned",
            target_files=["C:/FORGE/NEXUS/governance_layer.py"],
            change_type="governance_update",
            strategic_intent_category="governance_strengthening",
            executive_priorities=["governance_strengthening"],
            executive_priority_match=True,
            reason="Strengthen governance checkpoints and audit policy.",
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["status"] == "aligned_and_allowed"
    assert result["strategic_outcome"] == "aligned_and_allowed"
    assert result["alignment_status"] == "aligned"
    assert result["prohibited_goal_hit"] is False


def test_aligned_but_low_priority_for_useful_non_urgent_change():
    from NEXUS.governance_layer import evaluate_self_change_strategic_intent_outcome_safe

    result = evaluate_self_change_strategic_intent_outcome_safe(
        self_change_contract=_contract(
            change_id="chg-phase77-low-priority",
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="summary_refresh",
            strategic_intent_category="operator_experience",
            executive_priorities=["governance_strengthening"],
            executive_priority_match=False,
            reason="Improve operator dashboard visibility without changing controls.",
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["status"] == "aligned_but_low_priority"
    assert result["strategic_outcome"] == "aligned_but_low_priority"
    assert result["alignment_status"] == "aligned_low_priority"
    assert result["executive_priority_match"] is False


def test_out_of_scope_for_change_outside_current_mission_scope():
    from NEXUS.governance_layer import evaluate_self_change_strategic_intent_outcome_safe

    result = evaluate_self_change_strategic_intent_outcome_safe(
        self_change_contract=_contract(
            change_id="chg-phase77-out-of-scope",
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="marketing_surface",
            strategic_intent_category="mission_out_of_scope",
            mission_scope="outside_scope",
            reason="Add marketing style features unrelated to Forge's governed mission.",
            expected_outcome="Increase engagement through non-mission presentation work.",
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["status"] == "out_of_scope"
    assert result["strategic_outcome"] == "out_of_scope"
    assert result["alignment_status"] == "out_of_scope"


def test_prohibited_direction_for_governance_weakening_or_hidden_authority():
    from NEXUS.governance_layer import evaluate_self_change_strategic_intent_outcome_safe

    result = evaluate_self_change_strategic_intent_outcome_safe(
        self_change_contract=_contract(
            change_id="chg-phase77-prohibited",
            target_files=["C:/FORGE/NEXUS/authority_model.py"],
            change_type="authority_update",
            strategic_intent_category="governance_strengthening",
            prohibited_goal_hit=True,
            reason="Introduce a hidden_authority path to bypass_approval for convenience.",
            expected_outcome="Allow self_authorize behavior during emergencies.",
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["status"] == "prohibited_direction"
    assert result["strategic_outcome"] == "prohibited_direction"
    assert result["alignment_status"] == "prohibited"
    assert result["prohibited_goal_hit"] is True


def test_executive_review_required_for_sensitive_priority_dependent_change():
    from NEXUS.governance_layer import evaluate_self_change_strategic_intent_outcome_safe

    result = evaluate_self_change_strategic_intent_outcome_safe(
        self_change_contract=_contract(
            change_id="chg-phase77-exec-review",
            target_files=["C:/FORGE/NEXUS/governance_layer.py"],
            change_type="governance_update",
            strategic_intent_category="controlled_scaling",
            executive_priorities=["reliability_improvement"],
            executive_priority_match=False,
            executive_review_required=True,
            reason="Sensitive controlled scaling change for protected governance surfaces.",
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["status"] == "executive_review_required"
    assert result["strategic_outcome"] == "executive_review_required"
    assert result["alignment_status"] == "executive_review_required"


def test_audit_trail_persists_strategic_alignment_outcomes():
    from NEXUS.execution_package_registry import append_self_change_audit_record_safe, list_self_change_audit_entries

    with _local_test_dir() as tmp:
        write_result = append_self_change_audit_record_safe(
            project_path=str(tmp),
            contract=_contract(
                change_id="chg-phase77-audit",
                target_files=["C:/FORGE/NEXUS/governance_layer.py"],
                change_type="governance_update",
                strategic_intent_category="governance_strengthening",
                executive_priorities=["governance_strengthening"],
                executive_priority_match=True,
                reason="Strengthen governed policy enforcement.",
            ),
            outcome_status="completed",
            approval_status="approved",
            validation_status="passed",
            build_status="passed",
            regression_status="passed",
            stable_state_ref="stable-phase76",
            release_lane="stable",
        )
        rows = list_self_change_audit_entries(str(tmp), n=10)

    assert write_result["status"] == "ok"
    assert rows
    assert rows[0]["strategic_intent_category"] == "governance_strengthening"
    assert rows[0]["strategic_outcome"] in {
        "aligned_and_allowed",
        "aligned_but_low_priority",
        "out_of_scope",
        "prohibited_direction",
        "executive_review_required",
    }
    assert "strategic_intent" in rows[0]["governance_trace"]


def test_dashboard_summary_surfaces_strategic_alignment_state():
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    sample_entry = {
        "change_id": "chg-phase77-dashboard",
        "recorded_at": "2026-03-23T12:00:00+00:00",
        "target_files": ["C:/FORGE/NEXUS/governance_layer.py"],
        "change_type": "governance_update",
        "risk_level": "high_risk",
        "protected_zones": ["governance_layer"],
        "protected_zone_hit": True,
        "reason": "Strengthen governed mission alignment visibility.",
        "expected_outcome": "Strategic alignment remains explicit and auditable.",
        "validation_plan": {"summary": "Run full checks.", "checks": ["tests", "build", "regressions"]},
        "rollback_plan": {"summary": "Rollback if needed."},
        "approval_requirement": "mandatory",
        "approval_required": True,
        "approval_status": "approved",
        "approved_by": "operator_alex",
        "outcome_status": "completed",
        "outcome_summary": "Strategic policy recorded.",
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
        "baseline_reference": "stable-phase76",
        "candidate_reference": "chg-phase77-dashboard",
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
        "rollout_status": "rollout_blocked",
        "cohort_type": "protected_core_subset",
        "cohort_size": 3,
        "cohort_selection_reason": "Protected-core rollout remains narrow first.",
        "stage_promotion_required": True,
        "broader_rollout_blocked": True,
        "rollout_reason": "Strategic mission alignment is recorded.",
        "trust_status": "trusted_current",
        "confidence_age": "0d",
        "decay_state": "fresh",
        "revalidation_required": False,
        "revalidation_reason": "",
        "trust_window": {"window_start": "2026-03-23T00:00:00+00:00", "window_end": "2026-03-30T00:00:00+00:00", "policy": "protected_core_revalidation"},
        "last_validated_at": "2026-03-23T00:00:00+00:00",
        "last_revalidated_at": "",
        "drift_detected": False,
        "trust_outcome": "trust_retained",
        "strategic_intent_category": "governance_strengthening",
        "alignment_status": "aligned",
        "alignment_score": 0.95,
        "alignment_reason": "Governance strengthening matches charter and priority.",
        "allowed_goal_class": "governance_strengthening",
        "prohibited_goal_hit": False,
        "executive_priority_match": True,
        "mission_scope": "core_mission",
        "strategic_outcome": "aligned_and_allowed",
        "validation_reasons": ["Strategic policy recorded."],
        "stable_state_ref": "stable-phase76",
        "success": True,
        "authority_trace": {"actor": "nexus", "authority_status": "authorized"},
        "governance_trace": {"origin": "phase77_test", "strategic_intent": {"status": "recorded"}},
        "contract_status": "valid",
    }

    with patch("NEXUS.registry_dashboard.PROJECTS", {}), patch(
        "NEXUS.execution_package_registry.list_self_change_audit_entries",
        return_value=[sample_entry],
    ):
        summary = build_registry_dashboard_summary()

    governance_summary = summary["self_evolution_governance_summary"]
    assert governance_summary["strategic_intent_category_count_total"]["governance_strengthening"] == 1
    assert governance_summary["alignment_status_count_total"]["aligned"] == 1
    assert governance_summary["prohibited_goal_hit_count_total"]["not_hit"] == 1
    assert governance_summary["executive_priority_match_count_total"]["matched"] == 1
    assert governance_summary["mission_scope_count_total"]["core_mission"] == 1
    assert governance_summary["strategic_outcome_count_total"]["aligned_and_allowed"] == 1


def main():
    tests = [
        test_aligned_and_allowed_for_mission_consistent_safety_or_governance_work,
        test_aligned_but_low_priority_for_useful_non_urgent_change,
        test_out_of_scope_for_change_outside_current_mission_scope,
        test_prohibited_direction_for_governance_weakening_or_hidden_authority,
        test_executive_review_required_for_sensitive_priority_dependent_change,
        test_audit_trail_persists_strategic_alignment_outcomes,
        test_dashboard_summary_surfaces_strategic_alignment_state,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
