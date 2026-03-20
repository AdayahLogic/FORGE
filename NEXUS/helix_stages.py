"""
NEXUS HELIX stage logic (Phase 21).

Each stage produces structured output. No arbitrary code execution.
Uses existing PlannerEngine, regression_checks, model_router.
"""

from __future__ import annotations

from typing import Any

from NEXUS.helix_registry import normalize_helix_stage_result


def _score_approach_for_comparison(a: dict[str, Any]) -> float:
    """Phase 31: deterministic comparative score from risk_level, complexity, pros/cons."""
    risk = str(a.get("risk_level") or "medium").strip().lower()
    complexity = str(a.get("complexity") or "medium").strip().lower()
    pros = len(a.get("pros") or [])
    cons = len(a.get("cons") or [])
    risk_score = 0.9 if risk == "low" else (0.6 if risk == "medium" else 0.3)
    complexity_score = 0.9 if complexity == "low" else (0.6 if complexity == "medium" else 0.3)
    balance = 0.5 + 0.1 * (min(4, pros) - min(4, cons))
    return round(min(1.0, max(0.0, (risk_score * 0.4 + complexity_score * 0.4 + balance * 0.2))), 2)


def _normalize_approach(a: dict[str, Any], idx: int) -> dict[str, Any]:
    """Normalize approach to Phase 30/31 contract: approach_id, summary, pros, cons, risk_level, scalability, complexity, implementation_cost, recommended_when, comparative_score, confidence, recommended_rank, rejection_reasons, fit_for_constraints, operator_notes."""
    if not isinstance(a, dict):
        return {}
    aid = str(a.get("approach_id") or a.get("name") or chr(65 + idx))[:1]
    risk_level = str(a.get("risk_level") or "medium").strip().lower()[:20]
    pros = list(a.get("pros") or [])[:10]
    cons = list(a.get("cons") or [])[:10]
    complexity = str(a.get("complexity") or "")[:100]
    # Phase 31: derived comparative fields (deterministic, no fake intelligence)
    comparative_score = a.get("comparative_score")
    if comparative_score is None:
        comparative_score = _score_approach_for_comparison(a)
    confidence = str(a.get("confidence") or "medium").strip().lower()[:20]
    if confidence not in ("low", "medium", "high"):
        confidence = "medium"
    fit_for_constraints = a.get("fit_for_constraints")
    if fit_for_constraints is None:
        fit_for_constraints = risk_level != "high"
    rejection_reasons = list(a.get("rejection_reasons") or [])[:5]
    operator_notes = str(a.get("operator_notes") or "")[:300]
    return {
        "approach_id": aid,
        "summary": str(a.get("summary") or a.get("name") or "")[:500],
        "pros": pros,
        "cons": cons,
        "risk_level": risk_level,
        "scalability": str(a.get("scalability") or "")[:200],
        "complexity": complexity,
        "implementation_cost": str(a.get("implementation_cost") or "")[:100],
        "recommended_when": str(a.get("recommended_when") or "")[:200],
        "tradeoffs": a.get("tradeoffs") if isinstance(a.get("tradeoffs"), dict) else {},
        "comparative_score": comparative_score,
        "confidence": confidence,
        "fit_for_constraints": bool(fit_for_constraints),
        "rejection_reasons": rejection_reasons,
        "operator_notes": operator_notes,
    }


