"""
Phase 74 executive checkpoint policy and manual hold override tests.

Run: python tests/phase74_executive_checkpoint_hold_test.py
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
    path = base / f"phase74_{uuid.uuid4().hex[:8]}"
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
    rollback_required: bool = False,
    rollback_status: str = "rollback_pending",
    rollback_trigger_outcome: str = "monitor_more",
    monitoring_status: str = "monitoring_passed",
    mutation_rate_status: str = "within_budget",
    control_outcome: str = "budget_available",
    protected_zone_hit: bool = False,
    protected_zone_instability: bool = False,
    regression_detected: bool = False,
) -> dict:
    start = datetime.fromisoformat(_window()["window_start"])
    return {
        "change_id": record_id,
        "recorded_at": (start + timedelta(hours=6)).isoformat(),
        "outcome_status": "completed",
        "rollback_required": rollback_required,
        "rollback_status": rollback_status,
        "rollback_trigger_outcome": rollback_trigger_outcome,
        "monitoring_status": monitoring_status,
        "mutation_rate_status": mutation_rate_status,
        "control_outcome": control_outcome,
        "protected_zone_hit": protected_zone_hit,
        "protected_zone_instability": protected_zone_instability,
        "regression_detected": regression_detected,
    }


def _contract(
    *,
    change_id: str = "chg-phase74",
    target_files: list[str],
    change_type: str,
    approval_status: str = "approved",
    executive_approval_status: str = "pending",
    manual_hold_status: str = "no_hold",
    manual_hold_scope: str = "project_scoped",
    hold_reason: str = "",
    tests_status: str = "passed",
    build_status: str = "passed",
    regression_status: str = "passed",
    observation_count: int = 3,
    health_signals: dict | None = None,
    rollback_scope: str | None = None,
    blast_radius_level: str | None = None,
    rollback_status: str | None = None,
) -> dict:
    contract = {
        "change_id": change_id,
        "target_files": target_files,
        "change_type": change_type,
        "reason": "Phase 17 executive checkpoint and manual hold evaluation.",
        "expected_outcome": "Sensitive self-change requires explicit executive gating and auditable hold behavior.",
        "validation_plan": {"summary": "Run tests and verify governance state.", "checks": ["tests", "build", "regressions"]},
        "rollback_plan": {"summary": "Rollback to stable if governance requires it.", "last_stable_state_ref": "stable-phase73"},
        "authority_trace": {"actor": "nexus", "requested_action": "propose_self_change", "authority_status": "authorized"},
        "governance_trace": {"origin": "phase74_test"},
        "approval_status": approval_status,
        "executive_approval_status": executive_approval_status,
        "manual_hold_status": manual_hold_status,
        "manual_hold_scope": manual_hold_scope,
        "hold_reason": hold_reason,
        "validation_outcome": "failed" if "failed" in {tests_status, build_status, regression_status} else "passed",
        "tests_status": tests_status,
        "build_status": build_status,
        "regression_status": regression_status,
        "release_lane": "stable",
        "stable_release_approved": True,
        "sandbox_status": "sandbox_passed",
        "sandbox_result": "sandbox_passed",
        "baseline_reference": "stable-phase73",
        "candidate_reference": f"{change_id}-candidate",
        "baseline_evidence": {"tests_status": "passed", "build_status": "passed", "regression_status": "passed"},
        "comparison_dimensions": ["tests", "build", "regressions"],
        "promoted_at": "2026-03-23T00:00:00+00:00",
        "monitoring_window": "observation_window",
        "observation_count": observation_count,
        "health_signals": health_signals or {},
        "budgeting_window": _window(),
    }
    if rollback_scope is not None:
        contract["rollback_scope"] = rollback_scope
    if blast_radius_level is not None:
        contract["blast_radius_level"] = blast_radius_level
    if rollback_status is not None:
        contract["rollback_status"] = rollback_status
    return contract


def test_protected_core_high_risk_change_requires_executive_checkpoint():
    from NEXUS.governance_layer import evaluate_self_change_executive_checkpoint_outcome_safe

    result = evaluate_self_change_executive_checkpoint_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/governance_layer.py"],
            change_type="governance_update",
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["checkpoint_required"] is True
    assert result["checkpoint_scope"] == "protected_core_only"
    assert result["checkpoint_status"] == "checkpoint_required"
    assert result["status"] == "checkpoint_required"


def test_manual_hold_becomes_active_and_blocks_sensitive_advancement():
    from NEXUS.governance_layer import evaluate_self_change_executive_checkpoint_outcome_safe

    result = evaluate_self_change_executive_checkpoint_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/governance_layer.py"],
            change_type="governance_update",
            manual_hold_status="hold_active",
            manual_hold_scope="protected_core_only",
            hold_reason="Executive requested a protected-core pause.",
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["manual_hold_active"] is True
    assert result["status"] == "hold_active"
    assert result["checkpoint_status"] == "blocked_by_hold"
    assert "pause" in result["reason"].lower() or "hold" in result["reason"].lower()


def test_hold_scope_remains_bounded():
    from NEXUS.governance_layer import evaluate_self_change_executive_checkpoint_outcome_safe

    result = evaluate_self_change_executive_checkpoint_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/governance_layer.py"],
            change_type="governance_update",
            manual_hold_status="hold_active",
            manual_hold_scope="protected_core_only",
            hold_reason="Hold protected core only.",
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["manual_hold_scope"] == "protected_core_only"


def test_hold_release_requires_explicit_conditions():
    from NEXUS.governance_layer import evaluate_self_change_executive_checkpoint_outcome_safe

    blocked = evaluate_self_change_executive_checkpoint_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/governance_layer.py"],
            change_type="governance_update",
            manual_hold_status="hold_released",
            manual_hold_scope="protected_core_only",
            executive_approval_status="pending",
            hold_reason="Attempt release without executive signoff.",
        ),
        recent_audit_entries=[],
        actor="nexus",
    )
    released = evaluate_self_change_executive_checkpoint_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="summary_refresh",
            manual_hold_status="hold_released",
            manual_hold_scope="project_scoped",
            executive_approval_status="approved",
            hold_reason="Executive cleared release.",
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert blocked["status"] == "hold_release_pending"
    assert blocked["manual_hold_active"] is True
    assert "executive_approval_present" in blocked["hold_release_requirements"]
    assert released["status"] == "hold_released"
    assert released["manual_hold_active"] is False


def test_high_blast_radius_rollback_requires_executive_checkpoint():
    from NEXUS.governance_layer import evaluate_self_change_executive_checkpoint_outcome_safe

    result = evaluate_self_change_executive_checkpoint_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py", "C:/FORGE/README.md"],
            change_type="summary_refresh",
            tests_status="failed",
            rollback_scope="project_only",
            blast_radius_level="high",
            rollback_status="rollback_failed",
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["checkpoint_required"] is True
    assert result["checkpoint_scope"] == "rollback_scoped"


def test_audit_trail_persists_checkpoint_and_hold_outcomes():
    from NEXUS.execution_package_registry import append_self_change_audit_record_safe, list_self_change_audit_entries

    with _local_test_dir() as tmp:
        write_result = append_self_change_audit_record_safe(
            project_path=str(tmp),
            contract=_contract(
                target_files=["C:/FORGE/NEXUS/governance_layer.py"],
                change_type="governance_update",
                manual_hold_status="hold_active",
                manual_hold_scope="protected_core_only",
                hold_reason="Executive protected-core hold.",
            ),
            outcome_status="completed",
            approval_status="approved",
            validation_status="passed",
            build_status="passed",
            regression_status="passed",
            stable_state_ref="stable-phase73",
            release_lane="stable",
        )
        rows = list_self_change_audit_entries(str(tmp), n=10)

    assert write_result["status"] == "ok"
    assert rows
    assert rows[0]["checkpoint_required"] is True
    assert rows[0]["manual_hold_active"] is True
    assert rows[0]["manual_hold_scope"] == "protected_core_only"
    assert rows[0]["hold_reason"]
    assert rows[0]["override_status"]


def test_dashboard_summary_surfaces_checkpoint_and_hold_state():
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    sample_entry = {
        "change_id": "chg-phase74-dashboard",
        "recorded_at": "2026-03-23T12:00:00+00:00",
        "target_files": ["C:/FORGE/NEXUS/governance_layer.py"],
        "change_type": "governance_update",
        "risk_level": "high_risk",
        "protected_zones": ["governance_layer"],
        "protected_zone_hit": True,
        "reason": "Checkpoint and hold required for protected-core change.",
        "expected_outcome": "Executive gate is explicit and auditable.",
        "validation_plan": {"summary": "Run full checks.", "checks": ["tests", "build", "regressions"]},
        "rollback_plan": {"summary": "Rollback if needed."},
        "approval_requirement": "mandatory",
        "approval_required": True,
        "approval_status": "approved",
        "approved_by": "operator_alex",
        "outcome_status": "completed",
        "outcome_summary": "Checkpoint policy recorded.",
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
        "baseline_reference": "stable-phase73",
        "candidate_reference": "chg-phase74-dashboard",
        "comparison_dimensions": ["tests", "build", "regressions"],
        "observed_improvement": {},
        "observed_regression": {},
        "net_score": 0.0,
        "confidence_level": 0.8,
        "confidence_band": "strong",
        "comparison_status": "scored",
        "promotion_confidence": "keep_experimental",
        "recommendation": "hold_experimental",
        "comparison_reason": "Executive checkpoint still required.",
        "promoted_at": "2026-03-23T00:00:00+00:00",
        "monitoring_window": "observation_window",
        "monitoring_status": "monitoring_passed",
        "observation_count": 3,
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
        "checkpoint_status": "checkpoint_required",
        "executive_approval_required": True,
        "manual_hold_active": True,
        "manual_hold_scope": "protected_core_only",
        "hold_reason": "Executive hold active pending final checkpoint.",
        "hold_release_requirements": ["executive_approval_present", "protected_zone_clearance"],
        "override_status": "manual_hold_enforced",
        "validation_reasons": ["Checkpoint policy recorded."],
        "stable_state_ref": "stable-phase73",
        "success": True,
        "authority_trace": {"actor": "nexus", "authority_status": "authorized"},
        "governance_trace": {"origin": "phase74_test"},
        "contract_status": "valid",
    }

    with patch("NEXUS.registry_dashboard.PROJECTS", {}), patch(
        "NEXUS.execution_package_registry.list_self_change_audit_entries",
        return_value=[sample_entry],
    ):
        summary = build_registry_dashboard_summary()

    governance_summary = summary["self_evolution_governance_summary"]
    assert governance_summary["checkpoint_required_count_total"]["required"] == 1
    assert governance_summary["checkpoint_scope_count_total"]["protected_core_only"] == 1
    assert governance_summary["checkpoint_status_count_total"]["checkpoint_required"] == 1
    assert governance_summary["executive_approval_required_count_total"]["required"] == 1
    assert governance_summary["manual_hold_active_count_total"]["active"] == 1
    assert governance_summary["manual_hold_scope_count_total"]["protected_core_only"] == 1
    assert governance_summary["override_status_count_total"]["manual_hold_enforced"] == 1


def main():
    tests = [
        test_protected_core_high_risk_change_requires_executive_checkpoint,
        test_manual_hold_becomes_active_and_blocks_sensitive_advancement,
        test_hold_scope_remains_bounded,
        test_hold_release_requires_explicit_conditions,
        test_high_blast_radius_rollback_requires_executive_checkpoint,
        test_audit_trail_persists_checkpoint_and_hold_outcomes,
        test_dashboard_summary_surfaces_checkpoint_and_hold_state,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
