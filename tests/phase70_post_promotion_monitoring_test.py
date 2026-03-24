"""
Phase 70 post-promotion monitoring and rollback trigger tests.

Run: python tests/phase70_post_promotion_monitoring_test.py
"""

from __future__ import annotations

import shutil
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@contextmanager
def _local_test_dir():
    base = ROOT / ".tmp_test_runs"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"phase70_{uuid.uuid4().hex[:8]}"
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


def _contract(
    *,
    target_files: list[str],
    change_type: str,
    baseline_evidence: dict | None = None,
    comparison_dimensions: list[str] | None = None,
    release_lane: str = "stable",
    stable_release_approved: bool = True,
    sandbox_status: str = "sandbox_passed",
    sandbox_result: str = "sandbox_passed",
    promoted_at: str = "2026-03-23T00:00:00+00:00",
    observation_count: int = 0,
    health_signals: dict | None = None,
    validation_outcome: str = "passed",
    tests_status: str = "passed",
    build_status: str = "passed",
    regression_status: str = "passed",
) -> dict:
    contract = {
        "change_id": "chg-phase70",
        "target_files": target_files,
        "change_type": change_type,
        "reason": "Phase 13 post-promotion monitoring evaluation.",
        "expected_outcome": "Explicit monitoring and rollback-trigger decision.",
        "validation_plan": {
            "summary": "Run tests, verify build, and confirm no regressions.",
            "checks": ["tests", "build", "regressions"],
        },
        "rollback_plan": {
            "summary": "Revert to the last stable state if post-promotion monitoring fails.",
            "last_stable_state_ref": "stable-phase69",
        },
        "authority_trace": {"actor": "nexus", "requested_action": "propose_self_change", "authority_status": "authorized"},
        "governance_trace": {"origin": "phase70_test"},
        "approval_status": "approved",
        "validation_outcome": validation_outcome,
        "tests_status": tests_status,
        "build_status": build_status,
        "regression_status": regression_status,
        "release_lane": release_lane,
        "stable_release_approved": stable_release_approved,
        "sandbox_status": sandbox_status,
        "sandbox_result": sandbox_result,
        "baseline_reference": "stable-phase69",
        "candidate_reference": "candidate-phase70",
        "baseline_evidence": baseline_evidence
        or {
            "tests_status": "pending",
            "build_status": "pending",
            "regression_status": "pending",
            "governance_compatible": False,
            "authority_compatible": False,
        },
        "comparison_dimensions": comparison_dimensions or ["tests", "build", "regressions", "governance", "authority"],
        "promoted_at": promoted_at,
        "monitoring_window": "observation_window",
        "observation_count": observation_count,
        "health_signals": health_signals or {},
    }
    return contract


def test_promoted_change_enters_pending_monitoring():
    from NEXUS.self_evolution_governance import evaluate_self_change_post_promotion_monitoring_safe

    result = evaluate_self_change_post_promotion_monitoring_safe(
        _contract(
            target_files=["C:/FORGE/NEXUS/runtime_dispatcher.py"],
            change_type="routing_policy_update",
            observation_count=0,
        )
    )

    assert result["status"] == "pending_monitoring"
    assert result["monitoring_status"] == "pending_monitoring"
    assert result["stable_status"] == "provisionally_stable"


def test_monitoring_window_can_progress_to_monitoring_passed():
    from NEXUS.self_evolution_governance import evaluate_self_change_post_promotion_monitoring_safe

    result = evaluate_self_change_post_promotion_monitoring_safe(
        _contract(
            target_files=["C:/FORGE/NEXUS/runtime_dispatcher.py"],
            change_type="routing_policy_update",
            observation_count=3,
        )
    )

    assert result["status"] == "no_action"
    assert result["monitoring_status"] == "monitoring_passed"
    assert result["stable_status"] == "stable_confirmed"


def test_monitoring_failure_can_trigger_rollback_recommended():
    from NEXUS.self_evolution_governance import evaluate_self_change_post_promotion_monitoring_safe

    result = evaluate_self_change_post_promotion_monitoring_safe(
        _contract(
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="summary_refresh",
            observation_count=2,
            tests_status="failed",
        )
    )

    assert result["monitoring_status"] == "monitoring_failed"
    assert result["status"] == "rollback_recommended"
    assert result["stable_status"] == "stable_degraded"


def test_protected_zone_degradation_causes_stronger_rollback_outcome():
    from NEXUS.governance_layer import evaluate_self_change_post_promotion_monitoring_outcome_safe

    result = evaluate_self_change_post_promotion_monitoring_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/governance_layer.py"],
            change_type="governance_update",
            observation_count=1,
            health_signals={"protected_zone_degraded": True},
        ),
        actor="nexus",
    )

    assert result["protected_zone_hit"] is True
    assert result["status"] == "rollback_required"
    assert result["stable_status"] == "rollback_pending"


def test_stable_status_progresses_to_stable_confirmed():
    from NEXUS.self_evolution_governance import evaluate_self_change_post_promotion_monitoring_safe

    result = evaluate_self_change_post_promotion_monitoring_safe(
        _contract(
            target_files=["C:/FORGE/NEXUS/runtime_dispatcher.py"],
            change_type="routing_policy_update",
            observation_count=4,
        )
    )

    assert result["stable_status"] == "stable_confirmed"
    assert result["rollback_trigger_outcome"] == "no_action"


