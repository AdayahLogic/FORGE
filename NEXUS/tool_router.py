"""
Nexus core tool router.

Provides a safe routing decision for (agent, tool) without changing execution.
Used to check whether a tool is allowed for an agent before execution layers run.
"""

from __future__ import annotations

from typing import Any

from NEXUS.tool_registry import TOOL_REGISTRY, get_tools_for_agent
from NEXUS.agent_policy_registry import (
    is_tool_blocked_for_agent,
    is_tool_review_required_for_agent,
)


def route_tool(agent_name: str, tool_name: str) -> dict[str, Any]:
    """
    Check whether the given tool is allowed for the given agent.

    Returns a routing decision object. Does not execute the tool.
    """
    agent = (agent_name or "").strip().lower()
    tool = (tool_name or "").strip().lower()

    meta = TOOL_REGISTRY.get(tool)
    if not meta:
        return {
            "allowed": False,
            "tool_name": tool_name,
            "agent_name": agent_name,
            "reason": "Tool not found in registry.",
            "human_review_recommended": True,
            "status": "rejected",
        }

    if meta.get("status") != "active" or not meta.get("implemented"):
        return {
            "allowed": False,
            "tool_name": tool_name,
            "agent_name": agent_name,
            "reason": f"Tool '{tool}' is not implemented or not active.",
            "human_review_recommended": meta.get("human_review_recommended", True),
            "status": "rejected",
        }

    allowed_agents = [a.lower() for a in meta.get("allowed_agents", [])]
    if agent not in allowed_agents:
        return {
            "allowed": False,
            "tool_name": tool_name,
            "agent_name": agent_name,
            "reason": f"Agent '{agent_name}' is not in allowed_agents for tool '{tool}'.",
            "human_review_recommended": meta.get("human_review_recommended", True),
            "status": "rejected",
        }

    # Policy layer: blocked tools take precedence
    if is_tool_blocked_for_agent(agent, tool):
        return {
            "allowed": False,
            "tool_name": tool_name,
            "agent_name": agent_name,
            "reason": "Tool blocked by agent policy.",
            "human_review_recommended": True,
            "status": "rejected",
            "policy_rejected": True,
        }

    review_required = is_tool_review_required_for_agent(agent, tool)
    human_review = meta.get("human_review_recommended", True) or review_required

    sensitivity = meta.get("sensitivity") or None
    risk_level = meta.get("risk_level") or None
    external_internal = meta.get("external_internal") or None
    allowed_actions = meta.get("allowed_actions") if isinstance(meta.get("allowed_actions"), list) else []
    tool_family = meta.get("tool_family") or None
    tool_gateway_families = meta.get("tool_gateway_families") if isinstance(meta.get("tool_gateway_families"), list) else []

    return {
        "allowed": True,
        "tool_name": tool_name,
        "agent_name": agent_name,
        "reason": "Tool allowed for this agent.",
        "human_review_recommended": human_review,
        "review_required": review_required,
        "status": "allowed",
        "category": meta.get("category"),
        "tool_family": tool_family,
        "external_internal": external_internal,
        "sensitivity": sensitivity,
        "risk_level": risk_level,
        "allowed_actions": allowed_actions,
        "tool_gateway_families": tool_gateway_families,
    }
