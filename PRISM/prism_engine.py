from __future__ import annotations

from typing import Any

from PRISM.prism_recommendation import build_prism_recommendation_safe
from PRISM.prism_scoring import (
    score_clarity,
    score_curiosity,
    score_emotional_pull,
    score_monetization,
    score_novelty,
    score_success_estimate,
    score_virality,
)


def _is_present(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, list):
        return len([x for x in v if str(x).strip()]) > 0
    return True


def _merge_prism_inputs(cli_inputs: dict[str, Any], state_inputs: dict[str, Any]) -> dict[str, Any]:
    """
    Merge PRISM inputs deterministically.

    Preference order:
    - CLI inputs win when present/non-empty.
    - Otherwise fall back to state inputs.
    """
    keys = (
        "product_concept",
        "problem_solved",
        "target_audience",
        "comparable_products",
        "launch_angle",
        "monetization_model",
        "feature_list",
        "notes",
    )
    out: dict[str, Any] = {}
    for k in keys:
        cli_v = cli_inputs.get(k)
        state_v = state_inputs.get(k)
        out[k] = cli_v if _is_present(cli_v) else state_v
    return out


def _normalize_comparable_products(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        out: list[str] = []
        for x in v:
            s = str(x).strip()
            if s:
                out.append(s)
        return out
    s = str(v).strip()
    if not s:
        return []
    # Common delimiters.
    parts = [p.strip() for p in s.replace("\n", ",").split(",") if p.strip()]
    return parts


def _split_segments(v: Any, limit: int = 1) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        parts = [str(x).strip() for x in v if str(x).strip()]
        return parts[:limit]
    s = str(v).strip()
    if not s:
        return []
    # Split by common delimiters.
    raw = s.replace(" and ", ",").replace(";", ",")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts[:limit]


def _normalize_prism_input_text(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def evaluate_prism(
    *,
    project_name: str | None = None,
    product_concept: str | None = None,
    problem_solved: str | None = None,
    target_audience: str | None = None,
    comparable_products: Any = None,
    launch_angle: str | None = None,
    monetization_model: str | None = None,
    feature_list: Any = None,
    screenshots_or_mockups: Any = None,
    notes: str | None = None,
    cli_inputs: dict[str, Any] | None = None,
    state_inputs: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Evaluate PRISM v1 deterministically and explainably (recommend/revise/hold).
    """
    project_name_norm = project_name.strip() if isinstance(project_name, str) and project_name.strip() else None
    # Merge CLI + state inputs (Phase 1.5).
    if cli_inputs is not None or state_inputs is not None:
        merged = _merge_prism_inputs(cli_inputs or {}, state_inputs or {})
    else:
        merged = {
            "product_concept": product_concept,
            "problem_solved": problem_solved,
            "target_audience": target_audience,
            "comparable_products": comparable_products,
            "launch_angle": launch_angle,
            "monetization_model": monetization_model,
            "feature_list": feature_list,
            "notes": notes,
        }

    # Normalize core inputs.
    product_concept_s = _normalize_prism_input_text(merged.get("product_concept"))
    problem_solved_s = _normalize_prism_input_text(merged.get("problem_solved"))
    target_audience_s = _normalize_prism_input_text(merged.get("target_audience"))
    launch_angle_s = _normalize_prism_input_text(merged.get("launch_angle"))
    monetization_model_s = _normalize_prism_input_text(merged.get("monetization_model"))
    notes_s = _normalize_prism_input_text(merged.get("notes"))

    comparable_products_list = _normalize_comparable_products(merged.get("comparable_products"))

    feature_list_out: list[str] = []
    merged_feature_list = merged.get("feature_list")
    if isinstance(merged_feature_list, list):
        feature_list_out = [str(x).strip() for x in merged_feature_list if str(x).strip()]
    elif merged_feature_list is not None:
        feature_list_out = _normalize_comparable_products(merged_feature_list)

    # Determine PRISM status.
    # PRISM v1.5: only insufficient_input when product_concept is missing.
    prism_status = "insufficient_input" if not product_concept_s else "evaluated"

    # Missing-input signals (exclude product_concept from hard gating).
    missing_fields: dict[str, bool] = {
        "problem_solved": not bool(problem_solved_s),
        "target_audience": not bool(target_audience_s),
        "launch_angle": not bool(launch_angle_s),
        "monetization_model": not bool(monetization_model_s),
    }

    def _clamp_0_100(n: float) -> int:
        if n < 0:
            return 0
        if n > 100:
            return 100
        return int(round(n))

    # Scoring (still computed even with insufficient inputs, but success estimate is penalized).
    novelty = score_novelty(product_concept=product_concept_s, comparable_products=comparable_products_list)
    clarity = score_clarity(
        product_concept=product_concept_s,
        problem_solved=problem_solved_s,
        target_audience=target_audience_s,
        feature_list=feature_list_out,
    )
    emotional_pull = score_emotional_pull(problem_solved=problem_solved_s, launch_angle=launch_angle_s, notes=notes_s)
    curiosity = score_curiosity(product_concept=product_concept_s, launch_angle=launch_angle_s, notes=notes_s)
    virality_potential = score_virality(clarity=clarity, curiosity=curiosity, target_audience=target_audience_s)
    monetization_potential = score_monetization(
        monetization_model=monetization_model_s,
        product_concept=product_concept_s,
        problem_solved=problem_solved_s,
    )

    # Phase 1.5 adjustment: penalize missing inputs slightly, rather than failing.
    if missing_fields.get("problem_solved"):
        clarity = _clamp_0_100(clarity - 6)
        emotional_pull = _clamp_0_100(emotional_pull - 6)
    if missing_fields.get("target_audience"):
        virality_potential = _clamp_0_100(virality_potential - 10)
    if missing_fields.get("launch_angle"):
        curiosity = _clamp_0_100(curiosity - 6)
        emotional_pull = _clamp_0_100(emotional_pull - 3)
    if missing_fields.get("monetization_model"):
        monetization_potential = _clamp_0_100(monetization_potential - 12)

    # Friction points (explainable).
    audience_friction_points: list[str] = []
    if missing_fields.get("target_audience"):
        audience_friction_points.append("Target audience not specified (uncertain who to market to).")
    if missing_fields.get("problem_solved"):
        audience_friction_points.append("Problem solved not specified (value proposition lacks specificity).")
    if clarity < 55:
        audience_friction_points.append("Clarity is below threshold; messaging may confuse people.")
    if missing_fields.get("monetization_model"):
        audience_friction_points.append("Monetization model missing; payers may not see value alignment.")
    if comparable_products_list:
        audience_friction_points.append("Market comparables provided; differentiation must be explicitly articulated.")

    # Derive strongest audience segment.
    strongest_audience_segment = None
    audience_segments = _split_segments(target_audience_s, limit=3)
    if audience_segments:
        strongest_audience_segment = audience_segments[0]

    # Derive strongest launch angle.
    strongest_launch_angle = None
    if launch_angle_s:
        strongest_launch_angle = launch_angle_s
    else:
        # Simple deterministic fallback.
        if problem_solved_s and emotional_pull >= 60:
            strongest_launch_angle = "Solve the pain quickly (urgent emotional pull)."
        elif clarity >= 65:
            strongest_launch_angle = "Clear and specific value proposition (reduce confusion)."
        else:
            strongest_launch_angle = "Make it understandable (reduce messaging friction)."

    # Success estimate.
    success_estimate = score_success_estimate(
        novelty=novelty,
        clarity=clarity,
        emotional_pull=emotional_pull,
        curiosity=curiosity,
        virality_potential=virality_potential,
        monetization_potential=monetization_potential,
        friction_points=audience_friction_points,
        prism_status=prism_status,
    )

    recommendation_build = build_prism_recommendation_safe(
        prism_status=prism_status,
        success_estimate=success_estimate,
        clarity=clarity,
        novelty=novelty,
        audience_friction_points=audience_friction_points,
    )
    recommendation = recommendation_build.get("recommendation") or "hold"
    recommendation_reason = recommendation_build.get("recommendation_reason") or ""

    return {
        "prism_status": prism_status,
        "project_name": project_name_norm,
        "scores": {
            "novelty": novelty,
            "clarity": clarity,
            "emotional_pull": emotional_pull,
            "curiosity": curiosity,
            "virality_potential": virality_potential,
            "monetization_potential": monetization_potential,
            "success_estimate": success_estimate,
        },
        "strongest_audience_segment": strongest_audience_segment,
        "strongest_launch_angle": strongest_launch_angle,
        "audience_friction_points": audience_friction_points,
        "recommendation": recommendation,
        "recommendation_reason": recommendation_reason,
    }


def evaluate_prism_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return evaluate_prism(**kwargs)
    except Exception:
        return {
            "prism_status": "error_fallback",
            "project_name": None,
            "scores": {
                "novelty": 0,
                "clarity": 0,
                "emotional_pull": 0,
                "curiosity": 0,
                "virality_potential": 0,
                "monetization_potential": 0,
                "success_estimate": 0,
            },
            "strongest_audience_segment": None,
            "strongest_launch_angle": None,
            "audience_friction_points": [],
            "recommendation": "hold",
            "recommendation_reason": "PRISM evaluation failed; defaulting to hold.",
        }

