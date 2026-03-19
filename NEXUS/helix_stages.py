"""
NEXUS HELIX stage logic (Phase 21).

Each stage produces structured output. No arbitrary code execution.
Uses existing PlannerEngine, regression_checks, model_router.
"""

from __future__ import annotations

from typing import Any

from NEXUS.helix_registry import normalize_helix_stage_result


def _normalize_approach(a: dict[str, Any], idx: int) -> dict[str, Any]:
    """Normalize approach to Phase 22 contract: approach_id, summary, pros, cons, risk_level, scalability."""
    if not isinstance(a, dict):
        return {}
    aid = str(a.get("approach_id") or a.get("name") or chr(65 + idx))[:1]
    return {
        "approach_id": aid,
        "summary": str(a.get("summary") or a.get("name") or "")[:500],
        "pros": list(a.get("pros") or [])[:10],
        "cons": list(a.get("cons") or [])[:10],
        "risk_level": str(a.get("risk_level") or "medium").strip().lower()[:20],
        "scalability": str(a.get("scalability") or "")[:200],
        "tradeoffs": a.get("tradeoffs") if isinstance(a.get("tradeoffs"), dict) else {},
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

Return ONLY a JSON array, no markdown. Example:
[{{"approach_id":"A","summary":"Minimal change","pros":["fast","simple"],"cons":["less flexible"],"risk_level":"low","scalability":"single-node"}}, ...]
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
                    {"approach_id": "B", "summary": objective, "pros": ["covers core"], "cons": ["may need iteration"], "risk_level": "medium", "scalability": "TBD"},
                    1,
                ))
        except Exception:
            approaches = [
                _normalize_approach({"approach_id": "A", "summary": objective, "pros": ["direct"], "cons": ["limited scope"], "risk_level": "medium", "scalability": "TBD"}, 0),
                _normalize_approach({"approach_id": "B", "summary": f"Alternative for {objective[:100]}", "pros": ["flexible"], "cons": ["more work"], "risk_level": "medium", "scalability": "TBD"}, 1),
            ]

        tradeoffs = [a.get("tradeoffs") for a in approaches if a.get("tradeoffs")]

        return normalize_helix_stage_result({
            "stage": "architect",
            "stage_status": "completed",
            "output_summary": f"Generated {len(approaches)} approach(es) for: {objective[:200]}",
            "approaches": approaches,
            "tradeoffs": tradeoffs,
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
    hidden_failure_points = []
    if repair_rec:
        hidden_failure_points.append(f"Regression: {reg_reason[:150]}")
    if len(steps) > 5:
        hidden_failure_points.append("Many steps; consider integration points and rollback.")
    if not risks:
        hidden_failure_points.append("No explicit risks documented; consider edge cases.")

    critique_evaluation = {
        "correctness_risk": correctness_risk,
        "maintainability": maintainability,
        "scalability": scalability,
        "hidden_failure_points": hidden_failure_points[:5],
    }

    critique = ""
    if repair_rec:
        critique = f"Inspector flagged issues: {reg_reason[:300]}. correctness_risk={correctness_risk}; maintainability={maintainability}."
    else:
        critique = f"Structured evaluation: correctness_risk={correctness_risk}, maintainability={maintainability}, scalability={scalability}. Hidden failure points: {len(hidden_failure_points)}."

    return normalize_helix_stage_result({
        "stage": "critic",
        "stage_status": "completed",
        "output_summary": critique[:200],
        "critique": critique,
        "critique_evaluation": critique_evaluation,
        "repair_recommended": repair_rec,
        "repair_reason": reg_reason if repair_rec else "",
    })


def run_optimizer_stage(
    critic_result: dict[str, Any],
    builder_result: dict[str, Any],
) -> dict[str, Any]:
    """
    HELIX Optimizer: concrete improvements categorized by performance, structure,
    safety, readability. Structured output only; no execution.
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

    optimization_suggestions = {
        "performance": performance[:5],
        "structure": structure[:5],
        "safety": safety[:5],
        "readability": readability[:5],
    }
    optimizations = (
        performance + structure + safety + readability
    )[:10]

    return normalize_helix_stage_result({
        "stage": "optimizer",
        "stage_status": "completed",
        "output_summary": f"{len(optimizations)} optimization(s) across performance/structure/safety/readability",
        "optimizations": optimizations,
        "optimization_suggestions": optimization_suggestions,
    })


def run_surgeon_stage(
    critic_result: dict[str, Any],
    inspector_result: dict[str, Any],
    requested_outcome: str,
) -> dict[str, Any]:
    """
    HELIX Surgeon: invoked only when prior stages indicate repair is needed.
    Produces repair recommendation (structured); does NOT apply patches.
    Actual patch application goes through normal approval/patch flow.
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

    return normalize_helix_stage_result({
        "stage": "surgeon",
        "stage_status": "repair_recommended",
        "output_summary": f"Repair recommended: {repair_reason[:200]}",
        "repair_recommended": True,
        "repair_reason": repair_reason,
    })
