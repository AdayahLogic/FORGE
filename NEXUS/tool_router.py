"""
Nexus core tool router.

Provides a safe routing decision for (agent, tool) without changing execution.
Used to check whether a tool is allowed for an agent before execution layers run.
"""

from __future__ import annotations

from typing import Any

from NEXUS.tool_registry import TOOL_REGISTRY, get_tools_for_agent


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

    return {
        "allowed": True,
        "tool_name": tool_name,
        "agent_name": agent_name,
        "reason": "Tool allowed for this agent.",
        "human_review_recommended": meta.get("human_review_recommended", True),
        "status": "allowed",
        "category": meta.get("category"),
    }
