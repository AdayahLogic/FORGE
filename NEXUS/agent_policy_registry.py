"""
NEXUS agent policy registry.

Defines per-agent policy: allowed tools, review-required tools, and blocked tools.
Used by tool_router for safe routing decisions and by reporting for policy-aware summaries.
Does not replace tool_registry; policy is consulted after tool_registry allow check.
"""

from __future__ import annotations

from typing import Any

# policy_status: active | planned
AGENT_POLICY_REGISTRY: dict[str, dict[str, Any]] = {
    "coder": {
        "allowed_tools": [],
        "review_required_tools": ["file_modification", "diff_patch"],
        "blocked_tools": ["deployment", "billing_admin", "analytics_export"],
        "policy_status": "active",
        "notes": "Routable implementation agent; tool access governed by tool_registry and execution bridge.",
    },
    "tester": {
        "allowed_tools": [],
        "review_required_tools": ["terminal"],
        "blocked_tools": ["deployment", "billing_admin", "analytics_export"],
        "policy_status": "active",
        "notes": "Routable validation agent; tool access governed by tool_registry.",
    },
    "docs": {
        "allowed_tools": [],
        "review_required_tools": ["file_modification"],
        "blocked_tools": ["deployment", "billing_admin", "analytics_export"],
        "policy_status": "active",
        "notes": "Routable documentation agent; tool access governed by tool_registry.",
    },
    "architect": {
        "allowed_tools": [],
        "review_required_tools": [],
        "blocked_tools": ["terminal", "file_modification", "diff_patch", "deployment", "billing_admin", "analytics_export"],
        "policy_status": "planned",
        "notes": "Planned planning role; currently mapped to planner. No direct tool use.",
    },
    "helix": {
        "allowed_tools": [],
        "review_required_tools": [],
        "blocked_tools": [],
        "policy_status": "planned",
        "notes": "Planned senior engineering agent; policy TBD.",
    },
    "surgeon": {
        "allowed_tools": [],
        "review_required_tools": [],
        "blocked_tools": [],
        "policy_status": "planned",
        "notes": "Planned debugging specialist; policy TBD.",
    },
    "prism": {
        "allowed_tools": [],
        "review_required_tools": [],
        "blocked_tools": [],
        "policy_status": "planned",
        "notes": "Planned marketing/creative agent; policy TBD.",
    },
}


def get_agent_policy(agent_name: str | None) -> dict[str, Any] | None:
    """Return policy entry for canonical agent name, or None if not in registry."""
    if not agent_name:
        return None
    key = (agent_name or "").strip().lower()
    return AGENT_POLICY_REGISTRY.get(key)


def is_tool_blocked_for_agent(agent_name: str | None, tool_name: str | None) -> bool:
    """Return True if the tool is in the agent's blocked_tools list."""
    policy = get_agent_policy(agent_name)
    if not policy or not tool_name:
        return False
    tool = (tool_name or "").strip().lower()
    return tool in [t.lower() for t in policy.get("blocked_tools", [])]


def is_tool_review_required_for_agent(agent_name: str | None, tool_name: str | None) -> bool:
    """Return True if the tool is in the agent's review_required_tools list."""
    policy = get_agent_policy(agent_name)
    if not policy or not tool_name:
        return False
    tool = (tool_name or "").strip().lower()
    return tool in [t.lower() for t in policy.get("review_required_tools", [])]


def get_policy_summary_for_agent(agent_name: str | None) -> dict[str, Any]:
    """Return a safe summary dict for reporting: policy_status, allowed_count, blocked_count, review_required_count."""
    policy = get_agent_policy(agent_name)
    if not policy:
        return {"policy_status": None, "allowed_count": 0, "blocked_count": 0, "review_required_count": 0}
    return {
        "policy_status": policy.get("policy_status"),
        "allowed_count": len(policy.get("allowed_tools", [])),
        "blocked_count": len(policy.get("blocked_tools", [])),
        "review_required_count": len(policy.get("review_required_tools", [])),
    }
