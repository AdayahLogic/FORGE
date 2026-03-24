"""
Phase 71 rollback execution governance and blast-radius control tests.

Run: python tests/phase71_rollback_execution_governance_test.py
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
    path = base / f"phase71_{uuid.uuid4().hex[:8]}"
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
    change_id: str = "chg-phase71",
    target_files: list[str],
    change_type: str,
    approval_status: str = "approved",
    tests_status: str = "passed",
    build_status: str = "passed",
    regression_status: str = "passed",
    observation_count: int = 1,
    rollback_scope: str | None = None,
    rollback_target_files: list[str] | None = None,
    rollback_target_components: list[str] | None = None,
    blast_radius_level: str | None = None,
    health_signals: dict | None = None,
) -> dict:
    contract = {
        "change_id": change_id,
        "target_files": target_files,
        "change_type": change_type,
        "reason": "Phase 14 rollback execution governance evaluation.",
        "expected_outcome": "Governed rollback execution stays bounded and auditable.",
        "validation_plan": {
            "summary": "Run tests, verify build, and confirm no regressions.",
            "checks": ["tests", "build", "regressions"],
        },
        "rollback_plan": {
            "summary": "Rollback within declared scope and verify the result.",
            "last_stable_state_ref": "stable-phase70",
        },
        "authority_trace": {"actor": "nexus", "requested_action": "propose_self_change", "authority_status": "authorized"},
        "governance_trace": {"origin": "phase71_test"},
        "approval_status": approval_status,
        "validation_outcome": "failed" if "failed" in {tests_status, build_status, regression_status} else "passed",
        "tests_status": tests_status,
        "build_status": build_status,
        "regression_status": regression_status,
        "release_lane": "stable",
        "stable_release_approved": True,
        "sandbox_status": "sandbox_passed",
        "sandbox_result": "sandbox_passed",
        "baseline_reference": "stable-phase70",
        "candidate_reference": f"{change_id}-candidate",
        "baseline_evidence": {"tests_status": "passed", "build_status": "passed", "regression_status": "passed"},
        "comparison_dimensions": ["tests", "build", "regressions"],
        "promoted_at": "2026-03-23T00:00:00+00:00",
        "monitoring_window": "observation_window",
        "observation_count": observation_count,
        "health_signals": health_signals or {},
        "rollback_scope": rollback_scope,
        "rollback_target_files": rollback_target_files or target_files,
        "rollback_target_components": rollback_target_components or [],
    }
    if blast_radius_level is not None:
        contract["blast_radius_level"] = blast_radius_level
    return contract


def test_low_blast_radius_rollback_becomes_eligible_for_governed_execution():
    from NEXUS.governance_layer import evaluate_self_change_rollback_execution_outcome_safe

    result = evaluate_self_change_rollback_execution_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="summary_refresh",
            tests_status="failed",
            rollback_scope="file_only",
        ),
        actor="nexus",
    )

    assert result["blast_radius_level"] == "low"
    assert result["rollback_approval_required"] is False
    assert result["rollback_execution_eligible"] is True
    assert result["status"] == "rollback_completed"


def test_protected_core_rollback_requires_stronger_approval():
    from NEXUS.governance_layer import evaluate_self_change_rollback_execution_outcome_safe

    result = evaluate_self_change_rollback_execution_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/governance_layer.py"],
            change_type="governance_update",
            approval_status="pending",
            health_signals={"protected_zone_degraded": True},
            rollback_scope="protected_core_limited",
        ),
        actor="nexus",
    )

    assert result["protected_zone_hit"] is True
    assert result["blast_radius_level"] == "high"
    assert result["rollback_approval_required"] is True
    assert result["status"] == "rollback_blocked"


def test_rollback_scope_remains_bounded_to_declared_files():
    from NEXUS.governance_layer import evaluate_self_change_rollback_execution_outcome_safe

    result = evaluate_self_change_rollback_execution_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="summary_refresh",
            tests_status="failed",
            rollback_scope="file_only",
            rollback_target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
        ),
        actor="nexus",
    )

    assert result["rollback_scope"] == "file_only"
    assert result["rollback_target_files"] == ["C:/FORGE/NEXUS/registry_dashboard.py"]
    assert result["status"] == "rollback_completed"


def test_rollback_blocked_when_required_approval_is_missing():
    from NEXUS.governance_layer import evaluate_self_change_rollback_execution_outcome_safe

    result = evaluate_self_change_rollback_execution_outcome_safe(
        self_change_contract=_contract(
            target_files=[
                "C:/FORGE/NEXUS/registry_dashboard.py",
                "C:/FORGE/NEXUS/execution_package_registry.py",
            ],
            change_type="summary_refresh",
            approval_status="pending",
            tests_status="failed",
            rollback_scope="project_only",
            blast_radius_level="medium",
        ),
        actor="nexus",
    )

    assert result["rollback_approval_required"] is True
    assert result["status"] == "rollback_blocked"
    assert "approval" in result["rollback_result"].lower()


def test_valid_bounded_rollback_path_completes():
    from NEXUS.governance_layer import evaluate_self_change_rollback_execution_outcome_safe

    result = evaluate_self_change_rollback_execution_outcome_safe(
        self_change_contract=_contract(
            target_files=[
                "C:/FORGE/NEXUS/registry_dashboard.py",
                "C:/FORGE/NEXUS/execution_package_registry.py",
            ],
            change_type="summary_refresh",
            tests_status="failed",
            rollback_scope="project_only",
            blast_radius_level="medium",
            approval_status="approved",
        ),
        actor="nexus",
    )

    assert result["status"] == "rollback_completed"
    assert result["rollback_validation_status"] == "required"


def test_invalid_scope_expansion_is_blocked():
    from NEXUS.governance_layer import evaluate_self_change_rollback_execution_outcome_safe

    result = evaluate_self_change_rollback_execution_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="summary_refresh",
            tests_status="failed",
            rollback_scope="file_only",
            rollback_target_files=[
                "C:/FORGE/NEXUS/registry_dashboard.py",
                "C:/FORGE/NEXUS/governance_layer.py",
            ],
        ),
        actor="nexus",
    )

    assert result["status"] == "rollback_blocked"
    assert "scope" in result["rollback_result"].lower()


def test_audit_trail_persists_rollback_execution_outcome():
    from NEXUS.execution_package_registry import append_self_change_audit_record_safe, list_self_change_audit_entries

    with _local_test_dir() as tmp:
        write_result = append_self_change_audit_record_safe(
            project_path=str(tmp),
            contract=_contract(
                target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
                change_type="summary_refresh",
                tests_status="failed",
                rollback_scope="file_only",
            ),
            outcome_status="completed",
            approval_status="approved",
            validation_status="failed",
            build_status="passed",
            regression_status="passed",
            stable_state_ref="stable-phase70",
            release_lane="stable",
        )
        rows = list_self_change_audit_entries(str(tmp), n=10)

    assert write_result["status"] == "ok"
    assert rows
    assert rows[0]["rollback_scope"] == "file_only"
    assert rows[0]["blast_radius_level"] == "low"
    assert rows[0]["rollback_status"] == "rollback_completed"
    assert rows[0]["rollback_result"]


def test_dashboard_summary_surfaces_rollback_execution_and_blast_radius():
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    sample_entry = {
        "change_id": "chg-phase71-dashboard",
        "recorded_at": "2026-03-23T00:00:00+00:00",
        "target_files": ["C:/FORGE/NEXUS/governance_layer.py"],
        "change_type": "governance_update",
        "risk_level": "high_risk",
        "protected_zones": ["governance_layer"],
        "protected_zone_hit": True,
        "reason": "Execute a governed rollback for a protected-core regression.",
        "expected_outcome": "Protected-core rollback remains gated and visible.",
        "validation_plan": {"summary": "Run full checks.", "checks": ["tests", "build", "regressions"]},
        "rollback_plan": {"summary": "Revert protected core to prior stable state."},
        "approval_requirement": "mandatory",
        "approval_required": True,
        "approval_status": "approved",
        "approved_by": "operator_alex",
        "outcome_status": "completed",
        "outcome_summary": "Rollback executed in governed mode.",
        "validation_status": "failed",
        "build_status": "passed",
        "regression_status": "passed",
        "gate_outcome": "release_ready",
        "release_lane": "stable",
        "sandbox_required": True,
        "sandbox_status": "sandbox_passed",
        "sandbox_result": "sandbox_passed",
        "promotion_status": "promoted_to_stable",
        "promotion_reason": "Promoted before monitoring detected degradation.",
        "baseline_reference": "stable-phase70",
        "candidate_reference": "chg-phase71-dashboard",
        "comparison_dimensions": ["tests", "build", "regressions"],
        "observed_improvement": {},
        "observed_regression": {"tests": {"baseline": "passed", "candidate": "failed", "delta": -1.0}},
        "net_score": -1.0,
        "confidence_level": 0.85,
        "confidence_band": "strong",
        "comparison_status": "regression_detected",
        "promotion_confidence": "regression_detected",
        "recommendation": "rollback",
        "comparison_reason": "Regression detected after promotion.",
        "promoted_at": "2026-03-23T00:00:00+00:00",
        "monitoring_window": "observation_window",
        "monitoring_status": "monitoring_failed",
        "observation_count": 1,
        "health_signals": {"protected_zone_degraded": True},
        "regression_detected": True,
        "rollback_triggered": True,
        "rollback_trigger_outcome": "rollback_required",
        "rollback_reason": "Protected-zone post-promotion monitoring detected degraded behavior.",
        "stable_status": "rollback_pending",
        "rollback_required": True,
        "rollback_id": "rollback-phase71-dashboard",
        "rollback_scope": "protected_core_limited",
        "rollback_target_files": ["C:/FORGE/NEXUS/governance_layer.py"],
        "rollback_target_components": ["governance_layer"],
        "blast_radius_level": "high",
        "rollback_status": "rollback_completed",
        "rollback_result": "Rollback completed within its governed scope.",
        "rollback_execution_eligible": True,
        "rollback_approval_required": True,
        "rollback_sequence": ["validate", "approve", "execute", "verify"],
        "rollback_follow_up_validation_required": True,
        "rollback_validation_status": "required",
        "validation_reasons": ["Protected-zone rollback required approval and completed within scope."],
        "stable_state_ref": "stable-phase70",
        "success": True,
        "authority_trace": {"actor": "nexus", "authority_status": "authorized"},
        "governance_trace": {"origin": "phase71_test"},
        "contract_status": "valid",
    }

    with patch("NEXUS.registry_dashboard.PROJECTS", {}), patch(
        "NEXUS.execution_package_registry.list_self_change_audit_entries",
        return_value=[sample_entry],
    ):
        summary = build_registry_dashboard_summary()

    governance_summary = summary["self_evolution_governance_summary"]
    assert governance_summary["rollback_scope_count_total"]["protected_core_limited"] == 1
    assert governance_summary["blast_radius_count_total"]["high"] == 1
    assert governance_summary["rollback_status_count_total"]["rollback_completed"] == 1
    assert governance_summary["rollback_follow_up_validation_required_count_total"]["required"] == 1


def main():
    tests = [
        test_low_blast_radius_rollback_becomes_eligible_for_governed_execution,
        test_protected_core_rollback_requires_stronger_approval,
        test_rollback_scope_remains_bounded_to_declared_files,
        test_rollback_blocked_when_required_approval_is_missing,
        test_valid_bounded_rollback_path_completes,
        test_invalid_scope_expansion_is_blocked,
        test_audit_trail_persists_rollback_execution_outcome,
        test_dashboard_summary_surfaces_rollback_execution_and_blast_radius,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
