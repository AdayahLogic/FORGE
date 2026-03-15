"""
Nexus core registry of executable tools.

Models tools used by workflow agents (terminal, browser_research, file_modification,
diff_patch, tool_execution) and planned tools. Used by tool_inspector and tool_router
for summaries and routing decisions.
"""

from __future__ import annotations

from typing import Any

TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "terminal": {
        "implemented": True,
        "status": "active",
        "category": "execution",
        "allowed_agents": ["terminal"],
        "human_review_recommended": True,
        "description": "Runs allowlisted terminal commands and records execution results.",
    },
    "browser_research": {
        "implemented": True,
        "status": "active",
        "category": "research",
        "allowed_agents": ["browser_research"],
        "human_review_recommended": True,
        "description": "Launches safe research URLs and writes browser research reports.",
    },
    "file_modification": {
        "implemented": True,
        "status": "active",
        "category": "file_ops",
        "allowed_agents": ["file_modification"],
        "human_review_recommended": True,
        "description": "Performs controlled append/update operations on project files.",
    },
    "diff_patch": {
        "implemented": True,
        "status": "active",
        "category": "file_ops",
        "allowed_agents": ["diff_patch"],
        "human_review_recommended": True,
        "description": "Applies approval-gated diff/patch operations.",
    },
    "tool_execution": {
        "implemented": True,
        "status": "active",
        "category": "execution",
        "allowed_agents": ["tool_execution"],
        "human_review_recommended": True,
        "description": "Runs structured internal tool sequences and writes tool execution reports.",
    },
    "deployment": {
        "implemented": False,
        "status": "planned",
        "category": "deployment",
        "allowed_agents": [],
        "human_review_recommended": True,
        "description": "Deployment and release tooling (planned).",
    },
    "billing_admin": {
        "implemented": False,
        "status": "planned",
        "category": "admin",
        "allowed_agents": [],
        "human_review_recommended": True,
        "description": "Billing and subscription administration (planned).",
    },
    "analytics_export": {
        "implemented": False,
        "status": "planned",
        "category": "analytics",
        "allowed_agents": [],
        "human_review_recommended": True,
        "description": "Analytics export and reporting (planned).",
    },
}


def list_active_tools() -> list[str]:
    """Return sorted list of tool names that are active and implemented."""
    return sorted([
        name for name, meta in TOOL_REGISTRY.items()
        if meta.get("status") == "active" and meta.get("implemented") is True
    ])


def list_planned_tools() -> list[str]:
    """Return sorted list of tool names that are planned."""
    return sorted([
        name for name, meta in TOOL_REGISTRY.items()
        if meta.get("status") == "planned"
    ])


def get_tools_for_agent(agent_name: str | None) -> list[str]:
    """Return sorted list of tool names the given agent is allowed to use."""
    if not agent_name:
        return []
    agent = (agent_name or "").strip().lower()
    return sorted([
        name for name, meta in TOOL_REGISTRY.items()
        if agent in [a.lower() for a in meta.get("allowed_agents", [])]
    ])
