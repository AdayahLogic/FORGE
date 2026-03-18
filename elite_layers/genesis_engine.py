from __future__ import annotations

from typing import Any

from PRISM.prism_engine import evaluate_prism_safe


def _clamp_0_100(n: float) -> int:
    if n < 0:
        return 0
    if n > 100:
        return 100
    return int(round(n))


def _safe_list(v: Any) -> list[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if v is None:
        return []
    if isinstance(v, str):
        # allow comma-separated inputs
        parts = [p.strip() for p in v.replace("\n", ",").split(",") if p.strip()]
        return parts
    return [str(v).strip()]


def _extract_project_inputs(project_state: dict[str, Any]) -> dict[str, Any]:
    """
    Extract Genesis/PRISM-friendly inputs from persisted project_state.
    Uses existing architect_plan keys that PRISM already consumes.
    """
    architect_plan = project_state.get("architect_plan")
    if not isinstance(architect_plan, dict):
        architect_plan = {}

    return {
        "objective": architect_plan.get("objective") or architect_plan.get("product_concept") or "",
        "problem_solved": architect_plan.get("problem_solved") or architect_plan.get("problem") or "",
        "target_audience": architect_plan.get("target_audience") or architect_plan.get("audience") or "",
        "comparable_products": _safe_list(
            architect_plan.get("comparable_products") or architect_plan.get("comparables") or []
        ),
        "launch_angle": architect_plan.get("launch_angle") or "",
        "monetization_model": architect_plan.get("monetization_model") or "",
        "feature_list": _safe_list(architect_plan.get("feature_list") or architect_plan.get("features") or []),
        "notes": project_state.get("notes") or architect_plan.get("notes") or "",
    }


def _derive_idea_variants(base: dict[str, Any], *, n_ideas: int) -> list[dict[str, Any]]:
    objective = str(base.get("objective") or "").strip()
    problem = str(base.get("problem_solved") or "").strip()
    audience = str(base.get("target_audience") or "").strip()
    comparable_products = _safe_list(base.get("comparable_products"))
    monetization = str(base.get("monetization_model") or "").strip()
    launch_angle_base = str(base.get("launch_angle") or "").strip()
    feature_list_base = _safe_list(base.get("feature_list"))
    notes = str(base.get("notes") or "").strip()

    if not feature_list_base:
        # Deterministic minimal features; avoids empty feature_list.
        feature_list_base = [
            "Guided workflow",
            "Clear inputs/outputs",
            "Progress visibility",
        ]

    if not launch_angle_base:
        launch_angle_base = "Reduce friction and time-to-value."

    variants: list[dict[str, Any]] = []

    for i in range(max(1, int(n_ideas) or 1)):
        launch_angle = launch_angle_base
        monetization_model = monetization or "subscription"
        features = list(feature_list_base)
        comparable_out = list(comparable_products)

        # Create small deterministic deltas across variants.
        if i % 4 == 0:
            # Clarity-first
            launch_angle = (
                launch_angle_base
                if "clear" in launch_angle_base.lower()
                else "Clear and specific value proposition (reduce confusion)."
            )
            features = features + ["Onboarding checklist", "Plain-language examples"]
        elif i % 4 == 1:
            # Audience-first
            if not audience:
                audience = "Busy teams that need fast, reliable outcomes"
            launch_angle = "Solve the pain quickly (urgent value delivery)."
            features = features + ["Role-based templates", "Fast setup wizard"]
        elif i % 4 == 2:
            # Monetization-first
            if not monetization_model:
                monetization_model = "subscription"
            launch_angle = "Lower risk with transparent pricing and quick ROI."
            features = features + ["Usage-based reporting", "Export/hand-off artifacts"]
        else:
            # Differentiation-first
            launch_angle = "Compete on better workflow quality and measurable results."
            features = features + ["Quality gates", "Feedback loops", "Integration hooks"]

        # Deduplicate features while preserving order.
        seen: set[str] = set()
        features_out: list[str] = []
        for f in features:
            s = str(f).strip()
            if s and s not in seen:
                seen.add(s)
                features_out.append(s)

        product_concept = objective or f"Genesis offer variant {i + 1}"
        if problem:
            product_concept = product_concept if objective else f"{problem} for {audience or 'your audience'}"

        notes_out = notes
        if notes_out:
            notes_out = f"{notes_out}".strip()

        # Comparable products can help PRISM scoring; keep it stable.
        if not comparable_out and base.get("comparable_products"):
            comparable_out = _safe_list(base.get("comparable_products"))

        variants.append(
            {
                "idea_id": f"genesis-{i + 1}",
                "product_concept": product_concept,
                "problem_solved": problem,
                "target_audience": audience,
                "comparable_products": comparable_out,
                "launch_angle": launch_angle,
                "monetization_model": monetization_model,
                "feature_list": features_out,
                "notes": notes_out,
            }
        )

    return variants


def genesis_generate(project_state: dict[str, Any], *, n_ideas: int = 4, project_name: str | None = None) -> dict[str, Any]:
    base = _extract_project_inputs(project_state)
    ideas = _derive_idea_variants(base, n_ideas=n_ideas)
    return {"genesis_status": "generated", "ideas": ideas, "ranking": []}


def genesis_refine(
    project_state: dict[str, Any],
    *,
    idea: dict[str, Any],
    project_name: str | None = None,
) -> dict[str, Any]:
    base = _extract_project_inputs(project_state)

    idea_in = dict(idea or {})
    idea_in.setdefault("idea_id", "genesis-refined")

    # Normalize required PRISM inputs.
    product_concept = str(idea_in.get("product_concept") or base.get("objective") or "").strip()
    problem_solved = str(idea_in.get("problem_solved") or base.get("problem_solved") or "").strip()
    target_audience = str(idea_in.get("target_audience") or base.get("target_audience") or "").strip()
    comparable_products = _safe_list(idea_in.get("comparable_products") or base.get("comparable_products"))
    launch_angle = str(idea_in.get("launch_angle") or base.get("launch_angle") or "").strip()
    monetization_model = str(idea_in.get("monetization_model") or base.get("monetization_model") or "subscription").strip()
    feature_list = _safe_list(idea_in.get("feature_list") or base.get("feature_list"))
    notes = str(idea_in.get("notes") or base.get("notes") or "").strip()

    prism_res = evaluate_prism_safe(
        project_name=project_name,
        product_concept=product_concept,
        problem_solved=problem_solved,
        target_audience=target_audience,
        comparable_products=comparable_products,
        launch_angle=launch_angle,
        monetization_model=monetization_model,
        feature_list=feature_list,
        notes=notes,
    )

    rec = str(prism_res.get("recommendation") or "hold").strip().lower()
    scores = prism_res.get("scores") or {}

    improved = False

    # Especially refine when PRISM recommends "hold".
    if rec in ("hold", "revise") or prism_res.get("prism_status") != "evaluated":
        # Fill missing fields (deterministic, conservative).
        if not target_audience:
            target_audience = "Busy teams that need fast, reliable outcomes"
            improved = True

        if not monetization_model:
            monetization_model = "subscription"
            improved = True

        if not feature_list:
            feature_list = _safe_list(base.get("feature_list"))
            if not feature_list:
                feature_list = ["Guided workflow", "Clear inputs/outputs"]
            improved = True

        # Improve launch angle based on where PRISM is weakest.
        clarity = int(scores.get("clarity") or 0)
        if clarity < 55:
            launch_angle = "Clear and specific value proposition (reduce confusion)."
            improved = True
        elif rec == "hold":
            launch_angle = prism_res.get("strongest_launch_angle") or "Reduce friction and time-to-value."
            improved = True

        # Tighten product concept/promise when missing.
        if not product_concept:
            product_concept = f"{problem_solved or base.get('objective') or 'A useful product'} for {target_audience}"
            improved = True

        # Add a short specificity note when friction suggests insufficient clarity.
        if improved:
            extra_note = "Refined to reduce messaging friction and improve audience clarity."
            notes = f"{(notes + ' | ') if notes else ''}{extra_note}".strip()

    refined_idea = {
        **idea_in,
        "product_concept": product_concept,
        "problem_solved": problem_solved,
        "target_audience": target_audience,
        "comparable_products": comparable_products,
        "launch_angle": launch_angle,
        "monetization_model": monetization_model,
        "feature_list": feature_list,
        "notes": notes,
    }

    return {"genesis_status": "refined" if improved else "refine_noop", "ideas": [refined_idea], "ranking": []}


def _extract_aegis_decision(project_state: dict[str, Any]) -> str | None:
    last_aegis = project_state.get("last_aegis_decision")
    if isinstance(last_aegis, dict):
        d = str(last_aegis.get("aegis_decision") or "").strip().lower()
        if d in ("allow", "deny", "approval_required", "error_fallback"):
            return d
    return None


def _apply_risk_adjustments(
    *,
    base_score: float,
    aegis_decision: str | None,
    veritas_status: str | None,
    sentinel_status: str | None,
    sentinel_risk_level: str | None,
    prism_recommendation: str | None,
) -> float:
    score = float(base_score)

    # PRISM guidance: if PRISM says hold, keep ranking conservative.
    if prism_recommendation == "hold":
        score -= 6
    elif prism_recommendation == "revise":
        score -= 3

    # AEGIS gating: evaluation-only ranking should still reflect hard stops.
    if aegis_decision in ("deny", "error_fallback"):
        score *= 0.05
    elif aegis_decision == "approval_required":
        score *= 0.25

    if veritas_status in ("error_fallback", "review_required"):
        score *= 0.6
    elif veritas_status == "warning":
        score *= 0.8

    if sentinel_status in ("error_fallback", "review_required"):
        score *= 0.5
    elif sentinel_status == "warning":
        score *= 0.75

    if sentinel_risk_level == "high":
        score *= 0.7
    elif sentinel_risk_level == "medium":
        score *= 0.9

    return score


def genesis_rank(
    project_state: dict[str, Any],
    *,
    ideas: list[dict[str, Any]],
    project_name: str | None = None,
) -> dict[str, Any]:
    from elite_layers.veritas_engine import build_veritas_engine_safe
    from elite_layers.sentinel_engine import build_sentinel_engine_safe

    # Signals (evaluation-only).
    aegis_decision = _extract_aegis_decision(project_state)
    states_by_project = {str(project_name or project_state.get("active_project") or "project"): project_state}

    prj_name = str(project_name or project_state.get("active_project") or "project")

    veritas_res = build_veritas_engine_safe(states_by_project=states_by_project, project_name=prj_name)
    sentinel_res = build_sentinel_engine_safe(states_by_project=states_by_project, project_name=prj_name, meta_engine_summary={})

    veritas_status = veritas_res.get("veritas_status")
    sentinel_status = sentinel_res.get("sentinel_status")
    sentinel_risk_level = sentinel_res.get("risk_level")

    ranked: list[dict[str, Any]] = []
    for idea in ideas:
        idea_in = dict(idea or {})
        idea_id = str(idea_in.get("idea_id") or "")
        idea_id = idea_id if idea_id else "genesis-unknown"

        prism_res = evaluate_prism_safe(
            project_name=prj_name,
            product_concept=idea_in.get("product_concept"),
            problem_solved=idea_in.get("problem_solved"),
            target_audience=idea_in.get("target_audience"),
            comparable_products=idea_in.get("comparable_products"),
            launch_angle=idea_in.get("launch_angle"),
            monetization_model=idea_in.get("monetization_model"),
            feature_list=idea_in.get("feature_list"),
            notes=idea_in.get("notes"),
        )

        scores = prism_res.get("scores") or {}
        success_estimate = float(scores.get("success_estimate") or 0)
        clarity = float(scores.get("clarity") or 0)
        novelty = float(scores.get("novelty") or 0)
        emotional_pull = float(scores.get("emotional_pull") or 0)
        curiosity = float(scores.get("curiosity") or 0)
        monetization_potential = float(scores.get("monetization_potential") or 0)

        # Lightweight scoring: use PRISM success estimate as the anchor.
        base_score = (
            success_estimate * 0.55
            + clarity * 0.12
            + novelty * 0.10
            + emotional_pull * 0.10
            + curiosity * 0.08
            + monetization_potential * 0.05
        )

        prism_recommendation = prism_res.get("recommendation")
        adjusted = _apply_risk_adjustments(
            base_score=base_score,
            aegis_decision=aegis_decision,
            veritas_status=veritas_status,
            sentinel_status=sentinel_status,
            sentinel_risk_level=str(sentinel_risk_level or ""),
            prism_recommendation=str(prism_recommendation or "").lower(),
        )
        total_score = _clamp_0_100(adjusted)

        ranked.append(
            {
                "idea_id": idea_id,
                "total_score": total_score,
                "prism_status": prism_res.get("prism_status"),
                "prism_recommendation": prism_res.get("recommendation"),
                "prism_scores": prism_res.get("scores") or {},
                "veritas_status": veritas_status,
                "sentinel_status": sentinel_status,
                "sentinel_risk_level": sentinel_risk_level,
            }
        )

    ranked_sorted = sorted(ranked, key=lambda x: int(x.get("total_score") or 0), reverse=True)

    # Genesis status reflects evaluation-only posture.
    if aegis_decision in ("deny", "error_fallback"):
        genesis_status = "blocked_by_aegis"
    elif veritas_status in ("error_fallback", "review_required") or sentinel_status in ("error_fallback", "review_required"):
        genesis_status = "needs_review"
    else:
        genesis_status = "ranked"

    return {"genesis_status": genesis_status, "ideas": ideas, "ranking": ranked_sorted}


def build_genesis_engine_safe(
    *,
    genesis_mode: str,
    project_state: dict[str, Any] | None = None,
    project_name: str | None = None,
    n_ideas: int = 4,
    idea: dict[str, Any] | None = None,
    ideas: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    GENESIS evaluation-only engine.

    Output shape:
      {
        "genesis_status": "...",
        "ideas": [...],
        "ranking": [...]
      }
    """
    try:
        st = project_state or {}
        mode = str(genesis_mode or "").strip().lower()

        if mode == "generate":
            return genesis_generate(st, n_ideas=n_ideas, project_name=project_name)
        if mode == "refine":
            refined = genesis_refine(st, idea=idea or {}, project_name=project_name)
            return refined
        if mode == "rank":
            ideas_in = ideas or []
            if not isinstance(ideas_in, list) or not ideas_in:
                # Rank without explicit ideas: generate candidates first.
                gen = genesis_generate(st, n_ideas=n_ideas, project_name=project_name)
                ideas_in = gen.get("ideas") or []
            return genesis_rank(st, ideas=ideas_in, project_name=project_name)

        return {"genesis_status": "error_fallback", "ideas": [], "ranking": []}
    except Exception:
        return {"genesis_status": "error_fallback", "ideas": [], "ranking": []}

