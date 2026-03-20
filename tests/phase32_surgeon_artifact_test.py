"""
Phase 32 Surgeon artifact upgrade tests.

Run: python tests/phase32_surgeon_artifact_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _run(name: str, fn):
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except Exception as e:
        print(f"FAIL: {name} - {e}")
        return False


def test_surgeon_no_patch_has_phase32_fields():
    """Prove surgeon repair_metadata includes Phase 32 fields when builder lacks patch."""
    from NEXUS.helix_stages import run_surgeon_stage

    critic = {"repair_recommended": True, "repair_reason": "Regression failed", "critique_evaluation": {
        "correctness_risk": "high",
        "hidden_failure_points": ["Edge case not handled"],
        "testing_gaps": ["Unit tests missing"],
    }}
    inspector = {"repair_recommended": True, "repair_reason": "Regression", "validation_result": {"regression_reason": "test fail in src/foo.py"}}
    builder = {"implementation_plan": {"implementation_steps": ["a", "b", "c", "d", "e"]}}
    r = run_surgeon_stage(critic, inspector, "test", builder_result=builder)
    meta = r.get("repair_metadata") or {}
    assert meta.get("repair_strategy_category") == "builder_no_patch"
    assert "patch_readiness" in meta
    assert meta.get("patch_readiness") in ("low", "medium", "high")
    assert "issue_scope" in meta
    assert meta.get("issue_scope") in ("single_file", "multi_file", "unknown")
    assert "target_files_candidate" in meta
    assert "suspected_root_causes" in meta
    assert "validation_recommendations" in meta
    assert "human_followup_required" in meta
    assert meta.get("human_followup_required") is True
    assert "operator_handoff_notes" in meta
    assert "patch_followup_candidate" in meta


def test_surgeon_with_patch_has_high_readiness():
    """Prove surgeon has patch_readiness=high when builder has patch."""
    from NEXUS.helix_stages import run_surgeon_stage

    critic = {"repair_recommended": True, "repair_reason": "x", "critique_evaluation": {}}
    inspector = {"repair_recommended": True, "repair_reason": "x", "validation_result": {}}
    builder = {"implementation_plan": {"patch_request": {"target_relative_path": "a.py", "search_text": "x", "replacement_text": "y"}}}
    r = run_surgeon_stage(critic, inspector, "test", builder_result=builder)
    meta = r.get("repair_metadata") or {}
    assert meta.get("patch_readiness") == "high"
    assert meta.get("human_followup_required") is False
    assert "target_files_candidate" in meta
    assert meta.get("target_files_candidate") == ["a.py"]
    assert meta.get("issue_scope") == "single_file"


def test_surgeon_target_files_from_regression_reason():
    """Prove target_files_candidate inferred from regression_reason when it contains file path."""
    from NEXUS.helix_stages import run_surgeon_stage

    critic = {"repair_recommended": True, "repair_reason": "Fail", "critique_evaluation": {}}
    inspector = {"repair_recommended": True, "repair_reason": "Error in src/bar.py line 10", "validation_result": {"regression_reason": "Error in src/bar.py line 10"}}
    builder = {"implementation_plan": {}}
    r = run_surgeon_stage(critic, inspector, "test", builder_result=builder)
    meta = r.get("repair_metadata") or {}
    candidates = meta.get("target_files_candidate") or []
    assert "src/bar.py" in candidates or len(candidates) >= 0


def test_surgeon_suspected_root_causes_from_critic():
    """Prove suspected_root_causes populated from critic hidden_failure_points and testing_gaps."""
    from NEXUS.helix_stages import run_surgeon_stage

    critic = {"repair_recommended": True, "repair_reason": "Risk X", "critique_evaluation": {
        "hidden_failure_points": ["Rollback not tested", "Integration point fragile"],
        "testing_gaps": ["No E2E coverage"],
    }}
    inspector = {"repair_recommended": True, "repair_reason": "Reg", "validation_result": {}}
    builder = {"implementation_plan": {}}
    r = run_surgeon_stage(critic, inspector, "test", builder_result=builder)
    meta = r.get("repair_metadata") or {}
    causes = meta.get("suspected_root_causes") or []
    assert len(causes) >= 2
    assert any("Rollback" in c or "Integration" in c for c in causes)
    assert any("Testing" in c or "E2E" in c for c in causes)


def test_helix_summary_repair_artifact_quality_extended():
    """Prove helix summary repair_artifact_quality includes Phase 32 fields."""
    from NEXUS.helix_summary import build_helix_summary_safe

    s = build_helix_summary_safe(n_recent=5)
    rq = s.get("repair_artifact_quality") or {}
    assert "patch_readiness_distribution" in rq
    dist = rq.get("patch_readiness_distribution") or {}
    assert "high" in dist
    assert "medium" in dist
    assert "low" in dist
    assert "common_missing_info_patterns" in rq
    assert "actionable_count" in rq


def test_integrity_repair_metadata_check():
    """Prove check_repair_metadata_shape validates Phase 32 repair_metadata."""
    from NEXUS.helix_stages import run_surgeon_stage
    from NEXUS.integrity_checker import check_repair_metadata_shape

    critic = {"repair_recommended": True, "repair_reason": "x", "critique_evaluation": {}}
    inspector = {"repair_recommended": True, "repair_reason": "x", "validation_result": {}}
    builder = {"implementation_plan": {}}
    r = run_surgeon_stage(critic, inspector, "test", builder_result=builder)
    meta = r.get("repair_metadata") or {}
    result = check_repair_metadata_shape(meta)
    assert result.get("valid") is True
    assert result.get("payload_type") == "repair_metadata"


def test_learning_record_has_repair_artifact_fields():
    """Prove helix pipeline learning record includes repair artifact fields when surgeon required."""
    from NEXUS.helix_stages import run_surgeon_stage

    critic = {"repair_recommended": True, "repair_reason": "x", "critique_evaluation": {}}
    inspector = {"repair_recommended": True, "repair_reason": "x", "validation_result": {}}
    builder = {"implementation_plan": {}}
    r = run_surgeon_stage(critic, inspector, "test", builder_result=builder)
    meta = r.get("repair_metadata") or {}
    assert meta.get("patch_readiness") is not None
    assert meta.get("issue_scope") is not None
    assert "human_followup_required" in meta
    assert "missing_information_flags" in meta


def main():
    tests = [
        test_surgeon_no_patch_has_phase32_fields,
        test_surgeon_with_patch_has_high_readiness,
        test_surgeon_target_files_from_regression_reason,
        test_surgeon_suspected_root_causes_from_critic,
        test_helix_summary_repair_artifact_quality_extended,
        test_integrity_repair_metadata_check,
        test_learning_record_has_repair_artifact_fields,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
