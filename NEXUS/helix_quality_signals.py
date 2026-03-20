"""
NEXUS HELIX quality signals (Phase 31).

Deterministic, bounded quality summary layer for HELIX outputs.
Does NOT pretend to measure intelligence. Reflects completeness,
richness, and actionability of structured output.
"""

from __future__ import annotations

from typing import Any


def _score_risk(r: str) -> float:
    """Map risk_level to numeric score (higher = better)."""
    r = (r or "").strip().lower()
    if r == "low":
        return 0.9
    if r == "medium":
        return 0.6
    if r == "high":
        return 0.3
    return 0.5


def _score_complexity(c: str) -> float:
    """Map complexity to numeric score (higher = simpler)."""
    c = (c or "").strip().lower()
    if c == "low":
        return 0.9
    if c == "medium":
        return 0.6
    if c == "high":
        return 0.3
    return 0.5


def compute_architect_output_quality(stage_result: dict[str, Any]) -> dict[str, Any]:
    """
    Compute bounded architect output quality signal.
    Reflects: multi-approach richness, comparative structure, recommendation clarity.
    """
    r = stage_result or {}
    approaches = r.get("approaches") or []
    n = len(approaches)

    # Completeness: do we have 2+ approaches with structure?
    multi_approach_richness = min(1.0, n / 2.0) if n >= 2 else (0.5 if n == 1 else 0.0)

    # Structure: approaches with pros, cons, risk_level
    structured_count = 0
    for a in approaches:
        if isinstance(a, dict) and (a.get("pros") or a.get("cons")) and a.get("risk_level"):
            structured_count += 1
    structure_completeness = structured_count / n if n else 0.0

    # Comparative: do we have comparative_score or recommended_rank?
    has_comparative = any(
        isinstance(a, dict) and (a.get("comparative_score") is not None or a.get("recommended_rank") is not None)
        for a in approaches
    )
    comparative_signal = 1.0 if has_comparative and n >= 2 else (0.5 if n >= 2 else 0.0)

    # Selection rationale presence
    rationale = r.get("selection_rationale") or ""
    rationale_present = 1.0 if rationale and len(rationale) > 20 else 0.0

    # Bounded aggregate (0-1)
    raw = (multi_approach_richness * 0.3 + structure_completeness * 0.3 +
           comparative_signal * 0.2 + rationale_present * 0.2)
    architect_output_quality = round(min(1.0, max(0.0, raw)), 2)

    return {
        "architect_output_quality": architect_output_quality,
        "multi_approach_count": n,
        "multi_approach_richness": round(multi_approach_richness, 2),
        "structure_completeness": round(structure_completeness, 2),
        "comparative_signal": round(comparative_signal, 2),
    }


def compute_critic_output_quality(stage_result: dict[str, Any]) -> dict[str, Any]:
    """
    Compute bounded critic output quality signal.
    Reflects: correctness risk analysis, testing gaps, compatibility, severity structure.
    """
    r = stage_result or {}
    ev = r.get("critique_evaluation") or {}

    # Correctness risk present
    correctness = 1.0 if ev.get("correctness_risk") else 0.0

    # Testing gaps
    gaps = ev.get("testing_gaps") or []
    testing_coverage = 1.0 if isinstance(gaps, list) and len(gaps) > 0 else 0.5

    # Compatibility risk
    compat = 1.0 if ev.get("compatibility_risk") else 0.0

    # Severity / issue_categories (Phase 31)
    has_severity = ev.get("severity") is not None
    has_issue_categories = isinstance(ev.get("issue_categories"), list) and len(ev.get("issue_categories", [])) > 0
    severity_signal = 1.0 if (has_severity or has_issue_categories) else 0.5

    # Critique text presence
    critique = r.get("critique") or ""
    critique_present = 1.0 if critique and len(critique) > 30 else 0.5

    raw = (correctness * 0.2 + testing_coverage * 0.2 + compat * 0.2 +
           severity_signal * 0.2 + critique_present * 0.2)
    critic_output_quality = round(min(1.0, max(0.0, raw)), 2)

    return {
        "critic_output_quality": critic_output_quality,
        "correctness_risk_present": bool(correctness),
        "testing_gaps_count": len(gaps) if isinstance(gaps, list) else 0,
        "severity_structured": has_severity or has_issue_categories,
    }


def compute_optimizer_output_quality(stage_result: dict[str, Any]) -> dict[str, Any]:
    """
    Compute bounded optimizer output quality signal.
    Reflects: suggestion count, categorization, sequencing, actionability.
    """
    r = stage_result or {}
    sugg = r.get("optimization_suggestions") or {}
    optimizations = r.get("optimizations") or []
    sequencing = r.get("implementation_sequencing") or []

    n_sugg = len(optimizations)
    suggestion_richness = min(1.0, n_sugg / 5.0) if n_sugg else 0.0

    # Categorization
    cats = [k for k in ("performance", "structure", "safety", "readability", "implementation_sequencing")
            if sugg.get(k)]
    cat_count = len(cats)
    categorization = min(1.0, cat_count / 3.0)

    # Sequencing
    sequencing_present = 1.0 if sequencing and len(sequencing) > 0 else 0.0

    # Priority / expected_benefit (Phase 31)
    swp = r.get("suggestions_with_priority") or []
    has_priority = any(
        isinstance(s, dict) and s.get("priority") for s in swp
    ) if isinstance(swp, list) else False
    actionability_signal = 1.0 if has_priority or sequencing_present else 0.5

    raw = (suggestion_richness * 0.3 + categorization * 0.3 +
           sequencing_present * 0.2 + actionability_signal * 0.2)
    optimizer_output_quality = round(min(1.0, max(0.0, raw)), 2)

    return {
        "optimizer_output_quality": optimizer_output_quality,
        "suggestion_count": n_sugg,
        "category_count": cat_count,
        "sequencing_present": bool(sequencing_present),
    }


def compute_overall_helix_quality_signal(stage_results: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute overall HELIX quality signal from stage results.
    Bounded, explainable. Does NOT claim intelligence.
    """
    architect = next((sr for sr in (stage_results or []) if sr.get("stage") == "architect"), {})
    critic = next((sr for sr in (stage_results or []) if sr.get("stage") == "critic"), {})
    optimizer = next((sr for sr in (stage_results or []) if sr.get("stage") == "optimizer"), {})

    aq = compute_architect_output_quality(architect)
    cq = compute_critic_output_quality(critic)
    oq = compute_optimizer_output_quality(optimizer)

    a_val = aq.get("architect_output_quality", 0.0)
    c_val = cq.get("critic_output_quality", 0.0)
    o_val = oq.get("optimizer_output_quality", 0.0)

    # Weighted average; architect and critic matter more for trust
    raw = a_val * 0.35 + c_val * 0.35 + o_val * 0.30
    overall_helix_quality_signal = round(min(1.0, max(0.0, raw)), 2)

    return {
        "overall_helix_quality_signal": overall_helix_quality_signal,
        "architect_output_quality": a_val,
        "critic_output_quality": c_val,
        "optimizer_output_quality": o_val,
        "architect_details": aq,
        "critic_details": cq,
        "optimizer_details": oq,
    }
