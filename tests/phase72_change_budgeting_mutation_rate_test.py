"""
Phase 72 change budgeting and mutation-rate control tests.

Run: python tests/phase72_change_budgeting_mutation_rate_test.py
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
    path = base / f"phase72_{uuid.uuid4().hex[:8]}"
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


def _entry(
    *,
    record_id: str,
    recorded_at: str | None = None,
    success: bool = True,
    outcome_status: str = "completed",
    rollback_required: bool = False,
    rollback_status: str = "rollback_pending",
    rollback_trigger_outcome: str = "monitor_more",
    protected_zone_hit: bool = False,
) -> dict:
    if recorded_at is None:
        start = datetime.fromisoformat(_window()["window_start"])
        recorded_at = (start + timedelta(hours=6)).isoformat()
    return {
        "change_id": record_id,
        "recorded_at": recorded_at,
        "success": success,
        "outcome_status": outcome_status,
        "rollback_required": rollback_required,
        "rollback_status": rollback_status,
        "rollback_trigger_outcome": rollback_trigger_outcome,
        "protected_zone_hit": protected_zone_hit,
    }


def _contract(
    *,
    change_id: str = "chg-phase72",
    target_files: list[str],
    change_type: str,
    approval_status: str = "approved",
    tests_status: str = "passed",
    build_status: str = "passed",
    regression_status: str = "passed",
    budgeting_window: dict | None = None,
) -> dict:
    return {
        "change_id": change_id,
        "target_files": target_files,
        "change_type": change_type,
        "reason": "Phase 15 change budgeting and mutation-rate evaluation.",
        "expected_outcome": "Mutation pressure stays governed and auditable.",
        "validation_plan": {
            "summary": "Run tests, verify build, and confirm no regressions.",
            "checks": ["tests", "build", "regressions"],
        },
        "rollback_plan": {
            "summary": "Rollback to the last stable state if necessary.",
            "last_stable_state_ref": "stable-phase71",
        },
        "authority_trace": {"actor": "nexus", "requested_action": "propose_self_change", "authority_status": "authorized"},
        "governance_trace": {"origin": "phase72_test"},
        "approval_status": approval_status,
        "validation_outcome": "failed" if "failed" in {tests_status, build_status, regression_status} else "passed",
        "tests_status": tests_status,
        "build_status": build_status,
        "regression_status": regression_status,
        "release_lane": "stable",
        "stable_release_approved": True,
        "sandbox_status": "sandbox_passed",
        "sandbox_result": "sandbox_passed",
        "baseline_reference": "stable-phase71",
        "candidate_reference": f"{change_id}-candidate",
        "baseline_evidence": {"tests_status": "passed", "build_status": "passed", "regression_status": "passed"},
        "comparison_dimensions": ["tests", "build", "regressions"],
        "promoted_at": "2026-03-23T00:00:00+00:00",
        "monitoring_window": "observation_window",
        "observation_count": 1,
        "health_signals": {},
        "budgeting_window": budgeting_window or _window(),
    }


def test_low_risk_change_has_budget_available():
    from NEXUS.governance_layer import evaluate_self_change_mutation_budget_outcome_safe

    result = evaluate_self_change_mutation_budget_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="summary_refresh",
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["status"] == "budget_available"
    assert result["budget_remaining"] == 4
    assert result["mutation_rate_status"] in {"within_budget", "elevated"}


def test_protected_high_risk_change_is_throttled_sooner():
    from NEXUS.governance_layer import evaluate_self_change_mutation_budget_outcome_safe

    result = evaluate_self_change_mutation_budget_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/governance_layer.py"],
            change_type="governance_update",
        ),
        recent_audit_entries=[_entry(record_id="prior-protected", protected_zone_hit=True)],
        actor="nexus",
    )

    assert result["protected_zone_hit"] is True
    assert result["status"] == "protected_zone_throttled"
    assert result["cool_down_required"] is True


def test_budget_exhausted_after_repeated_attempts_in_window():
    from NEXUS.governance_layer import evaluate_self_change_mutation_budget_outcome_safe

    history = [_entry(record_id=f"prior-{i}") for i in range(5)]
    result = evaluate_self_change_mutation_budget_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="summary_refresh",
        ),
        recent_audit_entries=history,
        actor="nexus",
    )

    assert result["attempted_changes_in_window"] == 6
    assert result["status"] == "budget_exhausted"
    assert result["budget_remaining"] == 0


def test_cool_down_required_after_repeated_failures_or_rollbacks():
    from NEXUS.governance_layer import evaluate_self_change_mutation_budget_outcome_safe

    history = [
        _entry(record_id="failed-1", success=False, outcome_status="failed"),
        _entry(record_id="rollback-1", success=False, outcome_status="reverted", rollback_required=True, rollback_status="rollback_completed"),
    ]
    result = evaluate_self_change_mutation_budget_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/runtime_dispatcher.py"],
            change_type="routing_policy_update",
        ),
        recent_audit_entries=history,
        actor="nexus",
    )

    assert result["status"] == "cool_down_required"
    assert result["cool_down_required"] is True
    assert result["rollbacks_in_window"] >= 1


def test_change_attempt_blocked_when_mutation_pressure_is_too_high():
    from NEXUS.governance_layer import evaluate_self_change_mutation_budget_outcome_safe

    history = [_entry(record_id=f"prior-{i}") for i in range(6)]
    result = evaluate_self_change_mutation_budget_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="summary_refresh",
        ),
        recent_audit_entries=history,
        actor="nexus",
    )

    assert result["attempted_changes_in_window"] == 7
    assert result["status"] == "change_attempt_blocked"
    assert result["cool_down_required"] is True


def test_audit_trail_persists_budgeting_and_control_outcomes():
    from NEXUS.execution_package_registry import append_self_change_audit_record_safe, list_self_change_audit_entries

    with _local_test_dir() as tmp:
        first = append_self_change_audit_record_safe(
            project_path=str(tmp),
            contract=_contract(
                change_id="chg-phase72-first",
                target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
                change_type="summary_refresh",
            ),
            outcome_status="completed",
            approval_status="approved",
            validation_status="passed",
            build_status="passed",
            regression_status="passed",
            stable_state_ref="stable-phase71",
            release_lane="stable",
        )
        second = append_self_change_audit_record_safe(
            project_path=str(tmp),
            contract=_contract(
                change_id="chg-phase72-second",
                target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
                change_type="summary_refresh",
            ),
            outcome_status="completed",
            approval_status="approved",
            validation_status="passed",
            build_status="passed",
            regression_status="passed",
            stable_state_ref="stable-phase71",
            release_lane="stable",
        )
        rows = list_self_change_audit_entries(str(tmp), n=10)

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert rows
    assert rows[0]["budgeting_window"]["current_window_id"] == _window()["current_window_id"]
    assert rows[0]["attempted_changes_in_window"] >= 2
    assert rows[0]["control_outcome"]
    assert rows[0]["mutation_rate_status"]


def test_dashboard_summary_surfaces_budgeting_and_mutation_rate_status():
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    sample_entry = {
        "change_id": "chg-phase72-dashboard",
        "recorded_at": "2026-03-23T12:00:00+00:00",
        "target_files": ["C:/FORGE/NEXUS/governance_layer.py"],
        "change_type": "governance_update",
        "risk_level": "high_risk",
        "protected_zones": ["governance_layer"],
        "protected_zone_hit": True,
        "reason": "Throttle protected-core mutation pressure.",
        "expected_outcome": "Budgeting remains explicit and auditable.",
        "validation_plan": {"summary": "Run full checks.", "checks": ["tests", "build", "regressions"]},
        "rollback_plan": {"summary": "Rollback if needed."},
        "approval_requirement": "mandatory",
        "approval_required": True,
        "approval_status": "approved",
        "approved_by": "operator_alex",
        "outcome_status": "completed",
        "outcome_summary": "Budgeting control recorded.",
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
        "baseline_reference": "stable-phase71",
        "candidate_reference": "chg-phase72-dashboard",
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
        "monitoring_status": "actively_monitored",
        "observation_count": 1,
        "health_signals": {},
        "regression_detected": False,
        "rollback_triggered": False,
        "rollback_trigger_outcome": "monitor_more",
        "rollback_reason": "",
        "stable_status": "provisionally_stable",
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
        "attempted_changes_in_window": 2,
        "successful_changes_in_window": 1,
        "failed_changes_in_window": 1,
        "rollbacks_in_window": 1,
        "protected_zone_changes_in_window": 2,
        "mutation_rate_status": "cool_down",
        "budget_remaining": 0,
        "cool_down_required": True,
        "control_outcome": "cool_down_required",
        "budget_reason": "Recent failures or rollbacks require a cool-down before more self-change attempts.",
        "validation_reasons": ["Budgeting control recorded."],
        "stable_state_ref": "stable-phase71",
        "success": True,
        "authority_trace": {"actor": "nexus", "authority_status": "authorized"},
        "governance_trace": {"origin": "phase72_test"},
        "contract_status": "valid",
    }

    with patch("NEXUS.registry_dashboard.PROJECTS", {}), patch(
        "NEXUS.execution_package_registry.list_self_change_audit_entries",
        return_value=[sample_entry],
    ):
        summary = build_registry_dashboard_summary()

    governance_summary = summary["self_evolution_governance_summary"]
    assert governance_summary["mutation_rate_status_count_total"]["cool_down"] == 1
    assert governance_summary["control_outcome_count_total"]["cool_down_required"] == 1
    assert governance_summary["cool_down_required_count_total"]["required"] == 1


def main():
    tests = [
        test_low_risk_change_has_budget_available,
        test_protected_high_risk_change_is_throttled_sooner,
        test_budget_exhausted_after_repeated_attempts_in_window,
        test_cool_down_required_after_repeated_failures_or_rollbacks,
        test_change_attempt_blocked_when_mutation_pressure_is_too_high,
        test_audit_trail_persists_budgeting_and_control_outcomes,
        test_dashboard_summary_surfaces_budgeting_and_mutation_rate_status,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
