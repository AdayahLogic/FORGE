"""
Phase 69 self-change comparative scoring and promotion confidence tests.

Run: python tests/phase69_self_change_comparative_scoring_test.py
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
    path = base / f"phase69_{uuid.uuid4().hex[:8]}"
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
    baseline_reference: str = "stable-phase68",
    candidate_reference: str = "candidate-phase69",
    baseline_evidence: dict | None = None,
    candidate_evidence: dict | None = None,
    comparison_dimensions: list[str] | None = None,
    approval_status: str = "approved",
    validation_outcome: str = "passed",
    tests_status: str = "passed",
    build_status: str = "passed",
    regression_status: str = "passed",
    release_lane: str = "experimental",
    stable_release_approved: bool = False,
    sandbox_status: str | None = None,
    sandbox_result: str | None = None,
    application_state: str = "proposed",
) -> dict:
    contract = {
        "change_id": "chg-phase69",
        "target_files": target_files,
        "change_type": change_type,
        "reason": "Phase 12 comparative scoring evaluation.",
        "expected_outcome": "Explicit comparative score and promotion confidence.",
        "validation_plan": {
            "summary": "Run tests, verify build, and confirm no regressions.",
            "checks": ["tests", "build", "regressions"],
        },
        "rollback_plan": {
            "summary": "Revert to the last stable state if the change fails after application.",
            "last_stable_state_ref": "stable-phase68",
        },
        "authority_trace": {"actor": "nexus", "requested_action": "propose_self_change", "authority_status": "authorized"},
        "governance_trace": {"origin": "phase69_test"},
        "approval_status": approval_status,
        "validation_outcome": validation_outcome,
        "tests_status": tests_status,
        "build_status": build_status,
        "regression_status": regression_status,
        "release_lane": release_lane,
        "stable_release_approved": stable_release_approved,
        "application_state": application_state,
        "baseline_reference": baseline_reference,
        "candidate_reference": candidate_reference,
        "baseline_evidence": baseline_evidence or {},
        "candidate_evidence": candidate_evidence or {},
    }
    if comparison_dimensions is not None:
        contract["comparison_dimensions"] = comparison_dimensions
    if sandbox_status is not None:
        contract["sandbox_status"] = sandbox_status
    if sandbox_result is not None:
        contract["sandbox_result"] = sandbox_result
    return contract


def test_valid_comparison_produces_promote_ready_with_strong_confidence():
    from NEXUS.self_evolution_governance import evaluate_self_change_comparative_scoring_safe

    result = evaluate_self_change_comparative_scoring_safe(
        _contract(
            target_files=["C:/FORGE/NEXUS/runtime_dispatcher.py"],
            change_type="routing_policy_update",
            release_lane="stable",
            sandbox_status="sandbox_passed",
            sandbox_result="sandbox_passed",
            baseline_evidence={
                "tests_status": "pending",
                "build_status": "pending",
                "regression_status": "pending",
                "governance_compatible": False,
                "authority_compatible": False,
            },
            comparison_dimensions=["tests", "build", "regressions", "governance", "authority"],
        )
    )

    assert result["status"] == "promote_ready"
    assert result["promotion_confidence"] == "promote_ready"
    assert result["confidence_band"] == "strong"
    assert result["recommendation"] == "promote"


def test_comparison_can_keep_experimental_with_moderate_evidence():
    from NEXUS.governance_layer import evaluate_self_change_comparative_scoring_outcome_safe

    result = evaluate_self_change_comparative_scoring_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/runtime_dispatcher.py"],
            change_type="routing_policy_update",
            release_lane="experimental",
            sandbox_status="sandbox_passed",
            sandbox_result="sandbox_passed",
            baseline_evidence={
                "tests_status": "passed",
                "build_status": "passed",
                "regression_status": "passed",
                "governance_compatible": True,
                "authority_compatible": True,
            },
            comparison_dimensions=["tests", "build", "regressions", "governance", "authority"],
        ),
        actor="nexus",
    )

    assert result["status"] == "keep_experimental"
    assert result["promotion_confidence"] == "keep_experimental"
    assert result["confidence_band"] == "moderate"
    assert result["recommendation"] == "hold_experimental"


def test_incomplete_baseline_or_candidate_data_yields_insufficient_evidence():
    from NEXUS.self_evolution_governance import evaluate_self_change_comparative_scoring_safe

    result = evaluate_self_change_comparative_scoring_safe(
        _contract(
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="summary_refresh",
            baseline_reference="",
            baseline_evidence={},
            comparison_dimensions=["tests"],
        )
    )

    assert result["status"] == "insufficient_evidence"
    assert result["promotion_confidence"] == "insufficient_evidence"
    assert result["recommendation"] == "hold_experimental"


def test_candidate_worse_than_baseline_yields_regression_detected():
    from NEXUS.self_evolution_governance import evaluate_self_change_comparative_scoring_safe

    result = evaluate_self_change_comparative_scoring_safe(
        _contract(
            target_files=["C:/FORGE/NEXUS/runtime_dispatcher.py"],
            change_type="routing_policy_update",
            release_lane="experimental",
            sandbox_status="sandbox_passed",
            sandbox_result="sandbox_passed",
            regression_status="failed",
            validation_outcome="failed",
            baseline_evidence={
                "tests_status": "passed",
                "build_status": "passed",
                "regression_status": "passed",
            },
            comparison_dimensions=["tests", "build", "regressions"],
        )
    )

    assert result["status"] == "regression_detected"
    assert result["promotion_confidence"] == "regression_detected"
    assert result["recommendation"] == "reject"


def test_weak_confidence_can_block_promotion_even_after_sandbox_pass():
    from NEXUS.self_evolution_governance import evaluate_self_change_comparative_scoring_safe

    result = evaluate_self_change_comparative_scoring_safe(
        _contract(
            target_files=["C:/FORGE/NEXUS/runtime_dispatcher.py"],
            change_type="routing_policy_update",
            release_lane="stable",
            sandbox_status="sandbox_passed",
            sandbox_result="sandbox_passed",
            baseline_evidence={"tests_status": "pending"},
            comparison_dimensions=["tests"],
        )
    )

    assert result["status"] == "confidence_too_weak"
    assert result["promotion_confidence"] == "confidence_too_weak"
    assert result["confidence_band"] == "weak"


def test_audit_trail_persists_comparative_scoring_and_confidence():
    from NEXUS.execution_package_registry import append_self_change_audit_record_safe, list_self_change_audit_entries

    with _local_test_dir() as tmp:
        write_result = append_self_change_audit_record_safe(
            project_path=str(tmp),
            contract=_contract(
                target_files=["C:/FORGE/NEXUS/runtime_dispatcher.py"],
                change_type="routing_policy_update",
                release_lane="stable",
                sandbox_status="sandbox_passed",
                sandbox_result="sandbox_passed",
                baseline_evidence={
                    "tests_status": "pending",
                    "build_status": "pending",
                    "regression_status": "pending",
                    "governance_compatible": False,
                    "authority_compatible": False,
                },
                comparison_dimensions=["tests", "build", "regressions", "governance", "authority"],
            ),
            outcome_status="completed",
            approval_status="approved",
            validation_status="passed",
            build_status="passed",
            regression_status="passed",
            stable_state_ref="stable-phase68",
            release_lane="stable",
        )
        rows = list_self_change_audit_entries(str(tmp), n=10)

    assert write_result["status"] == "ok"
    assert rows
    assert rows[0]["baseline_reference"] == "stable-phase68"
    assert rows[0]["candidate_reference"] == "candidate-phase69"
    assert rows[0]["comparison_status"] == "promote_ready"
    assert rows[0]["confidence_band"] == "strong"
    assert rows[0]["recommendation"] == "promote"
    assert rows[0]["monitoring_status"] == "pending_monitoring"
    assert rows[0]["stable_status"] == "provisionally_stable"


def test_dashboard_summary_surfaces_comparative_scoring_and_confidence():
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    sample_entry = {
        "change_id": "chg-phase69-dashboard",
        "recorded_at": "2026-03-23T00:00:00+00:00",
        "target_files": ["C:/FORGE/NEXUS/runtime_dispatcher.py"],
        "change_type": "routing_update",
        "risk_level": "high_risk",
        "protected_zones": ["runtime_dispatcher"],
        "protected_zone_hit": True,
        "reason": "Compare candidate against baseline.",
        "expected_outcome": "Promotion confidence remains explicit.",
        "validation_plan": {"summary": "Run full checks.", "checks": ["tests", "build", "regressions"]},
        "rollback_plan": {"summary": "Revert to stable."},
        "approval_requirement": "mandatory",
        "approval_required": True,
        "approval_status": "approved",
        "approved_by": "operator_alex",
        "outcome_status": "completed",
        "outcome_summary": "Comparison completed.",
        "validation_status": "passed",
        "build_status": "passed",
        "regression_status": "passed",
        "gate_outcome": "release_ready",
        "release_lane": "experimental",
        "sandbox_required": True,
        "sandbox_status": "sandbox_passed",
        "sandbox_result": "sandbox_passed",
        "promotion_status": "kept_experimental",
        "promotion_reason": "Sandbox-passed self-change satisfied release gating but remains in the experimental lane.",
        "baseline_reference": "stable-phase68",
        "candidate_reference": "chg-phase69-dashboard",
        "comparison_dimensions": ["tests", "build", "regressions", "governance", "authority"],
        "observed_improvement": {"governance": {"baseline": False, "candidate": True, "delta": 2.0}},
        "observed_regression": {},
        "net_score": 2.0,
        "confidence_level": 0.72,
        "confidence_band": "moderate",
        "comparison_status": "keep_experimental",
        "promotion_confidence": "keep_experimental",
        "recommendation": "hold_experimental",
        "comparison_reason": "Candidate evidence is positive but not strong enough for broader promotion beyond the experimental lane.",
        "promoted_at": "2026-03-23T00:00:00+00:00",
        "monitoring_window": "observation_window",
        "monitoring_status": "actively_monitored",
        "observation_count": 2,
        "health_signals": {"tests_healthy": True, "build_healthy": True, "regressions_healthy": True, "protected_zone_healthy": True},
        "regression_detected": False,
        "rollback_triggered": False,
        "rollback_trigger_outcome": "monitor_more",
        "rollback_reason": "Promoted self-change remains under post-promotion monitoring.",
        "stable_status": "provisionally_stable",
        "rollback_required": False,
        "validation_reasons": ["Self-change satisfied approval, validation, and rollback requirements."],
        "stable_state_ref": "stable-phase68",
        "success": True,
        "authority_trace": {"actor": "nexus", "authority_status": "authorized"},
        "governance_trace": {"origin": "phase69_test"},
        "contract_status": "valid",
    }

    with patch("NEXUS.registry_dashboard.PROJECTS", {}), patch(
        "NEXUS.execution_package_registry.list_self_change_audit_entries",
        return_value=[sample_entry],
    ):
        summary = build_registry_dashboard_summary()

    governance_summary = summary["self_evolution_governance_summary"]
    assert governance_summary["comparison_status_count_total"]["keep_experimental"] == 1
    assert governance_summary["confidence_band_count_total"]["moderate"] == 1
    assert governance_summary["promotion_confidence_count_total"]["keep_experimental"] == 1
    assert governance_summary["recommendation_count_total"]["hold_experimental"] == 1
    assert governance_summary["monitoring_status_count_total"]["actively_monitored"] == 1
    assert governance_summary["stable_status_count_total"]["provisionally_stable"] == 1


def main():
    tests = [
        test_valid_comparison_produces_promote_ready_with_strong_confidence,
        test_comparison_can_keep_experimental_with_moderate_evidence,
        test_incomplete_baseline_or_candidate_data_yields_insufficient_evidence,
        test_candidate_worse_than_baseline_yields_regression_detected,
        test_weak_confidence_can_block_promotion_even_after_sandbox_pass,
        test_audit_trail_persists_comparative_scoring_and_confidence,
        test_dashboard_summary_surfaces_comparative_scoring_and_confidence,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
