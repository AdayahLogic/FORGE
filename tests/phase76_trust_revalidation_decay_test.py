"""
Phase 76 trust revalidation and confidence decay policy tests.

Run: python tests/phase76_trust_revalidation_decay_test.py
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
    path = base / f"phase76_{uuid.uuid4().hex[:8]}"
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


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _window(start: datetime, days: int) -> dict:
    return {
        "window_start": _iso(start),
        "window_end": _iso(start + timedelta(days=days)),
        "policy": "protected_core_revalidation" if days <= 7 else "standard_revalidation",
    }


def _contract(
    *,
    change_id: str,
    target_files: list[str],
    change_type: str,
    last_validated_at: datetime | None = None,
    last_revalidated_at: datetime | None = None,
    trust_window: dict | None = None,
    rollout_stage: str = "limited_cohort",
    health_signals: dict | None = None,
    revalidation_successful: bool = False,
) -> dict:
    now = datetime.now(timezone.utc)
    validated_at = last_validated_at or (now - timedelta(days=2))
    contract = {
        "change_id": change_id,
        "target_files": target_files,
        "change_type": change_type,
        "reason": "Phase 19 trust aging policy evaluation.",
        "expected_outcome": "Forge derives explicit trust freshness and revalidation state.",
        "validation_plan": {"summary": "Run tests and inspect trust state.", "checks": ["tests", "build", "regressions"]},
        "rollback_plan": {"summary": "Rollback if trust degrades materially.", "last_stable_state_ref": "stable-phase75"},
        "authority_trace": {"actor": "nexus", "requested_action": "propose_self_change", "authority_status": "authorized"},
        "governance_trace": {"origin": "phase76_test", "recorded_at": _iso(validated_at)},
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
        "promotion_reason": "Governed promotion complete.",
        "baseline_reference": "stable-phase75",
        "candidate_reference": f"{change_id}-candidate",
        "baseline_evidence": {"tests_status": "passed", "build_status": "passed", "regression_status": "passed"},
        "candidate_evidence": {"tests_status": "passed", "build_status": "passed", "regression_status": "passed"},
        "comparison_dimensions": ["tests", "build", "regressions"],
        "promoted_at": _iso(validated_at),
        "monitoring_window": "observation_window",
        "monitoring_status": "monitoring_passed",
        "observation_count": 5,
        "health_signals": health_signals or {},
        "last_validated_at": _iso(validated_at),
        "rollout_stage": rollout_stage,
        "budgeting_window": {
            "current_window_id": now.strftime("window-%Y%m%d"),
            "window_start": _iso(now.replace(hour=0, minute=0, second=0, microsecond=0)),
            "window_end": _iso(now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)),
        },
    }
    if trust_window is not None:
        contract["trust_window"] = trust_window
    if last_revalidated_at is not None:
        contract["last_revalidated_at"] = _iso(last_revalidated_at)
    if revalidation_successful:
        contract["revalidation_successful"] = True
    return contract


def test_trusted_current_under_fresh_evidence():
    from NEXUS.governance_layer import evaluate_self_change_trust_revalidation_outcome_safe

    result = evaluate_self_change_trust_revalidation_outcome_safe(
        self_change_contract=_contract(
            change_id="chg-phase76-fresh",
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="summary_refresh",
            last_validated_at=datetime.now(timezone.utc) - timedelta(days=2),
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["status"] == "trusted_current"
    assert result["trust_status"] == "trusted_current"
    assert result["trust_outcome"] == "trust_retained"
    assert result["revalidation_required"] is False


def test_trust_aging_after_evidence_ages():
    from NEXUS.governance_layer import evaluate_self_change_trust_revalidation_outcome_safe

    result = evaluate_self_change_trust_revalidation_outcome_safe(
        self_change_contract=_contract(
            change_id="chg-phase76-aging",
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="summary_refresh",
            last_validated_at=datetime.now(timezone.utc) - timedelta(days=10),
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["status"] == "trust_aging"
    assert result["trust_status"] == "trust_aging"
    assert result["decay_state"] == "aging"
    assert result["revalidation_required"] is False


def test_revalidation_required_when_trust_window_is_exceeded():
    from NEXUS.governance_layer import evaluate_self_change_trust_revalidation_outcome_safe

    validated_at = datetime.now(timezone.utc) - timedelta(days=16)
    result = evaluate_self_change_trust_revalidation_outcome_safe(
        self_change_contract=_contract(
            change_id="chg-phase76-revalidate",
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="summary_refresh",
            last_validated_at=validated_at,
            trust_window=_window(validated_at, 14),
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["status"] == "revalidation_required"
    assert result["trust_status"] == "revalidation_required"
    assert result["trust_outcome"] == "revalidation_required"
    assert result["revalidation_required"] is True
    assert "trust_window_exceeded" in result["revalidation_reason"]


def test_trust_degraded_on_detected_drift():
    from NEXUS.governance_layer import evaluate_self_change_trust_revalidation_outcome_safe

    result = evaluate_self_change_trust_revalidation_outcome_safe(
        self_change_contract=_contract(
            change_id="chg-phase76-degraded",
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="summary_refresh",
            last_validated_at=datetime.now(timezone.utc) - timedelta(days=5),
            health_signals={"drift_detected": True},
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["status"] == "trust_degraded"
    assert result["trust_status"] == "trust_degraded"
    assert result["drift_detected"] is True
    assert result["trust_outcome"] == "trust_degraded"


def test_trust_expired_under_stronger_decay_conditions():
    from NEXUS.governance_layer import evaluate_self_change_trust_revalidation_outcome_safe

    validated_at = datetime.now(timezone.utc) - timedelta(days=20)
    result = evaluate_self_change_trust_revalidation_outcome_safe(
        self_change_contract=_contract(
            change_id="chg-phase76-expired",
            target_files=["C:/FORGE/NEXUS/governance_layer.py"],
            change_type="governance_update",
            last_validated_at=validated_at,
            trust_window=_window(validated_at, 7),
            health_signals={"drift_detected": True, "comparison_degraded": True},
        ),
        recent_audit_entries=[
            {"change_id": "prior-caution-1", "trust_status": "trust_aging"},
            {"change_id": "prior-caution-2", "stability_state": "caution"},
        ],
        actor="nexus",
    )

    assert result["status"] == "trust_expired"
    assert result["trust_status"] == "trust_expired"
    assert result["decay_state"] == "expired"
    assert result["trust_outcome"] == "trust_expired"


def test_trust_restored_after_successful_revalidation():
    from NEXUS.governance_layer import evaluate_self_change_trust_revalidation_outcome_safe

    now = datetime.now(timezone.utc)
    result = evaluate_self_change_trust_revalidation_outcome_safe(
        self_change_contract=_contract(
            change_id="chg-phase76-restored",
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="summary_refresh",
            last_validated_at=now - timedelta(days=10),
            last_revalidated_at=now - timedelta(hours=12),
            revalidation_successful=True,
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["status"] == "trust_restored"
    assert result["trust_status"] == "trusted_current"
    assert result["trust_outcome"] == "trust_restored"
    assert result["last_revalidated_at"]


def test_audit_trail_persists_trust_and_revalidation_outcomes():
    from NEXUS.execution_package_registry import append_self_change_audit_record_safe, list_self_change_audit_entries

    with _local_test_dir() as tmp:
        write_result = append_self_change_audit_record_safe(
            project_path=str(tmp),
            contract=_contract(
                change_id="chg-phase76-audit",
                target_files=["C:/FORGE/NEXUS/governance_layer.py"],
                change_type="governance_update",
                last_validated_at=datetime.now(timezone.utc) - timedelta(days=12),
                health_signals={"drift_detected": True},
            ),
            outcome_status="completed",
            approval_status="approved",
            validation_status="passed",
            build_status="passed",
            regression_status="passed",
            stable_state_ref="stable-phase75",
            release_lane="stable",
        )
        rows = list_self_change_audit_entries(str(tmp), n=10)

    assert write_result["status"] == "ok"
    assert rows
    assert rows[0]["trust_status"] in {
        "trusted_current",
        "trust_aging",
        "revalidation_required",
        "trust_degraded",
        "trust_expired",
    }
    assert rows[0]["decay_state"]
    assert "window_start" in rows[0]["trust_window"]
    assert "trust_revalidation" in rows[0]["governance_trace"]


def test_dashboard_summary_surfaces_trust_revalidation_state():
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    sample_entry = {
        "change_id": "chg-phase76-dashboard",
        "recorded_at": "2026-03-23T12:00:00+00:00",
        "target_files": ["C:/FORGE/NEXUS/governance_layer.py"],
        "change_type": "governance_update",
        "risk_level": "high_risk",
        "protected_zones": ["governance_layer"],
        "protected_zone_hit": True,
        "reason": "Trust for protected-core change must be refreshed.",
        "expected_outcome": "Trust state is visible and auditable.",
        "validation_plan": {"summary": "Run full checks.", "checks": ["tests", "build", "regressions"]},
        "rollback_plan": {"summary": "Rollback if trust degrades."},
        "approval_requirement": "mandatory",
        "approval_required": True,
        "approval_status": "approved",
        "approved_by": "operator_alex",
        "outcome_status": "completed",
        "outcome_summary": "Trust policy recorded.",
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
        "baseline_reference": "stable-phase75",
        "candidate_reference": "chg-phase76-dashboard",
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
        "budgeting_window": {
            "current_window_id": "window-20260323",
            "window_start": "2026-03-23T00:00:00+00:00",
            "window_end": "2026-03-24T00:00:00+00:00",
        },
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
        "rollout_reason": "Trust evidence must be refreshed.",
        "trust_status": "revalidation_required",
        "confidence_age": "16d",
        "decay_state": "stale",
        "revalidation_required": True,
        "revalidation_reason": "trust_window_exceeded, rollout_expansion_requires_fresher_trust",
        "trust_window": {
            "window_start": "2026-03-07T00:00:00+00:00",
            "window_end": "2026-03-14T00:00:00+00:00",
            "policy": "protected_core_revalidation",
        },
        "last_validated_at": "2026-03-07T00:00:00+00:00",
        "last_revalidated_at": "",
        "drift_detected": False,
        "trust_outcome": "revalidation_required",
        "validation_reasons": ["Trust policy recorded."],
        "stable_state_ref": "stable-phase75",
        "success": True,
        "authority_trace": {"actor": "nexus", "authority_status": "authorized"},
        "governance_trace": {"origin": "phase76_test", "trust_revalidation": {"status": "recorded"}},
        "contract_status": "valid",
    }

    with patch("NEXUS.registry_dashboard.PROJECTS", {}), patch(
        "NEXUS.execution_package_registry.list_self_change_audit_entries",
        return_value=[sample_entry],
    ):
        summary = build_registry_dashboard_summary()

    governance_summary = summary["self_evolution_governance_summary"]
    assert governance_summary["trust_status_count_total"]["revalidation_required"] == 1
    assert governance_summary["decay_state_count_total"]["stale"] == 1
    assert governance_summary["revalidation_required_count_total"]["required"] == 1
    assert governance_summary["trust_outcome_count_total"]["revalidation_required"] == 1
    assert governance_summary["drift_detected_count_total"]["not_detected"] == 1


def main():
    tests = [
        test_trusted_current_under_fresh_evidence,
        test_trust_aging_after_evidence_ages,
        test_revalidation_required_when_trust_window_is_exceeded,
        test_trust_degraded_on_detected_drift,
        test_trust_expired_under_stronger_decay_conditions,
        test_trust_restored_after_successful_revalidation,
        test_audit_trail_persists_trust_and_revalidation_outcomes,
        test_dashboard_summary_surfaces_trust_revalidation_state,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
