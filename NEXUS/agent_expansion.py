"""
NEXUS agent expansion layer.

Lightweight agent profile expansion and selection summary building.
Normalizes role/specialty/action metadata for routing outputs. No side effects.
"""

from __future__ import annotations

from typing import Any

# Lightweight role mapping (align with agent_identity_registry roles where present)
AGENT_ROLE_MAP: dict[str, str] = {
    "coder": "implementation",
    "docs": "documentation",
    "tester": "testing",
    "architect": "architecture",
    "planner": "architecture",
    "executor": "execution",
    "workspace": "workspace",
    "operator": "automation",
    "supervisor": "governance",
}

# Role -> specialties (small, sensible; includes agent_identity_registry roles)
ROLE_SPECIALTIES: dict[str, list[str]] = {
    "implementation": ["code_changes", "refactoring", "patch_generation"],
    "documentation": ["docs_updates", "summaries", "writeups"],
    "testing": ["validation", "test_generation", "verification"],
    "validation": ["validation", "test_generation", "verification"],
    "architecture": ["planning", "design", "structure_review"],
    "planning": ["planning", "design", "structure_review"],
    "execution": ["command_execution", "safe_commands"],
    "workspace": ["scanning", "intelligence"],
    "automation": ["tool_sequence", "operator_actions"],
    "governance": ["review", "decision"],
    "senior_engineering": ["design", "review", "architecture"],
    "debugging": ["repair", "diagnosis", "patch_generation"],
    "marketing_creative": ["writeups", "summaries"],
}

# Role -> allowed_actions (compact)
ROLE_ALLOWED_ACTIONS: dict[str, list[str]] = {
    "implementation": ["code_changes", "refactoring", "patch_generation"],
    "documentation": ["docs_updates", "summaries", "writeups"],
    "testing": ["validation", "test_generation", "verification"],
    "validation": ["validation", "test_generation", "verification"],
    "architecture": ["planning", "design", "structure_review"],
    "planning": ["planning", "design", "structure_review"],
    "execution": ["run_commands", "report_results"],
    "workspace": ["scan", "report"],
    "automation": ["run_tools", "record_actions"],
    "governance": ["review", "recommend"],
    "senior_engineering": ["design", "review", "recommend"],
    "debugging": ["repair", "diagnose", "patch_generation"],
    "marketing_creative": ["writeups", "summaries"],
}


def build_agent_profile(
    *,
    selected_agent: str | None = None,
    runtime_node: str | None = None,
    task_type: str | None = None,
    request_type: str | None = None,
    request_summary: str | None = None,
    routing_summary: dict | None = None,
    agent_identity_data: dict | None = None,
    agent_policy_data: dict | None = None,
    capability_data: dict | None = None,
) -> dict[str, Any]:
    """
    Build normalized agent profile from optional inputs.

    Returns: agent_name, agent_role, specialties, allowed_actions,
    selection_reason, confidence. Tolerates missing data.
    """
    node = (selected_agent or runtime_node or "").strip().lower()
    routing = routing_summary or {}
    if not node and routing.get("runtime_node"):
        node = (routing.get("runtime_node") or "").strip().lower()
    if not node:
        node = "coder"

    role = (agent_identity_data or {}).get("role") if agent_identity_data else None
    if not role:
        role = AGENT_ROLE_MAP.get(node, "implementation")

    specialties = list(ROLE_SPECIALTIES.get(role, []))
    allowed_actions = list(ROLE_ALLOWED_ACTIONS.get(role, []))

    route_reason = routing.get("route_reason") or "Agent selected by router."
    route_status = (routing.get("route_status") or "").strip().lower()
    if route_status == "direct_runtime_route":
        confidence = "high"
    elif route_status in ("future_agent_mapped", "non_routable_runtime_agent"):
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "agent_name": node,
        "agent_role": role,
        "specialties": specialties,
        "allowed_actions": allowed_actions,
        "selection_reason": route_reason,
        "confidence": confidence,
    }


def build_agent_profile_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises; returns minimal profile on exception."""
    try:
        return build_agent_profile(**kwargs)
    except Exception:
        return {
            "agent_name": "coder",
            "agent_role": "implementation",
            "specialties": [],
            "allowed_actions": [],
            "selection_reason": "Agent expansion failed; using default profile.",
            "confidence": "low",
        }


def build_agent_selection_summary(
    *,
    selected_agent: str | None = None,
    runtime_node: str | None = None,
    routing_summary: dict | None = None,
    agent_profile: dict | None = None,
) -> dict[str, Any]:
    """
    Build compact agent selection summary for persistence and visibility.

    Uses agent_profile if provided; otherwise builds profile from selected_agent/runtime_node/routing_summary.
    """
    profile = agent_profile
    if not profile or not isinstance(profile, dict):
        profile = build_agent_profile_safe(
            selected_agent=selected_agent,
            runtime_node=runtime_node,
            routing_summary=routing_summary,
        )
    return {
        "selected_agent": profile.get("agent_name", ""),
        "agent_role": profile.get("agent_role", ""),
        "selection_reason": profile.get("selection_reason", ""),
        "confidence": profile.get("confidence", "low"),
        "specialties": list(profile.get("specialties", [])),
    }