def run_architect_stage(
    requested_outcome: str,
    project_name: str,
    loaded_context: dict[str, Any],
) -> dict[str, Any]:
    """
    HELIX Architect: understand request, generate 2-3 approaches with structured tradeoffs.
    Each approach: approach_id, summary, pros, cons, risk_level, scalability.
    Uses PlannerEngine; produces real multi-approach outputs.
    """
    try:
        from NEXUS.llm import generate_architect_plan
        from NEXUS.model_router import route_generate

        plan = generate_architect_plan(
            user_input=requested_outcome,
            project_name=project_name,
            loaded_context=loaded_context,
        )
        objective = plan.get("objective") or requested_outcome
        impl_steps = plan.get("implementation_steps") or []
        risks = plan.get("risks") or []

        tradeoff_prompt = f"""
Given this implementation plan for project {project_name}:

Objective: {objective}
Steps: {impl_steps}
Risks: {risks}

Produce exactly 2-3 distinct implementation approaches as a JSON array.
Each approach MUST have:
- approach_id: "A" or "B" or "C"
- summary: brief description
- pros: array of 2-4 advantages
- cons: array of 2-4 disadvantages
- risk_level: "low" or "medium" or "high"
- scalability: brief note on scalability
- complexity: "low" or "medium" or "high" (optional)
- implementation_cost: "low" or "medium" or "high" (optional)
- recommended_when: when to prefer this approach (optional)

Return ONLY a JSON array, no markdown.
"""
        try:
            result = route_generate(prompt=tradeoff_prompt, provider=None, model="gpt-4o-mini")
            raw = (result.get("output_text") or "[]").strip()
            import json
            import re
            if "```" in raw:
                raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
                raw = re.sub(r"\s*```$", "", raw)
            start = raw.find("[")
            end = raw.rfind("]")
            if start != -1 and end != -1 and end > start:
                raw = raw[start : end + 1]
            raw_approaches = json.loads(raw) if isinstance(raw, str) else []
            if not isinstance(raw_approaches, list):
                raw_approaches = []
            approaches = [_normalize_approach(a, i) for i, a in enumerate(raw_approaches[:3]) if isinstance(a, dict)]
            if len(approaches) < 2:
                approaches.append(_normalize_approach(
                    {"approach_id": "B", "summary": objective, "pros": ["covers core"], "cons": ["may need iteration"], "risk_level": "medium", "scalability": "TBD", "complexity": "medium", "implementation_cost": "medium", "recommended_when": "when primary approach fails"},
                    1,
                ))
        except Exception:
            approaches = [
                _normalize_approach({"approach_id": "A", "summary": objective, "pros": ["direct"], "cons": ["limited scope"], "risk_level": "medium", "scalability": "TBD"}, 0),
                _normalize_approach({"approach_id": "B", "summary": f"Alternative for {objective[:100]}", "pros": ["flexible"], "cons": ["more work"], "risk_level": "medium", "scalability": "TBD"}, 1),
            ]

        # Phase 31: assign recommended_rank by comparative_score (desc)
        sorted_by_score = sorted(approaches, key=lambda x: x.get("comparative_score") or 0.0, reverse=True)
        rank_map = {a.get("approach_id"): i + 1 for i, a in enumerate(sorted_by_score)}
        for a in approaches:
            a["recommended_rank"] = rank_map.get(a.get("approach_id"), 0)

        tradeoffs = [a.get("tradeoffs") for a in approaches if a.get("tradeoffs")]
        top = sorted_by_score[0] if sorted_by_score else {}
        why_note = f"Approach {top.get('approach_id', '?')} ranked first (comparative_score={top.get('comparative_score', 0):.2f}); compare recommended_rank, fit_for_constraints."
        selection_rationale = f"Generated {len(approaches)} approach(es); {why_note}" if len(approaches) >= 2 else "Single approach; consider alternatives if needed."

        return normalize_helix_stage_result({
            "stage": "architect",
            "stage_status": "completed",
            "output_summary": f"Generated {len(approaches)} approach(es) for: {objective[:200]}",
            "approaches": approaches,
            "tradeoffs": tradeoffs,
            "selection_rationale": selection_rationale,
            "multi_approach_count": len(approaches),
            "implementation_plan": plan,
        })
    except Exception as e:
        return normalize_helix_stage_result({
            "stage": "architect",
            "stage_status": "error_fallback",
            "output_summary": str(e)[:500],
            "approaches": [],
            "tradeoffs": [],
            "repair_recommended": True,
            "repair_reason": f"Architect stage failed: {e}",
        })


def run_builder_stage(
    architect_result: dict[str, Any],
    requested_outcome: str,
    project_name: str,
) -> dict[str, Any]:
    """
    HELIX Builder: produce implementation plan or code-change package from architect output.
    Structured output only; no file modification.
    """
    plan = architect_result.get("implementation_plan") or {}
    impl_steps = plan.get("implementation_steps") or []
    objective = plan.get("objective") or requested_outcome

    impl_plan = {
        "objective": objective,
        "implementation_steps": impl_steps,
        "assumptions": plan.get("assumptions") or [],
        "risks": plan.get("risks") or [],
        "next_agent": plan.get("next_agent") or "coder",
        "patch_request": plan.get("patch_request"),
    }

    return normalize_helix_stage_result({
        "stage": "builder",
        "stage_status": "completed",
        "output_summary": f"Implementation plan: {len(impl_steps)} steps",
        "implementation_plan": impl_plan,
    })


