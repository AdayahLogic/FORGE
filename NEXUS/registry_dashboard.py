"""
NEXUS registry dashboard summary layer.

Aggregates project, agent, policy, tool, engine, and capability registry
status into one normalized studio snapshot. Read-only; no UI, no async.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from NEXUS.registry import PROJECTS
from NEXUS.agent_identity_registry import (
    get_active_agent_canonical_names,
    get_planned_agent_canonical_names,
)
from NEXUS.agent_policy_registry import AGENT_POLICY_REGISTRY
from NEXUS.agent_registry import get_runtime_routable_agents
from NEXUS.tool_registry import list_active_tools, list_planned_tools
from NEXUS.engine_registry import list_active_engines, list_planned_engines
from NEXUS.capability_registry import list_active_capabilities, list_planned_capabilities
from NEXUS.runtime_target_registry import get_runtime_target_summary
from NEXUS.runtime_target_selector import get_selection_defaults_summary
from NEXUS.project_state import load_project_state


STUDIO_NAME = "NEXUS"


def build_registry_dashboard_summary() -> dict[str, Any]:
    """
    Build a unified registry summary for the studio.

    Returns a normalized snapshot with summary_generated_at, studio_name,
    project_summary, agent_summary, tool_summary, engine_summary,
    capability_summary, policy_summary. Each section has counts and name lists.
    """
    now = datetime.now().isoformat()

    # Projects: registry has no active/planned; use total and names
    project_keys = list(PROJECTS.keys())
    project_names = [PROJECTS[k].get("name") or k for k in project_keys]
    project_summary: dict[str, Any] = {
        "total": len(project_keys),
        "names": project_keys,
        "display_names": project_names,
    }

    # Agents: active / planned from identity registry; routable from agent_registry
    active_agents = get_active_agent_canonical_names()
    planned_agents = get_planned_agent_canonical_names()
    routable_agents = get_runtime_routable_agents()
    agent_summary: dict[str, Any] = {
        "active_count": len(active_agents),
        "planned_count": len(planned_agents),
        "active_names": active_agents,
        "planned_names": planned_agents,
        "routable_names": routable_agents,
        "routable_count": len(routable_agents),
    }

    # Policy: agents with policy entries; optional active/planned from policy_status
    policy_agents = list(AGENT_POLICY_REGISTRY.keys())
    policy_active = [a for a in policy_agents if AGENT_POLICY_REGISTRY.get(a, {}).get("policy_status") == "active"]
    policy_planned = [a for a in policy_agents if AGENT_POLICY_REGISTRY.get(a, {}).get("policy_status") == "planned"]
    policy_summary: dict[str, Any] = {
        "agents_with_policy_count": len(policy_agents),
        "agents_with_policy": policy_agents,
        "policy_active_count": len(policy_active),
        "policy_planned_count": len(policy_planned),
        "policy_active_names": policy_active,
        "policy_planned_names": policy_planned,
    }

    # Tools
    tools_active = list_active_tools()
    tools_planned = list_planned_tools()
    tool_summary: dict[str, Any] = {
        "active_count": len(tools_active),
        "planned_count": len(tools_planned),
        "active_names": tools_active,
        "planned_names": tools_planned,
    }

    # Engines
    engines_active = list_active_engines()
    engines_planned = list_planned_engines()
    engine_summary: dict[str, Any] = {
        "active_count": len(engines_active),
        "planned_count": len(engines_planned),
        "active_names": engines_active,
        "planned_names": engines_planned,
    }

    # Capabilities
    caps_active = list_active_capabilities()
    caps_planned = list_planned_capabilities()
    capability_summary: dict[str, Any] = {
        "active_count": len(caps_active),
        "planned_count": len(caps_planned),
        "active_names": caps_active,
        "planned_names": caps_planned,
    }

    # Runtime targets: active / planned
    runtime_target_summary = get_runtime_target_summary()
    # Selection defaults (target mappings)
    runtime_selection_defaults = get_selection_defaults_summary()

    # Dispatch planning: per-project from persisted state
    dispatch_by_project: dict[str, dict[str, Any]] = {}
    ready_count = 0
    dispatch_status_by_project: dict[str, str] = {}
    dispatch_status_count: dict[str, int] = {}
    for key in project_keys:
        path = PROJECTS[key].get("path")
        if not path:
            continue
        try:
            loaded = load_project_state(path)
            if "load_error" in loaded:
                continue
            dps = loaded.get("dispatch_plan_summary") or {}
            dispatch_by_project[key] = {
                "dispatch_planning_status": dps.get("dispatch_planning_status"),
                "ready_for_dispatch": dps.get("ready_for_dispatch", False),
                "runtime_target_id": dps.get("runtime_target_id"),
                "runtime_node": dps.get("runtime_node"),
                "task_type": dps.get("task_type"),
            }
            if dps.get("ready_for_dispatch"):
                ready_count += 1
            ds = loaded.get("dispatch_status") or "none"
            dispatch_status_by_project[key] = ds
            dispatch_status_count[ds] = dispatch_status_count.get(ds, 0) + 1
        except Exception:
            continue
    dispatch_planning_summary: dict[str, Any] = {
        "dispatch_planning_status": "planned" if dispatch_by_project else "no_data",
        "ready_for_dispatch_count": ready_count,
        "by_project": dispatch_by_project,
    }

    execution_status_by_project: dict[str, str] = {}
    execution_status_count: dict[str, int] = {}
    for k, ds in dispatch_status_by_project.items():
        # Read from already-loaded state where available (by reloading would be overkill here)
        # Use persisted runtime_execution_status if present; otherwise leave as unknown.
        try:
            path = PROJECTS[k].get("path")
            loaded = load_project_state(path) if path else {}
            exec_status = loaded.get("runtime_execution_status") or (loaded.get("dispatch_result") or {}).get("execution_status") or "unknown"
        except Exception:
            exec_status = "unknown"
        execution_status_by_project[k] = exec_status
        execution_status_count[exec_status] = execution_status_count.get(exec_status, 0) + 1

    return {
        "summary_generated_at": now,
        "studio_name": STUDIO_NAME,
        "project_summary": project_summary,
        "agent_summary": agent_summary,
        "policy_summary": policy_summary,
        "tool_summary": tool_summary,
        "engine_summary": engine_summary,
        "capability_summary": capability_summary,
        "runtime_target_summary": runtime_target_summary,
        "runtime_selection_defaults": runtime_selection_defaults,
        "dispatch_planning_summary": dispatch_planning_summary,
        "dispatch_status_count": dispatch_status_count,
        "dispatch_status_by_project": dispatch_status_by_project,
        "execution_status_by_project": execution_status_by_project,
        "execution_status_count": execution_status_count,
    }
