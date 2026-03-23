"""
Phase 55 governance and contract continuation tests.

Run: python tests/phase55_governance_contracts_test.py
"""

from __future__ import annotations

import shutil
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@contextmanager
def _local_test_dir():
    base = ROOT / ".tmp_test_runs"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"phase55_{uuid.uuid4().hex[:8]}"
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


def test_authority_model_blocks_role_overreach():
    from NEXUS.authority_model import evaluate_component_authority_safe

    trace = evaluate_component_authority_safe(
        component_name="helix",
        requested_actions=["generate_plan", "execute_package"],
    )
    assert trace["authority_status"] == "blocked"
    assert trace["violation_detected"] is True
    assert "execute_package" in trace["denied_actions"]


def test_helix_contract_builds_and_packages_review_output():
    from unittest.mock import patch

    from NEXUS.helix_pipeline import run_helix_pipeline
    from NEXUS.helix_registry import read_helix_journal_tail
    from NEXUS.execution_package_registry import read_execution_package

    with _local_test_dir() as tmp:
        state_dir = tmp / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        loaded = {
            "load_error": None,
            "run_id": "run-phase55",
            "active_project": "phase55proj",
            "governance_status": "approved",
            "enforcement_status": "continue",
            "recovery_status": "waiting",
            "autonomy_mode": "supervised_build",
            "review_queue_entry": {},
            "recovery_result": {},
            "reexecution_result": {},
            "enforcement_result": {"enforcement_status": "continue"},
        }
        context = {"memory_status": "ok", "current_focus": "Ship governed HELIX output.", "next_steps": ["review package"]}
        with patch("NEXUS.helix_pipeline.load_project_state", return_value=loaded), patch("NEXUS.helix_pipeline.load_project_context", return_value=context):
            result = run_helix_pipeline(project_path=str(tmp), project_name="phase55proj", requested_outcome="Add a bounded safe patch.")
        assert result["helix_contract"]["contract_version"] == "1.0"
        assert result["authority_trace"]["component_role"] == "generation_only"
        assert result["helix_contract"]["package_enforcement"]["required"] is True
        assert result["contract_validation"]["contract_status"] == "valid"
        assert result["contract_validation"]["validation_path"] == "package_binding_allowed"
        assert result["execution_package_refs"]
        package = read_execution_package(str(tmp), result["execution_package_refs"][0])
        assert package is not None
        assert package["helix_contract_summary"]["contract_status"] == "valid"
        assert package["helix_contract_summary"]["component_role"] == "generation_only"
        record = read_helix_journal_tail(str(tmp), n=1)[-1]
        assert record["helix_contract"]["package_enforcement"]["package_status"] == "packaged"
        assert record["contract_validation"]["package_binding_status"] == "validated_for_review_package"


def test_helix_contract_validation_blocks_invalid_output():
    from NEXUS.helix_contracts import validate_helix_contract_envelope

    result = validate_helix_contract_envelope(
        {
            "contract_version": "1.0",
            "input_schema_version": "1.0",
            "output_schema_version": "1.0",
            "input_contract": {
                "project_name": "phase55proj",
                "run_id": "run-1",
                "task": "Ship contract validation",
                "project_state": {},
                "loaded_context": {},
                "prior_evaluations": [],
            },
            "output_contract": {
                "task_summary": "Ship contract validation",
                "plans": {"implementation_steps": []},
                "code_generation": {"patch_request_present": False, "target_files": []},
                "validation": {},
                "pipeline_status": "completed",
                "stop_reason": "completed",
                "requires_surgeon": False,
            },
            "package_enforcement": {
                "required": True,
                "binding_path": "review_sealed_package_flow",
            },
            "authority_trace": {
                "component_name": "helix",
                "authority_status": "authorized",
            },
            "trace_metadata": {
                "project_name": "phase55proj",
                "trace_id": "helix-123",
            },
        }
    )
    assert result["contract_status"] == "invalid"
    assert result["validation_path"] == "blocked_before_package_binding"
    assert result["package_binding_status"] == "validation_failed"
    assert "output_contract.risk_flags" in result["missing_fields"]


def test_recovery_engine_pauses_on_governance_enforcement_conflict():
    from NEXUS.recovery_engine import evaluate_recovery_outcome

    result = evaluate_recovery_outcome(
        governance_status="approval_required",
        enforcement_status="continue",
        retry_count=0,
    )
    assert result["recovery_action"] == "pause_system"
    assert result["system_pause_required"] is True
    assert result["conflict_escalation_status"] == "system_pause_required"


def test_meta_engine_governance_uses_required_priority_order():
    from NEXUS.meta_engine_governance import resolve_meta_engine_governance

    result = resolve_meta_engine_governance(
        titan_summary={"review_required": True, "titan_status": "review_required"},
        helios_summary={"review_required": True, "helios_status": "gated"},
        veritas_summary={"review_required": True, "veritas_status": "review_required"},
        sentinel_summary={"review_required": True, "sentinel_status": "review_required"},
    )
    assert result["priority_order"] == ["SENTINEL", "VERITAS", "LEVIATHAN", "TITAN", "HELIOS"]
    assert result["governing_engine"] == "SENTINEL"


def test_memory_layer_records_reusable_patterns_without_self_modifying():
    from NEXUS.memory_layer import build_memory_layer_summary_safe, record_memory_pattern_safe

    before = build_memory_layer_summary_safe()
    record_memory_pattern_safe(
        project_name="phase55proj",
        source="abacus",
        pattern_key="evaluation:completed",
        attributes={"failure_risk_band": "low"},
    )
    after = build_memory_layer_summary_safe()
    assert after["self_modification_policy"] == "approval_required"
    assert after["total_records"] >= before["total_records"]
    assert after["patterns_by_key"].get("evaluation:completed", 0) >= 1


def test_cursor_runtime_exposes_phase16_bridge_scaffold_without_execution():
    from NEXUS.runtimes.cursor_runtime import dispatch

    result = dispatch({"ready_for_dispatch": True})
    assert result["cursor_bridge_summary"]["bridge_phase"] == "phase_16_scaffold"
    assert result["cursor_bridge_summary"]["execution_enabled"] is False
    assert result["authority_trace"]["component_name"] == "cursor_bridge"


def main():
    tests = [
        test_authority_model_blocks_role_overreach,
        test_helix_contract_builds_and_packages_review_output,
        test_helix_contract_validation_blocks_invalid_output,
        test_recovery_engine_pauses_on_governance_enforcement_conflict,
        test_meta_engine_governance_uses_required_priority_order,
        test_memory_layer_records_reusable_patterns_without_self_modifying,
        test_cursor_runtime_exposes_phase16_bridge_scaffold_without_execution,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
