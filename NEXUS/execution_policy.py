"""
NEXUS execution policy / approval gate layer.

Provides a normalized decision (allowed | review_required | blocked) for
agent/tool/action checks. Uses tool_router and agent policy under the hood.
Does not block execution by itself; callers use the decision for reporting
and optional gating.
"""

from __future__ import annotations

from typing import Any


def evaluate(
    agent_name: str,
    tool_name: str,
    action_type: str | None = None,
    target_path: str | None = None,
) -> dict[str, Any]:
    """
    Return a normalized execution policy decision for the given agent and tool.

    Uses tool_router.route_tool(agent_name, tool_name) and normalizes the
    result into a canonical shape for reporting and optional approval gates.

    Returns:
        status: "allowed" | "review_required" | "blocked"
        allowed: bool
        review_required: bool
        blocked: bool
        reason: str
        human_review_recommended: bool
        action_type: passed through if provided
        target_path: passed through if provided
    """
    from NEXUS.tool_router import route_tool

    agent = (agent_name or "").strip()
    tool = (tool_name or "").strip()
    route = route_tool(agent, tool)

    allowed = bool(route.get("allowed", False))
    review_required = bool(route.get("review_required", False))
    reason = str(route.get("reason", "Unknown"))
    human_review = bool(route.get("human_review_recommended", True))

    if not allowed:
        status = "blocked"
        blocked = True
        review_required = False
    elif review_required or human_review:
        status = "review_required"
        blocked = False
        review_required = True
        human_review = True
    else:
        status = "allowed"
        blocked = False
        review_required = False

    decision: dict[str, Any] = {
        "status": status,
        "allowed": allowed,
        "review_required": review_required,
        "blocked": blocked,
        "reason": reason,
        "human_review_recommended": human_review,
        "agent_name": agent,
        "tool_name": tool,
    }
    if action_type is not None:
        decision["action_type"] = action_type
    if target_path is not None:
        decision["target_path"] = target_path
    return decision


def evaluate_action_family(
    *,
    action_family: str,
    agent_name: str,
    tool_name: str | None = None,
    action_type: str | None = None,
    target_path: str | None = None,
) -> dict[str, Any]:
    """
    Compact policy decision for action families.

    Families: terminal, file_modification, diff_patch, browser_research,
    deployment_preflight.

    Returns the same decision shape as evaluate(...), keeping compatibility.
    """
    fam = (action_family or "").strip().lower()
    # Map to a canonical tool name when tool_name isn't provided.
    mapped_tool = (tool_name or "").strip() or fam
    if fam == "deployment_preflight":
        # Evaluation-only: allow but recommend review by default.
        decision = evaluate(agent_name=agent_name, tool_name=mapped_tool, action_type=action_type, target_path=target_path)
        # Ensure non-escalation: if allowed, keep as review_required to avoid implied auto-deploy.
        if decision.get("allowed"):
            decision["status"] = "review_required"
            decision["review_required"] = True
            decision["human_review_recommended"] = True
            decision["reason"] = (decision.get("reason") or "Tool allowed for this agent.") + " Deployment preflight is review-required."
        return decision
    return evaluate(agent_name=agent_name, tool_name=mapped_tool, action_type=action_type, target_path=target_path)


def evaluate_action_family_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises; returns blocked on exception."""
    try:
        return evaluate_action_family(**kwargs)
    except Exception:
        return {
            "status": "blocked",
            "allowed": False,
            "review_required": False,
            "blocked": True,
            "reason": "Execution policy evaluation failed.",
            "human_review_recommended": True,
            "agent_name": (kwargs.get("agent_name") or ""),
            "tool_name": (kwargs.get("tool_name") or kwargs.get("action_family") or ""),
            "action_type": kwargs.get("action_type"),
            "target_path": kwargs.get("target_path"),
        }