def run_inspector_stage(
    builder_result: dict[str, Any],
    project_path: str | None,
    project_name: str,
) -> dict[str, Any]:
    """
    HELIX Inspector: validate correctness/regression/compatibility posture.
    Uses existing regression_checks; no execution.
    """
    try:
        from NEXUS.regression_checks import run_regression_checks

        reg = run_regression_checks(project_name=project_name, project_path=project_path)
        status = reg.get("regression_status") or "unknown"
        reason = reg.get("regression_reason") or ""
        checks = reg.get("checks") or {}

        passed = status == "passed"
        return normalize_helix_stage_result({
            "stage": "inspector",
            "stage_status": "completed" if passed else "issues_detected",
            "output_summary": f"Regression: {status}; {reason[:200]}",
            "validation_result": {
                "regression_status": status,
                "regression_reason": reason,
                "checks": checks,
            },
            "repair_recommended": not passed,
            "repair_reason": reason if not passed else "",
        })
    except Exception as e:
        return normalize_helix_stage_result({
            "stage": "inspector",
            "stage_status": "error_fallback",
            "output_summary": str(e)[:500],
            "validation_result": {"regression_status": "error", "regression_reason": str(e)},
            "repair_recommended": True,
            "repair_reason": str(e),
        })


def run_critic_stage(
    inspector_result: dict[str, Any],
    builder_result: dict[str, Any],
    requested_outcome: str,
) -> dict[str, Any]:
    """
    HELIX Critic: structured evaluation of correctness risk, maintainability,
    scalability, hidden failure points. No execution.
    """
    repair_rec = inspector_result.get("repair_recommended", False)
    val = inspector_result.get("validation_result") or {}
    reg_reason = val.get("regression_reason") or ""
    impl_plan = builder_result.get("implementation_plan") or {}
    steps = impl_plan.get("implementation_steps") or []
    risks = impl_plan.get("risks") or []

    correctness_risk = "high" if repair_rec else ("medium" if len(risks) > 2 else "low")
    maintainability = "low" if len(steps) > 8 else ("high" if len(steps) <= 3 else "medium")
    scalability = "unknown" if not steps else "medium"
    hidden_failure_points: list[str] = []
    testing_gaps: list[str] = []
    compatibility_risk = "low"
    if repair_rec:
        hidden_failure_points.append(f"Regression: {reg_reason[:150]}")
        compatibility_risk = "medium"
    if len(steps) > 5:
        hidden_failure_points.append("Many steps; consider integration points and rollback.")
        testing_gaps.append("Integration tests may be needed across step boundaries.")
    if not risks:
        hidden_failure_points.append("No explicit risks documented; consider edge cases.")
        testing_gaps.append("Edge cases and failure modes not explicitly tested.")
    if len(steps) > 3:
        testing_gaps.append("Consider unit tests per step.")

    # Phase 31: issue_categories, severity, confidence, remediation_priority
    issue_categories: list[str] = []
    if repair_rec:
        issue_categories.append("correctness")
    if hidden_failure_points:
        issue_categories.append("hidden_failure_points")
    if testing_gaps:
        issue_categories.append("testing_gaps")
    if compatibility_risk != "low":
        issue_categories.append("compatibility")
    if maintainability in ("low", "medium"):
        issue_categories.append("maintainability")
    issue_categories = list(dict.fromkeys(issue_categories))[:8]

    severity = "high" if correctness_risk == "high" or repair_rec else ("medium" if correctness_risk == "medium" else "low")
    confidence = "high" if repair_rec or len(hidden_failure_points) + len(testing_gaps) > 2 else ("medium" if hidden_failure_points or testing_gaps else "low")
    remediation_priority = "high" if severity == "high" else ("medium" if severity == "medium" else "low")

    critique_evaluation = {
        "correctness_risk": correctness_risk,
        "maintainability": maintainability,
        "scalability": scalability,
        "hidden_failure_points": hidden_failure_points[:5],
        "testing_gaps": testing_gaps[:5],
        "compatibility_risk": compatibility_risk,
        "issue_categories": issue_categories,
        "severity": severity,
        "confidence": confidence,
        "remediation_priority": remediation_priority,
    }

    critique = ""
    if repair_rec:
        critique = f"Inspector flagged issues: {reg_reason[:300]}. correctness_risk={correctness_risk}; maintainability={maintainability}; testing_gaps={len(testing_gaps)}; compatibility_risk={compatibility_risk}."
    else:
        critique = f"Structured evaluation: correctness_risk={correctness_risk}, maintainability={maintainability}, scalability={scalability}. Hidden failure points: {len(hidden_failure_points)}; testing_gaps: {len(testing_gaps)}; compatibility_risk={compatibility_risk}."

    return normalize_helix_stage_result({
        "stage": "critic",
        "stage_status": "completed",
        "output_summary": critique[:200],
        "critique": critique,
        "critique_evaluation": critique_evaluation,
        "repair_recommended": repair_rec,
        "repair_reason": reg_reason if repair_rec else "",
    })


