"""
Phase 30 HELIX deepening tests.

Run: python tests/phase30_helix_deepening_test.py
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


def test_architect_approach_has_extended_fields():
    """Prove architect approaches include complexity, implementation_cost, recommended_when."""
    from NEXUS.helix_stages import _normalize_approach

    a = _normalize_approach({"approach_id": "A", "summary": "x", "complexity": "low", "implementation_cost": "medium", "recommended_when": "default"}, 0)
    assert "complexity" in a
    assert "implementation_cost" in a
    assert "recommended_when" in a
    assert a["complexity"] == "low"


def test_critic_has_testing_gaps_compatibility():
    """Prove critic evaluation includes testing_gaps, compatibility_risk."""
    from NEXUS.helix_stages import run_critic_stage

    inspector = {"repair_recommended": False, "validation_result": {}}
    builder = {"implementation_plan": {"implementation_steps": ["a", "b", "c", "d", "e"], "risks": []}}
    r = run_critic_stage(inspector, builder, "test")
    ev = r.get("critique_evaluation") or {}
    assert "testing_gaps" in ev
    assert "compatibility_risk" in ev


def test_optimizer_has_implementation_sequencing():
    """Prove optimizer includes implementation_sequencing."""
    from NEXUS.helix_stages import run_optimizer_stage

    critic = {"critique_evaluation": {"correctness_risk": "low"}}
    builder = {"implementation_plan": {"implementation_steps": ["a", "b"]}}
    r = run_optimizer_stage(critic, builder)
    assert "implementation_sequencing" in r
    assert len(r.get("implementation_sequencing") or []) > 0
    sugg = r.get("optimization_suggestions") or {}
    assert "implementation_sequencing" in sugg


def test_surgeon_repair_metadata_when_no_patch():
    """Prove surgeon repair_metadata includes repair_strategy_category, missing_information_flags, recommended_next_actions when builder lacks patch."""
    from NEXUS.helix_stages import run_surgeon_stage

    critic = {"repair_recommended": True, "repair_reason": "Regression failed", "critique_evaluation": {"correctness_risk": "high"}}
    inspector = {"repair_recommended": True, "repair_reason": "Regression", "validation_result": {"regression_reason": "test fail"}}
    builder = {"implementation_plan": {}}
    r = run_surgeon_stage(critic, inspector, "test", builder_result=builder)
    meta = r.get("repair_metadata") or {}
    assert meta.get("repair_strategy_category") == "builder_no_patch"
    assert "missing_information_flags" in meta
    assert "recommended_next_actions" in meta
    assert len(meta.get("missing_information_flags") or []) > 0
    assert len(meta.get("recommended_next_actions") or []) > 0


def test_surgeon_repair_metadata_when_has_patch():
    """Prove surgeon repair_metadata when builder has patch."""
    from NEXUS.helix_stages import run_surgeon_stage

    critic = {"repair_recommended": True, "repair_reason": "x", "critique_evaluation": {}}
    inspector = {"repair_recommended": True, "repair_reason": "x", "validation_result": {}}
    builder = {"implementation_plan": {"patch_request": {"target_relative_path": "a.py", "search_text": "x", "replacement_text": "y"}}}
    r = run_surgeon_stage(critic, inspector, "test", builder_result=builder)
    meta = r.get("repair_metadata") or {}
    assert meta.get("repair_strategy_category") == "patch_available"
    assert meta.get("has_patch_payload") is True


def test_helix_summary_has_phase30_fields():
    """Prove helix summary includes multi_approach_success_rate, repair_artifact_quality."""
    from NEXUS.helix_summary import build_helix_summary_safe

    s = build_helix_summary_safe(n_recent=5)
    assert "multi_approach_success_rate" in s
    assert "repair_artifact_quality" in s
    rq = s.get("repair_artifact_quality") or {}
    assert "repair_with_patch_count" in rq
    assert "repair_without_patch_count" in rq
    assert "repair_total" in rq


def test_helix_registry_normalize_stage_result():
    """Prove normalize_helix_stage_result preserves selection_rationale, multi_approach_count, implementation_sequencing."""
    from NEXUS.helix_registry import normalize_helix_stage_result

    r = normalize_helix_stage_result({
        "stage": "architect",
        "selection_rationale": "Compare approaches",
        "multi_approach_count": 2,
        "implementation_sequencing": ["step 1", "step 2"],
    })
    assert r.get("selection_rationale") == "Compare approaches"
    assert r.get("multi_approach_count") == 2
    assert "implementation_sequencing" in r
    assert r.get("implementation_sequencing") == ["step 1", "step 2"]


def main():
    tests = [
        test_architect_approach_has_extended_fields,
        test_critic_has_testing_gaps_compatibility,
        test_optimizer_has_implementation_sequencing,
        test_surgeon_repair_metadata_when_no_patch,
        test_surgeon_repair_metadata_when_has_patch,
        test_helix_summary_has_phase30_fields,
        test_helix_registry_normalize_stage_result,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
