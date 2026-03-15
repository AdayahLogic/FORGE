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
