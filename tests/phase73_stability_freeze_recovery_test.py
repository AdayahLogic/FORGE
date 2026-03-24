"""
Phase 73 stability freeze and recovery escalation policy tests.

Run: python tests/phase73_stability_freeze_recovery_test.py
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
    path = base / f"phase73_{uuid.uuid4().hex[:8]}"
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
    outcome_status: str = "completed",
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
        "outcome_status": outcome_status,
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
    change_id: str = "chg-phase73",
    target_files: list[str],
    change_type: str,
    approval_status: str = "approved",
    tests_status: str = "passed",
    build_status: str = "passed",
    regression_status: str = "passed",
    observation_count: int = 3,
    health_signals: dict | None = None,
) -> dict:
    return {
        "change_id": change_id,
        "target_files": target_files,
        "change_type": change_type,
        "reason": "Phase 16 governed stability posture evaluation.",
        "expected_outcome": "Forge derives freeze and recovery posture explicitly.",
        "validation_plan": {
            "summary": "Run tests, verify build, and confirm stability posture.",
            "checks": ["tests", "build", "regressions"],
        },
        "rollback_plan": {
            "summary": "Rollback to the last stable state if governance requires it.",
            "last_stable_state_ref": "stable-phase72",
        },
        "authority_trace": {"actor": "nexus", "requested_action": "propose_self_change", "authority_status": "authorized"},
        "governance_trace": {"origin": "phase73_test"},
        "approval_status": approval_status,
        "validation_outcome": "failed" if "failed" in {tests_status, build_status, regression_status} else "passed",
        "tests_status": tests_status,
        "build_status": build_status,
        "regression_status": regression_status,
        "release_lane": "stable",
        "stable_release_approved": True,
        "sandbox_status": "sandbox_passed",
        "sandbox_result": "sandbox_passed",
        "baseline_reference": "stable-phase72",
        "candidate_reference": f"{change_id}-candidate",
        "baseline_evidence": {"tests_status": "passed", "build_status": "passed", "regression_status": "passed"},
        "comparison_dimensions": ["tests", "build", "regressions"],
        "promoted_at": "2026-03-23T00:00:00+00:00",
        "monitoring_window": "observation_window",
        "observation_count": observation_count,
        "health_signals": health_signals or {},
        "budgeting_window": _window(),
    }


def test_stable_posture_under_normal_conditions():
    from NEXUS.governance_layer import evaluate_self_change_stability_posture_outcome_safe

    result = evaluate_self_change_stability_posture_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="summary_refresh",
        ),
        recent_audit_entries=[],
        actor="nexus",
    )

    assert result["status"] == "stable"
    assert result["freeze_required"] is False
    assert result["recovery_only_mode"] is False
    assert result["reentry_requirements"] == []


def test_repeated_turbulence_drives_unstable_posture():
    from NEXUS.governance_layer import evaluate_self_change_stability_posture_outcome_safe

    history = [
        _entry(record_id="prior-throttle", mutation_rate_status="cool_down", control_outcome="cool_down_required"),
        _entry(record_id="prior-failed", outcome_status="failed"),
    ]
    result = evaluate_self_change_stability_posture_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="routing_policy_update",
            tests_status="failed",
        ),
        recent_audit_entries=history,
        actor="nexus",
    )

    assert result["status"] == "unstable"
    assert result["turbulence_level"] in {"high", "severe"}
    assert result["escalation_required"] is True


def test_severe_protected_core_instability_forces_frozen_or_recovery_posture():
    from NEXUS.governance_layer import evaluate_self_change_stability_posture_outcome_safe

    history = [
        _entry(
            record_id="prior-protected",
            rollback_required=True,
            rollback_status="rollback_completed",
            rollback_trigger_outcome="rollback_required",
            monitoring_status="monitoring_failed",
            protected_zone_hit=True,
            protected_zone_instability=True,
            regression_detected=True,
        )
    ]
    result = evaluate_self_change_stability_posture_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/governance_layer.py"],
            change_type="governance_update",
            health_signals={"protected_zone_degraded": True},
        ),
        recent_audit_entries=history,
        actor="nexus",
    )

    assert result["freeze_required"] is True
    assert result["protected_zone_instability"] is True
    assert result["freeze_scope"] in {"protected_core_only", "self_change_global", "recovery_scoped"}
    assert result["status"] in {"frozen", "recovery_only"}


def test_recovery_only_mode_blocks_ordinary_self_change_activity():
    from NEXUS.governance_layer import evaluate_self_change_stability_posture_outcome_safe

    result = evaluate_self_change_stability_posture_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/governance_layer.py"],
            change_type="governance_update",
            health_signals={"protected_zone_degraded": True},
        ),
        recent_audit_entries=[
            _entry(
                record_id="prior-protected",
                rollback_required=True,
                rollback_status="rollback_failed",
                rollback_trigger_outcome="rollback_required",
                monitoring_status="monitoring_failed",
                protected_zone_hit=True,
                protected_zone_instability=True,
                regression_detected=True,
            )
        ],
        actor="nexus",
    )

    assert result["status"] == "recovery_only"
    assert result["recovery_only_mode"] is True
    assert result["freeze_scope"] == "recovery_scoped"
    assert "explicit_approval_present" in result["reentry_requirements"]


def test_reentry_requirements_are_set_after_freeze():
    from NEXUS.governance_layer import evaluate_self_change_stability_posture_outcome_safe

    history = [
        _entry(record_id="prior-1", rollback_required=True, rollback_status="rollback_completed", rollback_trigger_outcome="rollback_required"),
        _entry(record_id="prior-2", mutation_rate_status="cool_down", control_outcome="cool_down_required"),
        _entry(record_id="prior-3", monitoring_status="monitoring_failed", regression_detected=True),
    ]
    result = evaluate_self_change_stability_posture_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="summary_refresh",
            tests_status="failed",
        ),
        recent_audit_entries=history,
        actor="nexus",
    )

    assert result["freeze_required"] is True
    assert "cooldown_satisfied" in result["reentry_requirements"]
    assert "turbulence_below_threshold" in result["reentry_requirements"]


def test_audit_trail_persists_stability_freeze_and_recovery_fields():
    from NEXUS.execution_package_registry import append_self_change_audit_record_safe, list_self_change_audit_entries

    with _local_test_dir() as tmp:
        write_result = append_self_change_audit_record_safe(
            project_path=str(tmp),
            contract=_contract(
                target_files=["C:/FORGE/NEXUS/governance_layer.py"],
                change_type="governance_update",
                health_signals={"protected_zone_degraded": True},
            ),
            outcome_status="completed",
            approval_status="approved",
            validation_status="passed",
            build_status="passed",
            regression_status="passed",
            stable_state_ref="stable-phase72",
            release_lane="stable",
        )
        rows = list_self_change_audit_entries(str(tmp), n=10)

    assert write_result["status"] == "ok"
    assert rows
    assert rows[0]["stability_state"] in {"frozen", "recovery_only"}
    assert rows[0]["freeze_required"] is True
    assert rows[0]["freeze_scope"]
    assert rows[0]["escalation_reason"]
    assert rows[0]["reentry_requirements"]


def test_dashboard_summary_surfaces_stability_freeze_and_recovery_state():
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    sample_entry = {
        "change_id": "chg-phase73-dashboard",
        "recorded_at": "2026-03-23T12:00:00+00:00",
        "target_files": ["C:/FORGE/NEXUS/governance_layer.py"],
        "change_type": "governance_update",
        "risk_level": "high_risk",
        "protected_zones": ["governance_layer"],
        "protected_zone_hit": True,
        "reason": "Escalate into governed recovery posture.",
        "expected_outcome": "Freeze and recovery state is explicit and visible.",
        "validation_plan": {"summary": "Run full checks.", "checks": ["tests", "build", "regressions"]},
        "rollback_plan": {"summary": "Rollback if required."},
        "approval_requirement": "mandatory",
        "approval_required": True,
        "approval_status": "approved",
        "approved_by": "operator_alex",
        "outcome_status": "completed",
        "outcome_summary": "Recovery posture recorded.",
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
        "baseline_reference": "stable-phase72",
        "candidate_reference": "chg-phase73-dashboard",
        "comparison_dimensions": ["tests", "build", "regressions"],
        "observed_improvement": {},
        "observed_regression": {"governance": {"baseline": "passed", "candidate": "failed", "delta": -1.0}},
        "net_score": -1.0,
        "confidence_level": 0.8,
        "confidence_band": "strong",
        "comparison_status": "regression_detected",
        "promotion_confidence": "regression_detected",
        "recommendation": "rollback",
        "comparison_reason": "Protected-core regression detected.",
        "promoted_at": "2026-03-23T00:00:00+00:00",
        "monitoring_window": "observation_window",
        "monitoring_status": "monitoring_failed",
        "observation_count": 2,
        "health_signals": {"protected_zone_degraded": True},
        "regression_detected": True,
        "rollback_triggered": True,
        "rollback_trigger_outcome": "rollback_required",
        "rollback_reason": "Protected core degraded.",
        "stable_status": "rollback_pending",
        "rollback_required": True,
        "rollback_id": "rollback-phase73-dashboard",
        "rollback_scope": "protected_core_limited",
        "rollback_target_files": ["C:/FORGE/NEXUS/governance_layer.py"],
        "rollback_target_components": ["governance_layer"],
        "blast_radius_level": "high",
        "rollback_status": "rollback_failed",
        "rollback_result": "Rollback failed; enter recovery posture.",
        "rollback_execution_eligible": False,
        "rollback_approval_required": True,
        "rollback_sequence": ["validate", "approve", "execute", "verify"],
        "rollback_follow_up_validation_required": True,
        "rollback_validation_status": "pending",
        "budgeting_window": _window(),
        "attempted_changes_in_window": 2,
        "successful_changes_in_window": 0,
        "failed_changes_in_window": 2,
        "rollbacks_in_window": 2,
        "protected_zone_changes_in_window": 2,
        "mutation_rate_status": "cool_down",
        "budget_remaining": 0,
        "cool_down_required": True,
        "control_outcome": "cool_down_required",
        "budget_reason": "Recent failures require a cool-down.",
        "stability_state": "recovery_only",
        "turbulence_level": "severe",
        "protected_zone_instability": True,
        "freeze_required": True,
        "freeze_scope": "recovery_scoped",
        "recovery_only_mode": True,
        "escalation_required": True,
        "escalation_reason": "Recovery-only posture is required before ordinary self-improvement can resume.",
        "reentry_requirements": [
            "cooldown_satisfied",
            "recovery_validation_passed",
            "protected_zone_posture_cleared",
            "explicit_approval_present",
            "turbulence_below_threshold",
        ],
        "validation_reasons": ["Recovery posture recorded."],
        "stable_state_ref": "stable-phase72",
        "success": True,
        "authority_trace": {"actor": "nexus", "authority_status": "authorized"},
        "governance_trace": {"origin": "phase73_test"},
        "contract_status": "valid",
    }

    with patch("NEXUS.registry_dashboard.PROJECTS", {}), patch(
        "NEXUS.execution_package_registry.list_self_change_audit_entries",
        return_value=[sample_entry],
    ):
        summary = build_registry_dashboard_summary()

    governance_summary = summary["self_evolution_governance_summary"]
    assert governance_summary["stability_state_count_total"]["recovery_only"] == 1
    assert governance_summary["turbulence_level_count_total"]["severe"] == 1
    assert governance_summary["freeze_required_count_total"] == 1
    assert governance_summary["freeze_scope_count_total"]["recovery_scoped"] == 1
    assert governance_summary["recovery_only_mode_count_total"]["enabled"] == 1
    assert governance_summary["escalation_required_count_total"]["required"] == 1


def main():
    tests = [
        test_stable_posture_under_normal_conditions,
        test_repeated_turbulence_drives_unstable_posture,
        test_severe_protected_core_instability_forces_frozen_or_recovery_posture,
        test_recovery_only_mode_blocks_ordinary_self_change_activity,
        test_reentry_requirements_are_set_after_freeze,
        test_audit_trail_persists_stability_freeze_and_recovery_fields,
        test_dashboard_summary_surfaces_stability_freeze_and_recovery_state,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
