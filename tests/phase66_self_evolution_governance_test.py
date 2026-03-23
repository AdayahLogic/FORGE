"""
Phase 66 self-evolution governance foundations tests.

Run: python tests/phase66_self_evolution_governance_test.py
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
    path = base / f"phase66_{uuid.uuid4().hex[:8]}"
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


def _valid_contract(*, target_files: list[str], change_type: str) -> dict:
    return {
        "change_id": "chg-phase66",
        "target_files": target_files,
        "change_type": change_type,
        "reason": "Introduce governed self-change safety controls.",
        "expected_outcome": "All self-modifications are classified and audited.",
        "validation_plan": {
            "summary": "Run tests, verify build, and confirm no regressions.",
            "checks": ["tests", "build", "regressions"],
        },
        "rollback_plan": {
            "summary": "Revert to the last stable state if validation fails.",
            "last_stable_state_ref": "stable-phase65",
        },
        "authority_trace": {
            "actor": "nexus",
            "requested_action": "propose_self_change",
        },
        "governance_trace": {
            "origin": "phase66_test",
        },
    }


def test_self_change_classification_covers_low_medium_high_risk():
    from NEXUS.self_evolution_governance import classify_self_change

    low = classify_self_change(
        target_files=["C:/FORGE/NEXUS/registry_dashboard.py"],
        change_type="summary_refresh",
    )
    medium = classify_self_change(
        target_files=["C:/FORGE/NEXUS/helper_adapter.py"],
        change_type="adapter_refactor",
    )
    high = classify_self_change(
        target_files=["C:/FORGE/NEXUS/runtime_dispatcher.py"],
        change_type="routing_policy_update",
    )

    assert low["risk_level"] == "low_risk"
    assert low["approval_requirement"] == "optional"
    assert medium["risk_level"] == "medium_risk"
    assert medium["approval_requirement"] == "recommended"
    assert high["risk_level"] == "high_risk"
    assert high["approval_requirement"] == "mandatory"


def test_protected_core_zone_requires_explicit_approval():
    from NEXUS.governance_layer import evaluate_self_change_governance_outcome_safe

    result = evaluate_self_change_governance_outcome_safe(
        self_change_contract=_valid_contract(
            target_files=["C:/FORGE/NEXUS/authority_model.py"],
            change_type="governance_hardening",
        ),
        actor="nexus",
    )

    assert result["governance_status"] == "approval_required"
    assert result["approval_required"] is True
    assert "authority_model" in result["protected_zones"]


def test_invalid_contract_is_blocked_when_validation_or_rollback_missing():
    from NEXUS.self_evolution_governance import validate_self_change_contract, evaluate_self_change_governance_safe

    contract = _valid_contract(
        target_files=["C:/FORGE/NEXUS/execution_package_registry.py"],
        change_type="execution_policy_adjustment",
    )
    contract["validation_plan"] = {"summary": "Only run tests.", "checks": ["tests"]}
    contract["rollback_plan"] = {}

    validation = validate_self_change_contract(contract)
    governance = evaluate_self_change_governance_safe(contract)

    assert validation["contract_status"] == "invalid"
    assert "build" in validation["missing_validation_checks"]
    assert "regressions" in validation["missing_validation_checks"]
    assert governance["governance_status"] == "blocked"


def test_authority_model_allows_governed_self_change_proposal():
    from NEXUS.authority_model import enforce_component_authority_safe

    result = enforce_component_authority_safe(
        component_name="nexus",
        actor="nexus",
        requested_actions=["propose_self_change", "record_self_change_audit"],
        allowed_components=["nexus"],
    )

    assert result["status"] == "authorized"
    assert result["authority_trace"]["authority_status"] == "authorized"


def test_self_change_audit_records_persist_with_outcome_and_approval():
    from NEXUS.execution_package_registry import append_self_change_audit_record_safe, list_self_change_audit_entries

    with _local_test_dir() as tmp:
        result = append_self_change_audit_record_safe(
            project_path=str(tmp),
            contract=_valid_contract(
                target_files=["C:/FORGE/NEXUS/project_autopilot.py"],
                change_type="autopilot_guardrail_update",
            ),
            outcome_status="failed",
            approved_by="operator_alex",
            approval_status="approved",
            outcome_summary="Validation failed and rollback path remained available.",
            validation_status="failed",
            build_status="passed",
            regression_status="failed",
            stable_state_ref="phase65-stable",
        )
        rows = list_self_change_audit_entries(str(tmp), n=10)

    assert result["status"] == "ok"
    assert rows
    assert rows[0]["approval_status"] == "approved"
    assert rows[0]["approved_by"] == "operator_alex"
    assert rows[0]["outcome_status"] == "failed"
    assert rows[0]["stable_state_ref"] == "phase65-stable"
    assert rows[0]["risk_level"] == "high_risk"
    assert rows[0]["gate_outcome"] == "rollback_required"
    assert rows[0]["rollback_required"] is True


def test_registry_dashboard_surfaces_self_evolution_governance_summary():
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    sample_entry = {
        "change_id": "chg-phase66-dashboard",
        "recorded_at": "2026-03-23T00:00:00+00:00",
        "target_files": ["C:/FORGE/NEXUS/governance_layer.py"],
        "change_type": "governance_update",
        "risk_level": "high_risk",
        "protected_zones": ["governance_layer"],
        "reason": "Protect governance surfaces.",
        "expected_outcome": "Approval-gated self-change.",
        "validation_plan": {"summary": "Run full checks.", "checks": ["tests", "build", "regressions"]},
        "rollback_plan": {"summary": "Revert to stable.", "last_stable_state_ref": "phase65-stable"},
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
        "rollback_required": False,
        "validation_reasons": ["Protected-zone self-change requires mandatory approval before advancing."],
        "stable_state_ref": "phase65-stable",
        "success": False,
        "authority_trace": {"actor": "nexus"},
        "governance_trace": {"origin": "phase66_test"},
        "contract_status": "valid",
    }

    with patch("NEXUS.registry_dashboard.PROJECTS", {}), patch(
        "NEXUS.execution_package_registry.list_self_change_audit_entries",
        return_value=[sample_entry],
    ):
        summary = build_registry_dashboard_summary()

    governance_summary = summary["self_evolution_governance_summary"]
    assert governance_summary["recent_count"] == 1
    assert governance_summary["risk_count_total"]["high_risk"] == 1
    assert governance_summary["approval_requirement_count_total"]["mandatory"] == 1
    assert governance_summary["gate_outcome_count_total"]["blocked_missing_approval"] == 1
    assert governance_summary["release_lane_count_total"]["experimental"] == 1
    assert governance_summary["protected_zone_hits"]["governance_layer"] == 1


def main():
    tests = [
        test_self_change_classification_covers_low_medium_high_risk,
        test_protected_core_zone_requires_explicit_approval,
        test_invalid_contract_is_blocked_when_validation_or_rollback_missing,
        test_authority_model_allows_governed_self_change_proposal,
        test_self_change_audit_records_persist_with_outcome_and_approval,
        test_registry_dashboard_surfaces_self_evolution_governance_summary,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
