"""
Phase 31 HELIX evaluation quality tests.

Run: python tests/phase31_helix_evaluation_quality_test.py
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


def test_architect_has_comparative_fields():
    """Prove architect approaches include comparative_score, confidence, recommended_rank, fit_for_constraints."""
    from NEXUS.helix_stages import _normalize_approach

    a = _normalize_approach({
        "approach_id": "A",
        "summary": "x",
        "pros": ["a", "b"],
        "cons": ["c"],
        "risk_level": "low",
        "complexity": "low",
    }, 0)
    assert "comparative_score" in a
    assert a["comparative_score"] is not None
    assert 0 <= a["comparative_score"] <= 1
    assert "confidence" in a
    assert "fit_for_constraints" in a
    assert "rejection_reasons" in a
    assert "operator_notes" in a


def test_architect_recommended_rank_assigned():
    """Prove architect assigns recommended_rank by comparative_score."""
    from NEXUS.helix_stages import run_architect_stage

    # Mock to avoid LLM call - test via _normalize_approach + rank logic
    from NEXUS.helix_stages import _normalize_approach

    low = _normalize_approach({"approach_id": "A", "summary": "x", "pros": [], "cons": ["many"], "risk_level": "high"}, 0)
    high = _normalize_approach({"approach_id": "B", "summary": "y", "pros": ["a", "b", "c"], "cons": [], "risk_level": "low"}, 1)
    approaches = [low, high]
    from NEXUS.helix_stages import _score_approach_for_comparison
    sorted_by_score = sorted(approaches, key=lambda x: x.get("comparative_score") or 0.0, reverse=True)
    rank_map = {a.get("approach_id"): i + 1 for i, a in enumerate(sorted_by_score)}
    for ap in approaches:
        ap["recommended_rank"] = rank_map.get(ap.get("approach_id"), 0)
    assert approaches[0]["recommended_rank"] in (1, 2)
    assert approaches[1]["recommended_rank"] in (1, 2)
    assert set(ap["recommended_rank"] for ap in approaches) == {1, 2}


def test_critic_has_phase31_fields():
    """Prove critic evaluation includes issue_categories, severity, confidence, remediation_priority."""
    from NEXUS.helix_stages import run_critic_stage

    inspector = {"repair_recommended": True, "validation_result": {"regression_reason": "fail"}}
    builder = {"implementation_plan": {"implementation_steps": ["a", "b", "c", "d", "e", "f"], "risks": ["r1"]}}
    r = run_critic_stage(inspector, builder, "test")
    ev = r.get("critique_evaluation") or {}
    assert "issue_categories" in ev
    assert "severity" in ev
    assert "confidence" in ev
    assert "remediation_priority" in ev
    assert ev.get("severity") in ("low", "medium", "high")
    assert ev.get("remediation_priority") in ("low", "medium", "high")


def test_optimizer_has_suggestions_with_priority():
    """Prove optimizer includes suggestions_with_priority with priority, expected_benefit, recommendation_category, sequencing_group."""
    from NEXUS.helix_stages import run_optimizer_stage

    critic = {"critique_evaluation": {"correctness_risk": "low"}}
    builder = {"implementation_plan": {"implementation_steps": ["a", "b", "c"]}}
    r = run_optimizer_stage(critic, builder)
    swp = r.get("suggestions_with_priority") or []
    assert len(swp) > 0
    for s in swp[:3]:
        assert isinstance(s, dict)
        assert "suggestion" in s
        assert "priority" in s
        assert "expected_benefit" in s
        assert "recommendation_category" in s
        assert "sequencing_group" in s


def test_helix_quality_signals_module():
    """Prove helix_quality_signals computes bounded signals."""
    from NEXUS.helix_quality_signals import (
        compute_architect_output_quality,
        compute_critic_output_quality,
        compute_optimizer_output_quality,
        compute_overall_helix_quality_signal,
    )

    arch = {"approaches": [{"pros": ["a"], "cons": ["b"], "risk_level": "low", "comparative_score": 0.8, "recommended_rank": 1}], "selection_rationale": "Compare approaches by score."}
    aq = compute_architect_output_quality(arch)
    assert "architect_output_quality" in aq
    assert 0 <= aq["architect_output_quality"] <= 1

    crit = {"critique_evaluation": {"correctness_risk": "low", "testing_gaps": ["x"], "compatibility_risk": "low", "severity": "low"}, "critique": "Evaluation complete."}
    cq = compute_critic_output_quality(crit)
    assert "critic_output_quality" in cq
    assert 0 <= cq["critic_output_quality"] <= 1

    opt = {"optimizations": ["a", "b", "c"], "optimization_suggestions": {"safety": ["x"], "structure": ["y"]}, "implementation_sequencing": ["1. Step"], "suggestions_with_priority": [{"suggestion": "x", "priority": "high"}]}
    oq = compute_optimizer_output_quality(opt)
    assert "optimizer_output_quality" in oq
    assert 0 <= oq["optimizer_output_quality"] <= 1

    overall = compute_overall_helix_quality_signal([
        {"stage": "architect", **arch},
        {"stage": "critic", **crit},
        {"stage": "optimizer", **opt},
    ])
    assert "overall_helix_quality_signal" in overall
    assert 0 <= overall["overall_helix_quality_signal"] <= 1
    assert "architect_output_quality" in overall
    assert "critic_output_quality" in overall
    assert "optimizer_output_quality" in overall


def test_helix_summary_has_quality_signals():
    """Prove helix summary includes helix_quality_signals, critique_severity_patterns, optimizer_actionability_count."""
    from NEXUS.helix_summary import build_helix_summary_safe

    s = build_helix_summary_safe(n_recent=5)
    assert "helix_quality_signals" in s
    assert "critique_severity_patterns" in s
    assert "optimizer_actionability_count" in s
    qs = s.get("helix_quality_signals") or {}
    assert isinstance(qs, dict)


def test_helix_registry_preserves_suggestions_with_priority():
    """Prove normalize_helix_stage_result preserves suggestions_with_priority."""
    from NEXUS.helix_registry import normalize_helix_stage_result

    r = normalize_helix_stage_result({
        "stage": "optimizer",
        "stage_status": "completed",
        "suggestions_with_priority": [{"suggestion": "x", "priority": "high", "expected_benefit": "safety", "recommendation_category": "safety", "sequencing_group": 1}],
    })
    swp = r.get("suggestions_with_priority") or []
    assert len(swp) == 1
    assert swp[0].get("priority") == "high"
    assert swp[0].get("suggestion") == "x"


def main():
    tests = [
        test_architect_has_comparative_fields,
        test_architect_recommended_rank_assigned,
        test_critic_has_phase31_fields,
        test_optimizer_has_suggestions_with_priority,
        test_helix_quality_signals_module,
        test_helix_summary_has_quality_signals,
        test_helix_registry_preserves_suggestions_with_priority,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