def _make_suggestion_with_metadata(
    text: str,
    category: str,
    priority: str,
    expected_benefit: str,
    sequencing_group: int,
) -> dict[str, Any]:
    """Phase 31: wrap suggestion with priority, expected_benefit, recommendation_category, sequencing_group."""
    return {
        "suggestion": text,
        "priority": priority,
        "expected_benefit": expected_benefit,
        "recommendation_category": category,
        "sequencing_group": sequencing_group,
    }


def run_optimizer_stage(
    critic_result: dict[str, Any],
    builder_result: dict[str, Any],
) -> dict[str, Any]:
    """
    HELIX Optimizer: concrete improvements categorized by performance, structure,
    safety, readability. Structured output only; no execution.
    Phase 31: priority, expected_benefit, recommendation_category, sequencing_group.
    """
    impl_plan = builder_result.get("implementation_plan") or {}
    steps = impl_plan.get("implementation_steps") or []
    crit_eval = critic_result.get("critique_evaluation") or {}

    performance: list[str] = []
    structure: list[str] = []
    safety: list[str] = []
    readability: list[str] = []

    if len(steps) > 5:
        structure.append("Split into smaller milestones for maintainability.")
    structure.append("Ensure each step is testable and reversible.")
    structure.append("Document assumptions and failure modes.")
    safety.append("Add explicit error handling for each step.")
    safety.append("Consider rollback strategy.")
    readability.append("Add inline comments for non-obvious logic.")
    if crit_eval.get("correctness_risk") in ("high", "medium"):
        safety.append("Review regression checks before deployment.")

    implementation_sequencing: list[str] = []
    if steps:
        implementation_sequencing.append("1. Validate assumptions and rollback strategy before proceeding.")
        if len(steps) > 3:
            implementation_sequencing.append("2. Implement in logical milestones; verify each before proceeding.")
        implementation_sequencing.append("3. Run regression checks after each change.")
        implementation_sequencing.append("4. Document any deviations from the plan.")

    optimization_suggestions = {
        "performance": performance[:5],
        "structure": structure[:5],
        "safety": safety[:5],
        "readability": readability[:5],
        "implementation_sequencing": implementation_sequencing[:5],
    }
    optimizations = (
        performance + structure + safety + readability + implementation_sequencing
    )[:10]

    # Phase 31: suggestions_with_metadata (priority, expected_benefit, recommendation_category, sequencing_group)
    suggestions_with_priority: list[dict[str, Any]] = []
    seq = 0
    for cat, items in [
        ("safety", safety[:5]),
        ("structure", structure[:5]),
        ("performance", performance[:5]),
        ("readability", readability[:5]),
        ("implementation_sequencing", implementation_sequencing[:5]),
    ]:
        seq += 1
        prio = "high" if cat == "safety" else ("medium" if cat in ("structure", "implementation_sequencing") else "low")
        benefit = "risk_reduction" if cat == "safety" else ("maintainability" if cat == "structure" else "quality")
        for t in items:
            suggestions_with_priority.append(_make_suggestion_with_metadata(t, cat, prio, benefit, seq))

    return normalize_helix_stage_result({
        "stage": "optimizer",
        "stage_status": "completed",
        "output_summary": f"{len(optimizations)} optimization(s) across performance/structure/safety/readability/sequencing",
        "optimizations": optimizations,
        "optimization_suggestions": optimization_suggestions,
        "implementation_sequencing": implementation_sequencing[:5],
        "suggestions_with_priority": suggestions_with_priority[:15],
    })


