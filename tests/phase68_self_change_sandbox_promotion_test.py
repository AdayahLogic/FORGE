"""
Phase 68 self-change sandbox and promotion flow tests.

Run: python tests/phase68_self_change_sandbox_promotion_test.py
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
    path = base / f"phase68_{uuid.uuid4().hex[:8]}"
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
    stable_release_approved: bool = False,
    sandbox_status: str | None = None,
    sandbox_result: str | None = None,
    application_state: str = "proposed",
) -> dict:
    contract = {
        "change_id": "chg-phase68",
        "target_files": target_files,
        "change_type": change_type,
        "reason": "Phase 11 sandbox and promotion evaluation.",
        "expected_outcome": "Explicit sandbox and promotion decision.",
        "validation_plan": {
            "summary": "Run tests, verify build, and confirm no regressions.",
            "checks": ["tests", "build", "regressions"],
        },
        "rollback_plan": {
            "summary": "Revert to the last stable state if the change fails after application.",
            "last_stable_state_ref": "stable-phase67",
        },
        "authority_trace": {"actor": "nexus", "requested_action": "propose_self_change"},
        "governance_trace": {"origin": "phase68_test"},
        "approval_status": approval_status,
        "validation_outcome": validation_outcome,
        "tests_status": tests_status,
        "build_status": build_status,
        "regression_status": regression_status,
        "release_lane": release_lane,
        "stable_release_approved": stable_release_approved,
        "application_state": application_state,
    }
    if sandbox_status is not None:
        contract["sandbox_status"] = sandbox_status
    if sandbox_result is not None:
        contract["sandbox_result"] = sandbox_result
    return contract


def test_high_risk_change_requires_sandbox_before_promotion():
    from NEXUS.self_evolution_governance import evaluate_self_change_sandbox_promotion_safe

    result = evaluate_self_change_sandbox_promotion_safe(
        _contract(
            target_files=["C:/FORGE/NEXUS/project_autopilot.py"],
            change_type="autopilot_guardrail_update",
            approval_status="approved",
            release_lane="experimental",
        )
    )

    assert result["sandbox_required"] is True
    assert result["sandbox_result"] == "sandbox_pending"
    assert result["promotion_status"] == "promotion_pending"


def test_protected_zone_change_requires_sandbox_before_promotion():
    from NEXUS.governance_layer import evaluate_self_change_sandbox_promotion_outcome_safe

    result = evaluate_self_change_sandbox_promotion_outcome_safe(
        self_change_contract=_contract(
            target_files=["C:/FORGE/NEXUS/governance_layer.py"],
            change_type="governance_update",
            approval_status="approved",
            release_lane="experimental",
        ),
        actor="nexus",
    )

    assert result["protected_zone_hit"] is True
    assert result["sandbox_required"] is True
    assert result["promotion_status"] == "promotion_pending"


def test_low_risk_change_can_skip_sandbox_when_release_ready():
    from NEXUS.self_evolution_governance import evaluate_self_change_sandbox_promotion_safe

    result = evaluate_self_change_sandbox_promotion_safe(
        _contract(
            target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
            change_type="summary_refresh",
            release_lane="stable",
        )
    )

    assert result["sandbox_required"] is False
    assert result["sandbox_result"] == "sandbox_not_required"
    assert result["promotion_status"] == "promoted_to_stable"


def test_sandbox_passed_leads_to_promotion_ready_or_stable_when_requirements_met():
    from NEXUS.self_evolution_governance import evaluate_self_change_sandbox_promotion_safe

    ready = evaluate_self_change_sandbox_promotion_safe(
        _contract(
            target_files=["C:/FORGE/NEXUS/runtime_dispatcher.py"],
            change_type="routing_policy_update",
            approval_status="approved",
            release_lane="stable",
            sandbox_status="sandbox_passed",
            sandbox_result="sandbox_passed",
        )
    )
    stable = evaluate_self_change_sandbox_promotion_safe(
        _contract(
            target_files=["C:/FORGE/NEXUS/runtime_dispatcher.py"],
            change_type="routing_policy_update",
            approval_status="approved",
            release_lane="stable",
            stable_release_approved=True,
            sandbox_status="sandbox_passed",
            sandbox_result="sandbox_passed",
        )
    )

    assert ready["promotion_status"] == "promotion_ready"
    assert ready["release_lane"] == "experimental"
    assert stable["promotion_status"] == "promoted_to_stable"
    assert stable["release_lane"] == "stable"


def test_sandbox_failed_blocks_promotion_and_requires_rollback_after_attempt():
    from NEXUS.self_evolution_governance import evaluate_self_change_sandbox_promotion_safe

    result = evaluate_self_change_sandbox_promotion_safe(
        _contract(
            target_files=["C:/FORGE/NEXUS/runtime_dispatcher.py"],
            change_type="routing_policy_update",
            approval_status="approved",
            validation_outcome="failed",
            regression_status="failed",
            sandbox_status="sandbox_failed",
            sandbox_result="sandbox_failed",
            application_state="attempted",
        )
    )

    assert result["sandbox_result"] == "sandbox_failed"
    assert result["promotion_status"] == "promotion_blocked"
    assert result["rollback_required"] is True


def test_protected_zone_change_not_promoted_without_sandbox_success():
    from NEXUS.self_evolution_governance import evaluate_self_change_sandbox_promotion_safe

    result = evaluate_self_change_sandbox_promotion_safe(
        _contract(
            target_files=["C:/FORGE/NEXUS/governance_layer.py"],
            change_type="governance_update",
            approval_status="approved",
            release_lane="stable",
            stable_release_approved=True,
        )
    )

    assert result["sandbox_required"] is True
    assert result["sandbox_result"] == "sandbox_pending"
    assert result["promotion_status"] == "promotion_pending"


def test_audit_trail_persists_sandbox_and_promotion_outcomes():
    from NEXUS.execution_package_registry import append_self_change_audit_record_safe, list_self_change_audit_entries

    with _local_test_dir() as tmp:
        write_result = append_self_change_audit_record_safe(
            project_path=str(tmp),
            contract=_contract(
                target_files=["C:/FORGE/NEXUS/runtime_dispatcher.py"],
                change_type="routing_policy_update",
                approval_status="approved",
                release_lane="stable",
                stable_release_approved=True,
                sandbox_status="sandbox_passed",
                sandbox_result="sandbox_passed",
            ),
            outcome_status="completed",
            approval_status="approved",
            validation_status="passed",
            build_status="passed",
            regression_status="passed",
            stable_state_ref="stable-phase67",
            release_lane="stable",
        )
        rows = list_self_change_audit_entries(str(tmp), n=10)

    assert write_result["status"] == "ok"
    assert rows
    assert rows[0]["sandbox_required"] is True
    assert rows[0]["sandbox_result"] == "sandbox_passed"
    assert rows[0]["promotion_status"] == "promoted_to_stable"
    assert rows[0]["promotion_reason"]
    assert rows[0]["comparison_status"] == "insufficient_evidence"
    assert rows[0]["promotion_confidence"] == "insufficient_evidence"


def test_dashboard_summary_surfaces_sandbox_and_promotion_states():
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    sample_entry = {
        "change_id": "chg-phase68-dashboard",
        "recorded_at": "2026-03-23T00:00:00+00:00",
        "target_files": ["C:/FORGE/NEXUS/runtime_dispatcher.py"],
        "change_type": "routing_update",
        "risk_level": "high_risk",
        "protected_zones": ["runtime_dispatcher"],
        "protected_zone_hit": True,
        "reason": "Require sandbox-first proof.",
        "expected_outcome": "Remain experimental until promoted.",
        "validation_plan": {"summary": "Run full checks.", "checks": ["tests", "build", "regressions"]},
        "rollback_plan": {"summary": "Revert to stable."},
        "approval_requirement": "mandatory",
        "approval_required": True,
        "approval_status": "approved",
        "approved_by": "operator_alex",
        "outcome_status": "completed",
        "outcome_summary": "Sandbox passed.",
        "validation_status": "passed",
        "build_status": "passed",
        "regression_status": "passed",
        "gate_outcome": "release_ready",
        "release_lane": "experimental",
        "sandbox_required": True,
        "sandbox_status": "sandbox_passed",
        "sandbox_result": "sandbox_passed",
        "promotion_status": "kept_experimental",
        "promotion_reason": "Sandbox-passed risky self-change stays experimental until explicit stable promotion approval is present.",
        "baseline_reference": "stable-phase67",
        "candidate_reference": "chg-phase68-dashboard",
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
        "rollback_required": False,
        "validation_reasons": ["Self-change satisfied approval, validation, and rollback requirements."],
        "stable_state_ref": "stable-phase67",
        "success": True,
        "authority_trace": {"actor": "nexus"},
        "governance_trace": {"origin": "phase68_test"},
        "contract_status": "valid",
    }

    with patch("NEXUS.registry_dashboard.PROJECTS", {}), patch(
        "NEXUS.execution_package_registry.list_self_change_audit_entries",
        return_value=[sample_entry],
    ):
        summary = build_registry_dashboard_summary()

    governance_summary = summary["self_evolution_governance_summary"]
    assert governance_summary["sandbox_required_count_total"]["required"] == 1
    assert governance_summary["sandbox_status_count_total"]["sandbox_passed"] == 1
    assert governance_summary["sandbox_result_count_total"]["sandbox_passed"] == 1
    assert governance_summary["promotion_status_count_total"]["kept_experimental"] == 1
    assert governance_summary["comparison_status_count_total"]["keep_experimental"] == 1
    assert governance_summary["confidence_band_count_total"]["moderate"] == 1


def main():
    tests = [
        test_high_risk_change_requires_sandbox_before_promotion,
        test_protected_zone_change_requires_sandbox_before_promotion,
        test_low_risk_change_can_skip_sandbox_when_release_ready,
        test_sandbox_passed_leads_to_promotion_ready_or_stable_when_requirements_met,
        test_sandbox_failed_blocks_promotion_and_requires_rollback_after_attempt,
        test_protected_zone_change_not_promoted_without_sandbox_success,
        test_audit_trail_persists_sandbox_and_promotion_outcomes,
        test_dashboard_summary_surfaces_sandbox_and_promotion_states,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
