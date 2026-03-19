"""
NEXUS HELIX stage logic (Phase 21).

Each stage produces structured output. No arbitrary code execution.
Uses existing PlannerEngine, regression_checks, model_router.
"""

from __future__ import annotations

from typing import Any

from NEXUS.helix_registry import normalize_helix_stage_result


def run_architect_stage(
    requested_outcome: str,
    project_name: str,
    loaded_context: dict[str, Any],
) -> dict[str, Any]:
    """
    HELIX Architect: understand request, generate 2-3 approaches, tradeoff analysis.
    Uses PlannerEngine; produces structured approaches with tradeoffs.
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

        # Build 2-3 approaches from plan + tradeoff prompt (lightweight)
        tradeoff_prompt = f"""
Given this implementation plan for project {project_name}:

Objective: {objective}
Steps: {impl_steps}
Risks: {risks}

Produce exactly 2-3 distinct implementation approaches as a JSON array.
For each approach include: name, summary, tradeoffs (speed vs scalability, simplicity vs flexibility, cost vs performance).
Return ONLY a JSON array, no markdown. Example:
[{{"name":"A","summary":"...","tradeoffs":{{"speed":"fast","scalability":"medium","simplicity":"high"}}}}, ...]
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
            approaches = json.loads(raw) if isinstance(raw, str) else []
            if not isinstance(approaches, list):
                approaches = []
            approaches = approaches[:3]
        except Exception:
            approaches = [
                {"name": "primary", "summary": objective, "tradeoffs": {"speed": "medium", "scalability": "medium", "simplicity": "medium"}},
            ]

        tradeoffs = []
        for a in approaches:
            if isinstance(a, dict) and a.get("tradeoffs"):
                tradeoffs.append(a.get("tradeoffs"))

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
    HELIX Critic: challenge fragility; ask what is wrong / what fails later.
    Structured critique; no execution.
    """
    repair_rec = inspector_result.get("repair_recommended", False)
    val = inspector_result.get("validation_result") or {}
    reg_reason = val.get("regression_reason") or ""

    critique = ""
    if repair_rec:
        critique = f"Inspector flagged issues: {reg_reason[:300]}. Review regression checks and fix before proceeding."
    else:
        critique = "No critical issues from Inspector. Consider: edge cases, error handling, backward compatibility."

    return normalize_helix_stage_result({
        "stage": "critic",
        "stage_status": "completed",
        "output_summary": critique[:200],
        "critique": critique,
        "repair_recommended": repair_rec,
        "repair_reason": reg_reason if repair_rec else "",
    })


def run_optimizer_stage(
    critic_result: dict[str, Any],
    builder_result: dict[str, Any],
) -> dict[str, Any]:
    """
    HELIX Optimizer: improve maintainability/performance/clarity.
    Structured recommendations only; no execution.
    """
    impl_plan = builder_result.get("implementation_plan") or {}
    steps = impl_plan.get("implementation_steps") or []

    optimizations = []
    if len(steps) > 5:
        optimizations.append("Consider splitting into smaller milestones for maintainability.")
    optimizations.append("Ensure each step is testable and reversible.")
    optimizations.append("Document assumptions and failure modes.")

    return normalize_helix_stage_result({
        "stage": "optimizer",
        "stage_status": "completed",
        "output_summary": f"{len(optimizations)} optimization(s) suggested",
        "optimizations": optimizations,
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