def _infer_target_files_candidate(
    builder_result: dict[str, Any] | None,
    val_result: dict[str, Any],
    target_hint: str,
) -> list[str]:
    """Phase 32: infer candidate target files from patch_request, validation, or hint."""
    candidates: list[str] = []
    if builder_result:
        impl_plan = builder_result.get("implementation_plan") or {}
        patch_req = impl_plan.get("patch_request") if isinstance(impl_plan, dict) else None
        if isinstance(patch_req, dict) and patch_req.get("target_relative_path"):
            p = str(patch_req.get("target_relative_path", "")).strip()
            if p and p not in candidates:
                candidates.append(p)
    checks = val_result.get("checks") or {}
    if isinstance(checks, dict):
        for k, v in checks.items():
            if isinstance(v, str) and (".py" in v or ".ts" in v or ".js" in v or "/" in v):
                for part in v.replace("\\", "/").split():
                    if "/" in part or part.endswith((".py", ".ts", ".js", ".tsx", ".jsx")):
                        if part not in candidates and len(part) < 200:
                            candidates.append(part[:200])
    if target_hint and not candidates:
        import re
        for m in re.finditer(r"[\w./\-]+\.(py|ts|tsx|js|jsx|json)\b", target_hint):
            p = m.group(0)
            if p not in candidates:
                candidates.append(p)
    return candidates[:10]


def _infer_issue_scope(target_files: list[str], impl_steps: list[Any]) -> str:
    """Phase 32: infer issue_scope from targets or implementation steps."""
    if len(target_files) > 1:
        return "multi_file"
    if len(target_files) == 1:
        return "single_file"
    if impl_steps and len(impl_steps) > 3:
        return "multi_file"
    return "unknown"


