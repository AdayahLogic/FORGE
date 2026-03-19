"""
Phase 22 HELIX upgrade tests.

Run: python tests/phase22_helix_upgrade_test.py
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


def test_helix_record_has_autonomy_id_refs():
    """Prove HELIX record includes autonomy_id_refs."""
    from NEXUS.helix_registry import normalize_helix_record

    r = normalize_helix_record({"autonomy_id_refs": ["a1", "a2"]})
    assert "autonomy_id_refs" in r
    assert r["autonomy_id_refs"] == ["a1", "a2"]


def test_architect_approach_has_pros_cons_risk_scalability():
    """Prove Architect approaches have pros, cons, risk_level, scalability."""
    from NEXUS.helix_stages import _normalize_approach

    a = _normalize_approach({
        "approach_id": "A",
        "summary": "Minimal",
        "pros": ["fast", "simple"],
        "cons": ["limited"],
        "risk_level": "low",
        "scalability": "single-node",
    }, 0)
    assert a["approach_id"] == "A"
    assert a["pros"] == ["fast", "simple"]
    assert a["cons"] == ["limited"]
    assert a["risk_level"] == "low"
    assert a["scalability"] == "single-node"


def test_critic_has_structured_evaluation():
    """Prove Critic produces critique_evaluation with correctness_risk, maintainability, etc."""
    from NEXUS.helix_stages import run_critic_stage

    r = run_critic_stage(
        inspector_result={"repair_recommended": False, "validation_result": {}},
        builder_result={"implementation_plan": {"implementation_steps": ["a", "b", "c"], "risks": []}},
        requested_outcome="test",
    )
    ev = r.get("critique_evaluation") or {}
    assert "correctness_risk" in ev
    assert "maintainability" in ev
    assert "scalability" in ev
    assert "hidden_failure_points" in ev


def test_optimizer_has_categorized_suggestions():
    """Prove Optimizer produces optimization_suggestions with performance, structure, safety, readability."""
    from NEXUS.helix_stages import run_optimizer_stage, run_critic_stage

    critic = run_critic_stage(
        {"repair_recommended": False, "validation_result": {}},
        {"implementation_plan": {"implementation_steps": ["a"]}},
        "test",
    )
    r = run_optimizer_stage(critic, {"implementation_plan": {"implementation_steps": ["a"]}})
    sug = r.get("optimization_suggestions") or {}
    assert "performance" in sug
    assert "structure" in sug
    assert "safety" in sug
    assert "readability" in sug


def test_helix_summary_has_stage_distribution_and_frequencies():
    """Prove helix_summary includes stage_distribution, surgeon_invocation_frequency, etc."""
    from NEXUS.helix_summary import build_helix_summary_safe, HELIX_SUMMARY_KEYS

    s = build_helix_summary_safe()
    for k in ("stage_distribution", "surgeon_invocation_frequency", "approval_blocked_frequency", "autonomy_linkage_presence"):
        assert k in s
    assert "stage_distribution" in s
    assert isinstance(s["stage_distribution"], dict)
    assert 0 <= s["surgeon_invocation_frequency"] <= 1


if __name__ == "__main__":
    ok = 0
    ok += _run("test_helix_record_has_autonomy_id_refs", test_helix_record_has_autonomy_id_refs)
    ok += _run("test_architect_approach_has_pros_cons_risk_scalability", test_architect_approach_has_pros_cons_risk_scalability)
    ok += _run("test_critic_has_structured_evaluation", test_critic_has_structured_evaluation)
    ok += _run("test_optimizer_has_categorized_suggestions", test_optimizer_has_categorized_suggestions)
    ok += _run("test_helix_summary_has_stage_distribution_and_frequencies", test_helix_summary_has_stage_distribution_and_frequencies)
    print(f"\n{ok}/5 passed")
    sys.exit(0 if ok == 5 else 1)
