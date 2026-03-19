"""
Nexus core registry of executable tools.

Models tools used by workflow agents (terminal, browser_research, file_modification,
diff_patch, tool_execution) and planned tools. Used by tool_inspector and tool_router
for summaries and routing decisions.
"""

from __future__ import annotations

from typing import Any

TOOL_CONTRACT_VERSION = "1.0"

# NOTE ON CONTRACT HONESTY:
# This repository's "tool registry" is metadata used for safe routing decisions
# and operator visibility. It must not silently broaden permissions. Actual
# enforcement remains with AEGIS (policy_engine + file_guard + ForgeShell).

TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "terminal": {
        "implemented": True,
        "status": "active",
        "category": "execution",
        "tool_family": "terminal",
        "external_internal": "internal",
        "sensitivity": "medium",
        "allowed_actions": ["evaluate", "read"],
        "risk_level": "medium",
        "allowed_agents": ["terminal"],
        "human_review_recommended": True,
        "description": "Runs allowlisted terminal commands and records execution results.",
    },
    "browser_research": {
        "implemented": True,
        "status": "active",
        "category": "research",
        "tool_family": "browser_research",
        "external_internal": "internal",
        "sensitivity": "medium",
        "allowed_actions": ["evaluate", "read"],
        "risk_level": "medium",
        "allowed_agents": ["browser_research"],
        "human_review_recommended": True,
        "description": "Launches safe research URLs and writes browser research reports.",
    },
    "file_modification": {
        "implemented": True,
        "status": "active",
        "category": "file_ops",
        "tool_family": "file_modification",
        "external_internal": "internal",
        "sensitivity": "high",
        "allowed_actions": ["evaluate", "read", "mutate"],
        "risk_level": "high",
        "allowed_agents": ["file_modification"],
        "human_review_recommended": True,
        "description": "Performs controlled append/update operations on project files.",
    },
    "diff_patch": {
        "implemented": True,
        "status": "active",
        "category": "file_ops",
        "tool_family": "diff_patch",
        "external_internal": "internal",
        "sensitivity": "high",
        "allowed_actions": ["evaluate", "read", "mutate"],
        "risk_level": "high",
        "allowed_agents": ["diff_patch"],
        "human_review_recommended": True,
        "description": "Applies approval-gated diff/patch operations.",
    },
    "tool_execution": {
        "implemented": True,
        "status": "active",
        "category": "execution",
        "tool_family": "tool_execution",
        "external_internal": "internal",
        "sensitivity": "medium",
        "allowed_actions": ["evaluate", "read", "mutate"],
        "risk_level": "medium",
        "allowed_agents": ["tool_execution"],
        "human_review_recommended": True,
        "description": "Runs structured internal tool sequences and writes tool execution reports.",
    },
    "deployment": {
        "implemented": False,
        "status": "planned",
        "category": "deployment",
        "tool_family": "deployment",
        "external_internal": "planned_external",
        "sensitivity": "high",
        "allowed_actions": ["evaluate", "read"],
        "risk_level": "high",
        # No execution capabilities in this phase; metadata only.
        "tool_gateway_families": [],
        "allowed_agents": [],
        "human_review_recommended": True,
        "description": "Deployment and release tooling (planned).",
    },
    "billing_admin": {
        "implemented": False,
        "status": "planned",
        "category": "admin",
        "tool_family": "billing_admin",
        "external_internal": "planned_external",
        "sensitivity": "high",
        "allowed_actions": ["evaluate", "read"],
        "risk_level": "high",
        "tool_gateway_families": [],
        "allowed_agents": [],
        "human_review_recommended": True,
        "description": "Billing and subscription administration (planned).",
    },
    "analytics_export": {
        "implemented": False,
        "status": "planned",
        "category": "analytics",
        "tool_family": "analytics_export",
        "external_internal": "planned_external",
        "sensitivity": "medium",
        "allowed_actions": ["evaluate", "read"],
        "risk_level": "medium",
        "tool_gateway_families": [],
        "allowed_agents": [],
        "human_review_recommended": True,
        "description": "Analytics export and reporting (planned).",
    },

    # Git-aware scaffolding (Phase 16).
    # These entries are metadata-only unless real execution integration is added.
    "git_status": {
        "implemented": False,
        "status": "planned",
        "category": "git_ops",
        "tool_family": "git_status",
        "external_internal": "internal",
        "sensitivity": "low",
        "allowed_actions": ["evaluate", "read"],
        "risk_level": "low",
        # AEGIS tool_gateway family (ForgeShell wrapper) known for this scaffold.
        "tool_gateway_families": ["git_status"],
        "allowed_agents": [],
        "human_review_recommended": True,
        "description": "Git repository status visibility (planned scaffold; evaluation-only).",
    },
    "git_diff": {
        "implemented": False,
        "status": "planned",
        "category": "git_ops",
        "tool_family": "git_diff",
        "external_internal": "internal",
        "sensitivity": "low",
        "allowed_actions": ["evaluate", "read"],
        "risk_level": "low",
        # Scaffold only: no direct tool_gateway family wired yet in this repo.
        "tool_gateway_families": [],
        "allowed_agents": [],
        "human_review_recommended": True,
        "description": "Git diff visibility (planned scaffold; diff metadata only).",
    },

    # Connector scaffolding for future API/cloud integrations (Phase 16).
    # Marked planned_external and evaluation-only. No execution claims.
    "api_connector_evaluate": {
        "implemented": False,
        "status": "planned",
        "category": "connector",
        "tool_family": "api_connector_evaluate",
        "external_internal": "planned_external",
        "sensitivity": "high",
        "allowed_actions": ["evaluate", "read"],
        "risk_level": "high",
        "tool_gateway_families": [],
        "allowed_agents": [],
        "human_review_recommended": True,
        "description": "API connector scaffold for evaluation-only interactions (planned).",
    },
    "cloud_connector_metadata_evaluate": {
        "implemented": False,
        "status": "planned",
        "category": "connector",
        "tool_family": "cloud_connector_metadata_evaluate",
        "external_internal": "planned_external",
        "sensitivity": "high",
        "allowed_actions": ["evaluate", "read"],
        "risk_level": "high",
        "tool_gateway_families": [],
        "allowed_agents": [],
        "human_review_recommended": True,
        "description": "Cloud connector scaffold for metadata evaluation (planned).",
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


def normalize_tool_metadata(tool_name: str) -> dict[str, Any]:
    """
    Return a deterministic, contract-shaped tool metadata dict.

    This is metadata-only. Enforcement and execution remain with AEGIS.
    """
    name = (tool_name or "").strip().lower()
    meta = TOOL_REGISTRY.get(name) or {}

    allowed_actions = meta.get("allowed_actions") or []
    if not isinstance(allowed_actions, list):
        allowed_actions = []

    tool_gateway_families = meta.get("tool_gateway_families") or []
    if not isinstance(tool_gateway_families, list):
        tool_gateway_families = []

    return {
        "tool_contract_version": TOOL_CONTRACT_VERSION,
        "tool_name": name,
        "implemented": bool(meta.get("implemented")),
        "status": meta.get("status") or "unknown",
        "category": meta.get("category") or "unknown",
        "tool_family": meta.get("tool_family") or None,
        "external_internal": meta.get("external_internal") or "unknown",
        "sensitivity": meta.get("sensitivity") or "unknown",
        "risk_level": meta.get("risk_level") or "unknown",
        "allowed_actions": allowed_actions,
        "requires_human_review": bool(meta.get("human_review_recommended", True)),
        "tool_gateway_families": tool_gateway_families,
        "allowed_agents": meta.get("allowed_agents") if isinstance(meta.get("allowed_agents"), list) else [],
        "description": meta.get("description") or "",
    }