def run_surgeon_stage(
    critic_result: dict[str, Any],
    inspector_result: dict[str, Any],
    requested_outcome: str,
    *,
    builder_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    HELIX Surgeon: invoked only when prior stages indicate repair is needed.
    Produces repair recommendation (structured); does NOT apply patches.
    When repair recommended and builder has patch_request, includes repair_patch_proposal.
    Actual patch application goes through normal approval/patch flow.
    Phase 32: richer repair artifacts (patch_readiness, issue_scope, suspected_root_causes,
    validation_recommendations, target_files_candidate, operator_handoff_notes).
    """
    repair_rec = critic_result.get("repair_recommended", False) or inspector_result.get("repair_recommended", False)
    repair_reason = critic_result.get("repair_reason") or inspector_result.get("repair_reason") or ""

    if not repair_rec:
        return normalize_helix_stage_result({
            "stage": "surgeon",
            "stage_status": "skipped",
            "output_summary": "No repair required; surgeon not invoked.",
            "repair_recommended": False,
            "repair_reason": "",
        })

    repair_patch_proposal = None
    if builder_result:
        impl_plan = builder_result.get("implementation_plan") or {}
        patch_req = impl_plan.get("patch_request") if isinstance(impl_plan, dict) else None
        if isinstance(patch_req, dict) and patch_req.get("target_relative_path") and patch_req.get("search_text"):
            repair_patch_proposal = {
                "target_relative_path": patch_req.get("target_relative_path"),
                "search_text": str(patch_req.get("search_text", ""))[:500],
                "replacement_text": str(patch_req.get("replacement_text", "")),
                "replace_all": bool(patch_req.get("replace_all", False)),
            }

    val_result = inspector_result.get("validation_result") or {}
    target_hint = ""
    if isinstance(val_result, dict):
        reg_reason = str(val_result.get("regression_reason") or "")
        if reg_reason:
            target_hint = reg_reason[:200]
    crit_eval = critic_result.get("critique_evaluation") or {}
    severity = "medium"
    if isinstance(crit_eval, dict) and crit_eval.get("correctness_risk") == "high":
        severity = "high"

    has_patch = repair_patch_proposal is not None
    repair_strategy_category = "patch_available" if has_patch else "builder_no_patch"
    impl_plan = (builder_result or {}).get("implementation_plan") or {}
    impl_steps = impl_plan.get("implementation_steps") or []

    # Phase 32: target_files_candidate, issue_scope
    target_files_candidate = _infer_target_files_candidate(builder_result, val_result, target_hint)
    issue_scope = _infer_issue_scope(target_files_candidate, impl_steps)

    # Phase 32: suspected_root_causes from critic + inspector
    suspected_root_causes: list[str] = []
    if repair_reason:
        suspected_root_causes.append(repair_reason[:200])
    hidden = crit_eval.get("hidden_failure_points") or []
    for h in hidden[:3]:
        if isinstance(h, str) and h.strip():
            suspected_root_causes.append(h.strip()[:150])
    testing_gaps = crit_eval.get("testing_gaps") or []
    for t in testing_gaps[:2]:
        if isinstance(t, str) and t.strip():
            suspected_root_causes.append(f"Testing gap: {t.strip()[:120]}")
    suspected_root_causes = list(dict.fromkeys(suspected_root_causes))[:8]

    missing_information_flags: list[str] = []
    recommended_next_actions: list[str] = []
    validation_recommendations: list[str] = []
    if not has_patch:
        missing_information_flags.append("Builder did not produce patch_request; no target file or search/replace.")
        missing_information_flags.append("Inspector regression reason may indicate target area.")
        recommended_next_actions.append("Review Builder implementation_plan for patch_request; refine if needed.")
        recommended_next_actions.append("Re-run Architect with narrower scope to elicit concrete patch.")
        recommended_next_actions.append("Consider manual fix guided by target_hint and repair_reason.")
        validation_recommendations.append("Re-run regression checks after any manual fix.")
        if testing_gaps:
            validation_recommendations.append("Address testing gaps before considering patch complete.")
        if not target_files_candidate:
            missing_information_flags.append("No target file candidate identified; scope may be unclear.")
    else:
        recommended_next_actions.append("Patch proposal available; submit through approval flow for apply.")
        validation_recommendations.append("Verify patch via approval flow before apply.")
        validation_recommendations.append("Run regression checks after patch apply.")

    # Phase 32: patch_readiness, human_followup_required
    if has_patch:
        patch_readiness = "high"
        human_followup_required = False
    elif target_files_candidate and suspected_root_causes:
        patch_readiness = "medium"
        human_followup_required = True
    else:
        patch_readiness = "low"
        human_followup_required = True

    # Phase 32: operator_handoff_notes, patch_followup_candidate (forward-compat with governed patch flows)
    patch_followup_candidate = not has_patch and (len(target_files_candidate) > 0 or bool(target_hint))
    if has_patch and repair_patch_proposal:
        operator_handoff_notes = f"Patch ready for approval flow. Target: {repair_patch_proposal.get('target_relative_path', '?')}. Severity: {severity}."
    elif patch_readiness == "medium":
        operator_handoff_notes = f"Partial info: {len(target_files_candidate)} target candidate(s), {len(suspected_root_causes)} suspected cause(s). {len(missing_information_flags)} missing info flag(s). Human follow-up required."
    else:
        operator_handoff_notes = f"Low readiness. Repair reason: {repair_reason[:100]}. Target hint: {target_hint[:80] or 'none'}. Review recommended_next_actions and missing_information_flags."

    repair_metadata = {
        "repair_reason": repair_reason[:500],
        "severity": severity,
        "target_hint": target_hint,
        "has_patch_payload": has_patch,
        "repair_strategy_category": repair_strategy_category,
        "missing_information_flags": missing_information_flags[:5],
        "recommended_next_actions": recommended_next_actions[:5],
        "target_files_candidate": target_files_candidate[:10],
        "issue_scope": issue_scope,
        "suspected_root_causes": suspected_root_causes[:8],
        "validation_recommendations": validation_recommendations[:5],
        "patch_readiness": patch_readiness,
        "human_followup_required": human_followup_required,
        "operator_handoff_notes": operator_handoff_notes[:500],
        "patch_followup_candidate": patch_followup_candidate,
    }

    return normalize_helix_stage_result({
        "stage": "surgeon",
        "stage_status": "repair_recommended",
        "output_summary": f"Repair recommended: {repair_reason[:200]}; strategy={repair_strategy_category}; patch_readiness={patch_readiness}",
        "repair_recommended": True,
        "repair_reason": repair_reason,
        "repair_patch_proposal": repair_patch_proposal,
        "repair_metadata": repair_metadata,
    })
