"""
Phase 75 staged rollout and promotion cohort policy tests.

Run: python tests/phase75_staged_rollout_cohort_test.py
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
    path = base / f"phase75_{uuid.uuid4().hex[:8]}"
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
    change_id: str = "chg-phase75",
    target_files: list[str],
    change_type: str,
    promotion_status: str = "promoted_to_stable",
    executive_approval_status: str = "approved",
    manual_hold_status: str = "no_hold",
    observation_count: int = 3,
    monitoring_status: str = "monitoring_passed",
    rollback_trigger_outcome: str = "no_action",
    blast_radius_level: str | None = None,
    rollout_stage: str | None = None,
    health_signals: dict | None = None,
    baseline_evidence: dict | None = None,
    candidate_evidence: dict | None = None,
) -> dict:
    contract = {
        "change_id": change_id,
        "target_files": target_files,
        "change_type": change_type,
        "reason": "Phase 18 staged rollout policy evaluation.",
        "expected_outcome": "Forge keeps promoted self-change adoption staged and auditable.",
        "validation_plan": {"summary": "Run tests and verify governance state.", "checks": ["tests", "build", "regressions"]},
        "rollback_plan": {"summary": "Rollback to stable if rollout health degrades.", "last_stable_state_ref": "stable-phase74"},
        "authority_trace": {"actor": "nexus", "requested_action": "propose_self_change", "authority_status": "authorized"},
        "governance_trace": {"origin": "phase75_test"},
        "approval_status": "approved",
        "executive_approval_status": executive_approval_status,
        "manual_hold_status": manual_hold_status,
        "validation_outcome": "passed",
        "tests_status": "passed",
        "build_status": "passed",
        "regression_status": "passed",
        "release_lane": "stable",
        "stable_release_approved": True,
        "sandbox_status": "sandbox_passed",
        "sandbox_result": "sandbox_passed",
        "promotion_status": promotion_status,
        "baseline_reference": "stable-phase74",
        "candidate_reference": f"{change_id}-candidate",
        "baseline_evidence": baseline_evidence
        or {"tests_status": "pending", "build_status": "pending", "regression_status": "pending"},
        "candidate_evidence": candidate_evidence
        or {"tests_status": "passed", "build_status": "passed", "regression_status": "passed"},
        "comparison_dimensions": ["tests", "build", "regressions"],
        "promoted_at": "2026-03-23T00:00:00+00:00",
        "monitoring_window": "observation_window",
        "observation_count": observation_count,
        "monitoring_status": monitoring_status,
        "rollback_trigger_outcome": rollback_trigger_outcome,
        "health_signals": health_signals or {},
        "budgeting_window": _window(),
    }
    if blast_radius_level is not None:
        contract["blast_radius_level"] = blast_radius_level
    if rollout_stage is not None:
        contract["rollout_stage"] = rollout_stage
    return contract


def test_promoted_change_starts_in_limited_cohort_when_staged_rollout_is_required():
    from NEXUS.governance_layer import evaluate_self_change_staged_rollout_outcome_safe

    result = evaluate_self_change_staged_rollout_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/helpers/policy_adapter.py"],
            change_type="adapter_update",
            blast_radius_level="medium",
            observation_count=0,
            monitoring_status="pending_monitoring",
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["status"] == "rollout_pending"
    assert result["rollout_stage"] == "limited_cohort"
    assert result["cohort_type"] in {"low_risk_subset", "project_scoped_subset"}
    assert result["broader_rollout_blocked"] is True


def test_protected_core_high_blast_radius_change_remains_narrower_by_policy():
    from NEXUS.governance_layer import evaluate_self_change_staged_rollout_outcome_safe

    result = evaluate_self_change_staged_rollout_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/governance_layer.py"],
            change_type="governance_update",
            blast_radius_level="high",
            observation_count=5,
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["status"] == "rollout_advancing"
    assert result["rollout_stage"] == "limited_cohort"
    assert result["cohort_type"] == "protected_core_subset"
    assert result["blast_radius_level"] == "high"


def test_broader_rollout_is_blocked_when_checkpoint_or_hold_conditions_fail():
    from NEXUS.governance_layer import evaluate_self_change_staged_rollout_outcome_safe

    result = evaluate_self_change_staged_rollout_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/helpers/policy_adapter.py"],
            change_type="adapter_update",
            blast_radius_level="medium",
            rollout_stage="limited_cohort",
            executive_approval_status="pending",
            manual_hold_status="hold_active",
            observation_count=5,
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["status"] == "rollout_blocked"
    assert result["broader_rollout_blocked"] is True
    assert "checkpoint" in result["rollout_reason"].lower() or "hold" in result["rollout_reason"].lower()


def test_rollout_advances_when_monitoring_and_confidence_remain_healthy():
    from NEXUS.governance_layer import evaluate_self_change_staged_rollout_outcome_safe

    result = evaluate_self_change_staged_rollout_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/helpers/policy_adapter.py"],
            change_type="adapter_update",
            blast_radius_level="medium",
            rollout_stage="limited_cohort",
            observation_count=4,
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["status"] == "rollout_advancing"
    assert result["rollout_stage"] == "broader_cohort"
    assert result["broader_rollout_blocked"] is True


def test_rollout_reverts_when_later_signals_degrade():
    from NEXUS.governance_layer import evaluate_self_change_staged_rollout_outcome_safe

    result = evaluate_self_change_staged_rollout_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/helpers/policy_adapter.py"],
            change_type="adapter_update",
            blast_radius_level="medium",
            rollout_stage="broader_cohort",
            observation_count=5,
            monitoring_status="monitoring_failed",
            rollback_trigger_outcome="rollback_required",
            health_signals={"comparison_degraded": True},
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["status"] == "rollout_reverted"
    assert result["rollout_stage"] == "experimental_only"
    assert result["broader_rollout_blocked"] is True


def test_audit_trail_persists_rollout_and_cohort_fields():
    from NEXUS.execution_package_registry import append_self_change_audit_record_safe, list_self_change_audit_entries

    with _local_test_dir() as tmp:
        write_result = append_self_change_audit_record_safe(
            project_path=str(tmp),
            contract=_contract(
                target_files=["C:/FORGE/NEXUS/governance_layer.py"],
                change_type="governance_update",
                blast_radius_level="high",
                observation_count=5,
            ),
            outcome_status="completed",
            approval_status="approved",
            validation_status="passed",
            build_status="passed",
            regression_status="passed",
            stable_state_ref="stable-phase74",
            release_lane="stable",
        )
        rows = list_self_change_audit_entries(str(tmp), n=10)

    assert write_result["status"] == "ok"
    assert rows
    assert rows[0]["rollout_stage"] in {"experimental_only", "limited_cohort"}
    assert rows[0]["rollout_status"] in {
        "rollout_pending",
        "rollout_blocked",
        "rollout_advancing",
        "rollout_halted",
        "rollout_reverted",
    }
    assert rows[0]["cohort_type"]
    assert isinstance(rows[0]["cohort_size"], int)
    assert rows[0]["cohort_selection_reason"]
    assert "staged_rollout" in rows[0]["governance_trace"]


def test_dashboard_summary_surfaces_rollout_and_cohort_state():
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    sample_entry = {
        "change_id": "chg-phase75-dashboard",
        "recorded_at": "2026-03-23T12:00:00+00:00",
        "target_files": ["C:/FORGE/NEXUS/governance_layer.py"],
        "change_type": "governance_update",
        "risk_level": "high_risk",
        "protected_zones": ["governance_layer"],
        "protected_zone_hit": True,
        "reason": "Keep protected-core rollout narrow until evidence accumulates.",
        "expected_outcome": "Rollout stage and cohort are explicit and visible.",
        "validation_plan": {"summary": "Run full checks.", "checks": ["tests", "build", "regressions"]},
        "rollback_plan": {"summary": "Rollback if needed."},
        "approval_requirement": "mandatory",
        "approval_required": True,
        "approval_status": "approved",
        "approved_by": "operator_alex",
        "outcome_status": "completed",
        "outcome_summary": "Rollout policy recorded.",
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
        "baseline_reference": "stable-phase74",
        "candidate_reference": "chg-phase75-dashboard",
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
        "validation_reasons": ["Rollout policy recorded."],
        "stable_state_ref": "stable-phase74",
        "success": True,
        "authority_trace": {"actor": "nexus", "authority_status": "authorized"},
        "governance_trace": {"origin": "phase75_test", "rollout": "recorded"},
        "contract_status": "valid",
    }

    with patch("NEXUS.registry_dashboard.PROJECTS", {}), patch(
        "NEXUS.execution_package_registry.list_self_change_audit_entries",
        return_value=[sample_entry],
    ):
        summary = build_registry_dashboard_summary()

    governance_summary = summary["self_evolution_governance_summary"]
    assert governance_summary["rollout_stage_count_total"]["limited_cohort"] == 1
    assert governance_summary["rollout_scope_count_total"]["protected_core_subset"] == 1
    assert governance_summary["rollout_status_count_total"]["rollout_advancing"] == 1
    assert governance_summary["cohort_type_count_total"]["protected_core_subset"] == 1
    assert governance_summary["stage_promotion_required_count_total"]["required"] == 1
    assert governance_summary["broader_rollout_blocked_count_total"]["blocked"] == 1


def main():
    tests = [
        test_promoted_change_starts_in_limited_cohort_when_staged_rollout_is_required,
        test_protected_core_high_blast_radius_change_remains_narrower_by_policy,
        test_broader_rollout_is_blocked_when_checkpoint_or_hold_conditions_fail,
        test_rollout_advances_when_monitoring_and_confidence_remain_healthy,
        test_rollout_reverts_when_later_signals_degrade,
        test_audit_trail_persists_rollout_and_cohort_fields,
        test_dashboard_summary_surfaces_rollout_and_cohort_state,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
