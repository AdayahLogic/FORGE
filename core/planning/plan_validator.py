from typing import Any


ALLOWED_NEXT_AGENTS = {"coder", "tester", "docs"}


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    cleaned: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            cleaned.append(text)
    return cleaned


def _validate_patch_request(value: Any) -> tuple[dict | None, list[str]]:
    """
    Returns:
    - normalized patch_request or None
    - validation issues
    """
    issues: list[str] = []

    if value is None:
        return None, issues

    if not isinstance(value, dict):
        issues.append("patch_request must be an object or null.")
        return None, issues

    approved = bool(value.get("approved", False))
    target_relative_path = value.get("target_relative_path")
    search_text = value.get("search_text")
    replacement_text = value.get("replacement_text")
    replace_all = bool(value.get("replace_all", False))
    justification = value.get("justification", "")

    if not approved:
        # Non-approved patch requests are treated as absent
        return None, issues

    if not _is_non_empty_string(target_relative_path):
        issues.append("patch_request.target_relative_path is required when approved=true.")

    if not _is_non_empty_string(search_text):
        issues.append("patch_request.search_text is required when approved=true.")

    if not isinstance(replacement_text, str):
        issues.append("patch_request.replacement_text must be a string when approved=true.")

    if isinstance(search_text, str) and len(search_text) > 20000:
        issues.append("patch_request.search_text is too large.")

    if isinstance(replacement_text, str) and len(replacement_text) > 40000:
        issues.append("patch_request.replacement_text is too large.")

    normalized = None
    if not issues:
        normalized = {
            "approved": True,
            "target_relative_path": target_relative_path.strip(),
            "search_text": search_text,
            "replacement_text": replacement_text,
            "replace_all": replace_all,
            "justification": justification.strip() if isinstance(justification, str) else "",
        }

    return normalized, issues


def validate_and_normalize_plan(plan: Any, project_name: str) -> dict:
    """
    Strict validation layer for planner output.

    Returns a normalized plan with:
    - validation_status
    - validation_issues
    - patch_request normalized or nulled
    """
    if not isinstance(plan, dict):
        return {
            "objective": f"Fallback planning output for {project_name}",
            "assumptions": [
                "Planner output was not a JSON object.",
            ],
            "implementation_steps": [
                "Review planner output format.",
                "Refine prompt and retry the planning call.",
            ],
            "risks": [
                "Planner returned non-object JSON.",
            ],
            "next_agent": "coder",
            "patch_request": None,
            "validation_status": "invalid",
            "validation_issues": [
                "Planner output must be a JSON object.",
            ],
        }

    issues: list[str] = []

    objective = plan.get("objective")
    assumptions = plan.get("assumptions")
    implementation_steps = plan.get("implementation_steps")
    risks = plan.get("risks")
    next_agent = plan.get("next_agent")
    patch_request = plan.get("patch_request")

    if not _is_non_empty_string(objective):
        issues.append("objective is required and must be a non-empty string.")
        objective = f"Plan next implementation slice for {project_name}"
    else:
        objective = objective.strip()

    normalized_assumptions = _normalize_string_list(assumptions)
    if not normalized_assumptions:
        issues.append("assumptions should contain at least one item.")

    normalized_steps = _normalize_string_list(implementation_steps)
    if not normalized_steps:
        issues.append("implementation_steps must contain at least one actionable step.")

    normalized_risks = _normalize_string_list(risks)
    if not normalized_risks:
        issues.append("risks should contain at least one item.")

    if not _is_non_empty_string(next_agent):
        issues.append("next_agent is required.")
        next_agent = "coder"
    else:
        next_agent = next_agent.strip().lower()
        if next_agent not in ALLOWED_NEXT_AGENTS:
            issues.append(
                f"next_agent must be one of: {sorted(ALLOWED_NEXT_AGENTS)}."
            )
            next_agent = "coder"

    normalized_patch_request, patch_issues = _validate_patch_request(patch_request)
    issues.extend(patch_issues)

    status = "valid" if not issues else "valid_with_warnings"

    # Escalate to invalid if no actionable steps exist
    if not normalized_steps:
        status = "invalid"
        normalized_steps = [
            "Review planner output and repair schema compliance.",
            "Retry with a narrower and safer implementation slice.",
        ]

    return {
        "objective": objective,
        "assumptions": normalized_assumptions or [
            "Planner output required fallback assumptions."
        ],
        "implementation_steps": normalized_steps,
        "risks": normalized_risks or [
            "Planner output required fallback risk handling."
        ],
        "next_agent": next_agent,
        "patch_request": normalized_patch_request,
        "validation_status": status,
        "validation_issues": issues,
    }