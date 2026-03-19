from __future__ import annotations

from typing import Any, cast


def _safe_int(v: Any) -> int:
    try:
        return int(float(v))
    except Exception:
        return 0


def _safe_list(v: Any) -> list[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if v is None:
        return []
    if isinstance(v, str):
        return [p.strip() for p in v.replace("\n", ",").split(",") if p.strip()]
    return [str(v).strip()]


def _append_feature_list(feature_list: list[str], new_features: list[str]) -> list[str]:
    seen = set(feature_list)
    out = list(feature_list)
    for nf in new_features:
        s = str(nf).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def refine_idea_from_prism(
    *,
    idea: dict[str, Any],
    prism_result: dict[str, Any],
) -> dict[str, Any]:
    """
    Deterministic refinement based purely on PRISM score weak points.

    Behavior:
    - weak novelty => strengthen differentiation
    - weak curiosity => strengthen hook
    - weak virality => add shareability/community angle
    - weak monetization => strengthen payer/value model
    - weak clarity => simplify concept
    """
    out = dict(idea or {})
    scores = cast(dict[str, Any], prism_result.get("scores") or {})

    novelty = _safe_int(scores.get("novelty"))
    curiosity = _safe_int(scores.get("curiosity"))
    virality = _safe_int(scores.get("virality_potential"))
    monetization = _safe_int(scores.get("monetization_potential"))
    clarity = _safe_int(scores.get("clarity"))

    feature_list = _safe_list(out.get("feature_list"))
    notes = str(out.get("notes") or "").strip()
    product_concept = str(out.get("product_concept") or "").strip()
    launch_angle = str(out.get("launch_angle") or "").strip()
    problem_solved = str(out.get("problem_solved") or "").strip()
    target_audience = str(out.get("target_audience") or "").strip()
    monetization_model = str(out.get("monetization_model") or "").strip()

    # Thresholds: conservative; only apply targeted refinements on weak scores.
    weak_novelty = novelty < 45
    weak_curiosity = curiosity < 45
    weak_virality = virality < 45
    weak_monetization = monetization < 45
    weak_clarity = clarity < 45

    if weak_novelty:
        feature_list = _append_feature_list(feature_list, ["Differentiation points (why you vs alternatives)"])
        if product_concept:
            product_concept = f"{product_concept} + clear differentiators"

    if weak_curiosity:
        hook = "Hook: show instant progress and a clear next step in the first interaction."
        launch_angle = hook if not launch_angle else f"{launch_angle} ({hook})"
        notes = f"{notes} | {hook}".strip(" |")
        feature_list = _append_feature_list(feature_list, ["First-session win (instant progress)"])

    if weak_virality:
        feature_list = _append_feature_list(feature_list, ["Shareable output for community/social proof", "Referral-friendly handoffs"])
        community_note = "Add a community loop: share outcomes and invite feedback to accelerate iteration."
        notes = f"{notes} | {community_note}".strip(" |")

    if weak_monetization:
        value_note = "Payer value model: make ROI/impact explicit (what metrics improve and when)."
        notes = f"{notes} | {value_note}".strip(" |")
        if monetization_model:
            monetization_model = f"{monetization_model} (ROI-aligned pricing)"
        else:
            monetization_model = "subscription (ROI-aligned pricing)"
        feature_list = _append_feature_list(feature_list, ["ROI dashboard / value reporting"])

    if weak_clarity:
        # Simplify concept deterministically.
        if problem_solved or target_audience:
            product_concept = f"A simple solution to {problem_solved or 'solve the user need'} for {target_audience or 'the target audience'}."
        else:
            product_concept = product_concept or "A simple, clear solution."
        launch_angle = launch_angle or "Clear inputs, clear outputs, minimal time-to-value."
        notes = f"{notes} | Simplified for clarity.".strip(" |")
        feature_list = feature_list[: max(3, len(feature_list))]

    out["feature_list"] = feature_list
    out["notes"] = notes
    out["product_concept"] = product_concept
    out["launch_angle"] = launch_angle
    out["monetization_model"] = monetization_model

    return out


def refine_idea_from_prism_safe(
    *,
    idea: dict[str, Any],
    prism_result: dict[str, Any],
) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return refine_idea_from_prism(idea=idea, prism_result=prism_result)
    except Exception:
        return dict(idea or {})