def test_failed_monitoring_can_mark_rollback_pending():
    from NEXUS.self_evolution_governance import evaluate_self_change_post_promotion_monitoring_safe

    result = evaluate_self_change_post_promotion_monitoring_safe(
        _contract(
            target_files=["C:/FORGE/NEXUS/runtime_dispatcher.py"],
            change_type="routing_policy_update",
            observation_count=1,
            regression_status="failed",
            validation_outcome="failed",
        )
    )

    assert result["monitoring_status"] == "monitoring_failed"
    assert result["stable_status"] == "rollback_pending"
    assert result["rollback_triggered"] is True


def test_audit_trail_persists_monitoring_and_rollback_results():
    from NEXUS.execution_package_registry import append_self_change_audit_record_safe, list_self_change_audit_entries

    with _local_test_dir() as tmp:
        write_result = append_self_change_audit_record_safe(
            project_path=str(tmp),
            contract=_contract(
                target_files=["C:/FORGE/NEXUS/runtime_dispatcher.py"],
                change_type="routing_policy_update",
                observation_count=3,
            ),
            outcome_status="completed",
            approval_status="approved",
            validation_status="passed",
            build_status="passed",
            regression_status="passed",
            stable_state_ref="stable-phase69",
            release_lane="stable",
        )
        rows = list_self_change_audit_entries(str(tmp), n=10)

    assert write_result["status"] == "ok"
    assert rows
    assert rows[0]["monitoring_status"] == "monitoring_passed"
    assert rows[0]["rollback_trigger_outcome"] == "no_action"
    assert rows[0]["stable_status"] == "stable_confirmed"


def test_dashboard_summary_surfaces_monitoring_and_rollback_states():
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    sample_entry = {
        "change_id": "chg-phase70-dashboard",
        "recorded_at": "2026-03-23T00:00:00+00:00",
        "target_files": ["C:/FORGE/NEXUS/governance_layer.py"],
        "change_type": "governance_update",
        "risk_level": "high_risk",
        "protected_zones": ["governance_layer"],
        "protected_zone_hit": True,
        "reason": "Monitor protected-zone behavior after promotion.",
        "expected_outcome": "Rollback if degradation appears.",
        "validation_plan": {"summary": "Run full checks.", "checks": ["tests", "build", "regressions"]},
        "rollback_plan": {"summary": "Revert to stable."},
        "approval_requirement": "mandatory",
        "approval_required": True,
        "approval_status": "approved",
        "approved_by": "operator_alex",
        "outcome_status": "completed",
        "outcome_summary": "Protected-zone degradation detected.",
        "validation_status": "passed",
        "build_status": "passed",
        "regression_status": "passed",
        "gate_outcome": "release_ready",
        "release_lane": "stable",
        "sandbox_required": True,
        "sandbox_status": "sandbox_passed",
        "sandbox_result": "sandbox_passed",
        "promotion_status": "promoted_to_stable",
        "promotion_reason": "Sandbox-passed self-change satisfied promotion criteria and was promoted to stable.",
        "baseline_reference": "stable-phase69",
        "candidate_reference": "chg-phase70-dashboard",
        "comparison_dimensions": ["tests", "build", "regressions", "governance", "authority"],
        "observed_improvement": {"governance": {"baseline": False, "candidate": True, "delta": 2.0}},
        "observed_regression": {},
        "net_score": 2.0,
        "confidence_level": 0.91,
        "confidence_band": "strong",
        "comparison_status": "promote_ready",
        "promotion_confidence": "promote_ready",
        "recommendation": "promote",
        "comparison_reason": "Candidate outperformed the baseline with strong confidence.",
        "promoted_at": "2026-03-23T00:00:00+00:00",
        "monitoring_window": "observation_window",
        "monitoring_status": "monitoring_failed",
        "observation_count": 2,
        "health_signals": {"tests_healthy": True, "build_healthy": True, "regressions_healthy": True, "protected_zone_healthy": False, "protected_zone_degraded": True},
        "regression_detected": False,
        "rollback_triggered": True,
        "rollback_trigger_outcome": "rollback_required",
        "rollback_reason": "Protected-zone post-promotion monitoring detected degraded behavior.",
        "stable_status": "rollback_pending",
        "rollback_required": True,
        "validation_reasons": ["Protected-zone post-promotion monitoring detected degraded behavior."],
        "stable_state_ref": "stable-phase69",
        "success": True,
        "authority_trace": {"actor": "nexus", "authority_status": "authorized"},
        "governance_trace": {"origin": "phase70_test"},
        "contract_status": "valid",
    }

    with patch("NEXUS.registry_dashboard.PROJECTS", {}), patch(
        "NEXUS.execution_package_registry.list_self_change_audit_entries",
        return_value=[sample_entry],
    ):
        summary = build_registry_dashboard_summary()

    governance_summary = summary["self_evolution_governance_summary"]
    assert governance_summary["monitoring_status_count_total"]["monitoring_failed"] == 1
    assert governance_summary["rollback_trigger_outcome_count_total"]["rollback_required"] == 1
    assert governance_summary["stable_status_count_total"]["rollback_pending"] == 1


def main():
    tests = [
        test_promoted_change_enters_pending_monitoring,
        test_monitoring_window_can_progress_to_monitoring_passed,
        test_monitoring_failure_can_trigger_rollback_recommended,
        test_protected_zone_degradation_causes_stronger_rollback_outcome,
        test_stable_status_progresses_to_stable_confirmed,
        test_failed_monitoring_can_mark_rollback_pending,
        test_audit_trail_persists_monitoring_and_rollback_results,
        test_dashboard_summary_surfaces_monitoring_and_rollback_states,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
