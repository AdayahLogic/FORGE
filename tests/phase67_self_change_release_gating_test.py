"""
Phase 67 self-change validation and release-gating tests.

Run: python tests/phase67_self_change_release_gating_test.py
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
    path = base / f"phase67_{uuid.uuid4().hex[:8]}"
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
    approval_status: str = "optional",
    validation_outcome: str = "passed",
    tests_status: str = "passed",
    build_status: str = "passed",
    regression_status: str = "passed",
    release_lane: str = "stable",
    application_state: str = "proposed",
    stable_release_approved: bool = False,
) -> dict:
    return {
        "change_id": "chg-phase67",
        "target_files": target_files,
        "change_type": change_type,
        "reason": "Phase 10 release-gating evaluation.",
        "expected_outcome": "Explicit gate and release-lane outcome.",
        "validation_plan": {
            "summary": "Run tests, verify build, and confirm no regressions.",
            "checks": ["tests", "build", "regressions"],
        },
        "rollback_plan": {
            "summary": "Revert to the last stable state if the change fails after application.",
            "last_stable_state_ref": "stable-phase66",
        },
        "authority_trace": {"actor": "nexus", "requested_action": "propose_self_change"},
        "governance_trace": {"origin": "phase67_test"},
        "approval_status": approval_status,
        "validation_outcome": validation_outcome,
        "tests_status": tests_status,
        "build_status": build_status,
        "regression_status": regression_status,
        "release_lane": release_lane,
        "application_state": application_state,
        "stable_release_approved": stable_release_approved,
    }


def test_valid_low_risk_change_becomes_release_ready():
    from NEXUS.self_evolution_governance import evaluate_self_change_release_gate_safe

    result = evaluate_self_change_release_gate_safe(
        _contract(
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="summary_refresh",
        )
    )

    assert result["status"] == "release_ready"
    assert result["gate_outcome"] == "release_ready"
    assert result["release_lane"] == "stable"


def test_protected_zone_high_risk_change_blocked_without_approval():
    from NEXUS.governance_layer import evaluate_self_change_release_gate_outcome_safe

    result = evaluate_self_change_release_gate_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/governance_layer.py"],
            change_type="governance_update",
            approval_status="pending",
            release_lane="experimental",
        ),
        actor="nexus",
    )

    assert result["status"] == "blocked"
    assert result["gate_outcome"] == "blocked_missing_approval"
    assert result["protected_zone_hit"] is True


def test_protected_zone_high_risk_change_blocked_without_validation():
    from NEXUS.self_evolution_governance import evaluate_self_change_release_gate_safe

    result = evaluate_self_change_release_gate_safe(
        _contract(
            target_files=["C:/FORGE/NEXUS/runtime_dispatcher.py"],
            change_type="routing_update",
            approval_status="approved",
            validation_outcome="pending",
            tests_status="pending",
            build_status="pending",
            regression_status="pending",
            release_lane="experimental",
        )
    )

    assert result["status"] == "blocked"
    assert result["gate_outcome"] == "blocked_protected_zone"


def test_high_risk_defaults_to_experimental_lane():
    from NEXUS.self_evolution_governance import evaluate_self_change_release_gate_safe

    result = evaluate_self_change_release_gate_safe(
        _contract(
            target_files=["C:/FORGE/NEXUS/project_autopilot.py"],
            change_type="autopilot_guardrail_update",
            approval_status="approved",
            release_lane="stable",
        )
    )

    assert result["release_lane"] == "experimental"


def test_low_risk_validated_change_qualifies_for_stable_lane():
    from NEXUS.self_evolution_governance import evaluate_self_change_release_gate_safe

    result = evaluate_self_change_release_gate_safe(
        _contract(
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="summary_refresh",
            release_lane="stable",
        )
    )

    assert result["gate_outcome"] == "release_ready"
    assert result["release_lane"] == "stable"


def test_failed_regression_after_attempt_triggers_rollback_required():
    from NEXUS.self_evolution_governance import evaluate_self_change_release_gate_safe

    result = evaluate_self_change_release_gate_safe(
        _contract(
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="summary_refresh",
            validation_outcome="failed",
            regression_status="failed",
            application_state="attempted",
        )
    )

    assert result["status"] == "rollback_required"
    assert result["gate_outcome"] == "rollback_required"
    assert result["rollback_required"] is True


def test_audit_trail_persists_gate_outcome():
    from NEXUS.execution_package_registry import append_self_change_audit_record_safe, list_self_change_audit_entries

    with _local_test_dir() as tmp:
        write_result = append_self_change_audit_record_safe(
            project_path=str(tmp),
            contract=_contract(
                target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
                change_type="summary_refresh",
                release_lane="stable",
            ),
            outcome_status="completed",
            approval_status="optional",
            validation_status="passed",
            build_status="passed",
            regression_status="passed",
            stable_state_ref="stable-phase66",
            release_lane="stable",
        )
        rows = list_self_change_audit_entries(str(tmp), n=10)

    assert write_result["status"] == "ok"
    assert rows
    assert rows[0]["gate_outcome"] == "release_ready"
    assert rows[0]["release_lane"] == "stable"
    assert rows[0]["sandbox_required"] is False
    assert rows[0]["sandbox_result"] == "sandbox_not_required"
    assert rows[0]["promotion_status"] == "promoted_to_stable"
    assert rows[0]["comparison_status"] == "insufficient_evidence"
    assert rows[0]["promotion_confidence"] == "insufficient_evidence"
    assert rows[0]["recommendation"] == "hold_experimental"


def test_dashboard_summary_surfaces_release_gating():
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    sample_entry = {
        "change_id": "chg-phase67-dashboard",
        "recorded_at": "2026-03-23T00:00:00+00:00",
        "target_files": ["C:/FORGE/NEXUS/runtime_dispatcher.py"],
        "change_type": "routing_update",
        "risk_level": "high_risk",
        "protected_zones": ["runtime_dispatcher"],
        "protected_zone_hit": True,
        "reason": "Protect release gating.",
        "expected_outcome": "Blocked without approval.",
        "validation_plan": {"summary": "Run full checks.", "checks": ["tests", "build", "regressions"]},
        "rollback_plan": {"summary": "Revert to stable."},
        "approval_requirement": "mandatory",
        "approval_required": True,
        "approval_status": "pending",
        "approved_by": "",
        "outcome_status": "proposed",
        "outcome_summary": "",
        "validation_status": "pending",
        "build_status": "pending",
        "regression_status": "pending",
        "gate_outcome": "blocked_missing_approval",
        "release_lane": "experimental",
        "sandbox_required": True,
        "sandbox_status": "sandbox_pending",
        "sandbox_result": "sandbox_pending",
        "promotion_status": "promotion_pending",
        "promotion_reason": "Sandbox-required self-change remains pending until sandbox evaluation completes successfully.",
        "baseline_reference": "",
        "candidate_reference": "chg-phase67-dashboard",
        "comparison_dimensions": [],
        "observed_improvement": {},
        "observed_regression": {},
        "net_score": 0.0,
        "confidence_level": 0.0,
        "confidence_band": "weak",
        "comparison_status": "insufficient_evidence",
        "promotion_confidence": "insufficient_evidence",
        "recommendation": "hold_experimental",
        "comparison_reason": "Comparative scoring requires explicit baseline/candidate references and usable evidence across at least one shared dimension.",
        "rollback_required": False,
        "validation_reasons": ["Protected-zone self-change requires mandatory approval before advancing."],
        "stable_state_ref": "stable-phase66",
        "success": False,
        "authority_trace": {"actor": "nexus"},
        "governance_trace": {"origin": "phase67_test"},
        "contract_status": "valid",
    }

    with patch("NEXUS.registry_dashboard.PROJECTS", {}), patch(
        "NEXUS.execution_package_registry.list_self_change_audit_entries",
        return_value=[sample_entry],
    ):
        summary = build_registry_dashboard_summary()

    governance_summary = summary["self_evolution_governance_summary"]
    assert governance_summary["gate_outcome_count_total"]["blocked_missing_approval"] == 1
    assert governance_summary["release_lane_count_total"]["experimental"] == 1
    assert governance_summary["validation_outcome_count_total"]["pending"] == 1
    assert governance_summary["sandbox_status_count_total"]["sandbox_pending"] == 1
    assert governance_summary["promotion_status_count_total"]["promotion_pending"] == 1
    assert governance_summary["comparison_status_count_total"]["insufficient_evidence"] == 1
    assert governance_summary["confidence_band_count_total"]["weak"] == 1


def main():
    tests = [
        test_valid_low_risk_change_becomes_release_ready,
        test_protected_zone_high_risk_change_blocked_without_approval,
        test_protected_zone_high_risk_change_blocked_without_validation,
        test_high_risk_defaults_to_experimental_lane,
        test_low_risk_validated_change_qualifies_for_stable_lane,
        test_failed_regression_after_attempt_triggers_rollback_required,
        test_audit_trail_persists_gate_outcome,
        test_dashboard_summary_surfaces_release_gating,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
