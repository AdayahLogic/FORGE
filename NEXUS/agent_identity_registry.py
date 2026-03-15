"""
NEXUS agent identity registry.

Single source of truth for agent identity: canonical name, display name,
role, status, and metadata. Used for display consistency in reports and
routing summaries. Runtime routing and node names remain in agent_registry.
"""

from __future__ import annotations

from typing import Any

# status: active | planned
# runtime_type: routable_node | internal_node | planned
AGENT_IDENTITY_REGISTRY: dict[str, dict[str, Any]] = {
    "coder": {
        "canonical_name": "coder",
        "display_name": "Coder",
        "role": "implementation",
        "status": "active",
        "runtime_type": "routable_node",
        "allowed_tools": ["cursor_agent", "codex"],
        "owned_capabilities": [],
        "fallback_to": None,
        "description": "Primary implementation and code-writing agent.",
    },
    "tester": {
        "canonical_name": "tester",
        "display_name": "Tester",
        "role": "validation",
        "status": "active",
        "runtime_type": "routable_node",
        "allowed_tools": ["cursor_terminal", "codex"],
        "owned_capabilities": [],
        "fallback_to": None,
        "description": "Validation and testing agent.",
    },
    "docs": {
        "canonical_name": "docs",
        "display_name": "Docs",
        "role": "documentation",
        "status": "active",
        "runtime_type": "routable_node",
        "allowed_tools": ["cursor_agent", "codex"],
        "owned_capabilities": [],
        "fallback_to": None,
        "description": "Documentation and knowledge output agent.",
    },
    "architect": {
        "canonical_name": "architect",
        "display_name": "Architect",
        "role": "planning",
        "status": "planned",
        "runtime_type": "planned",
        "allowed_tools": [],
        "owned_capabilities": [],
        "fallback_to": "planner",
        "description": "Conceptual architecture role; currently handled by planner.",
    },
    "helix": {
        "canonical_name": "helix",
        "display_name": "Helix",
        "role": "senior_engineering",
        "status": "planned",
        "runtime_type": "planned",
        "allowed_tools": [],
        "owned_capabilities": [],
        "fallback_to": None,
        "description": "Planned senior engineering and systems intelligence agent.",
    },
    "surgeon": {
        "canonical_name": "surgeon",
        "display_name": "Surgeon",
        "role": "debugging",
        "status": "planned",
        "runtime_type": "planned",
        "allowed_tools": [],
        "owned_capabilities": [],
        "fallback_to": None,
        "description": "Planned debugging and repair specialist.",
    },
    "prism": {
        "canonical_name": "prism",
        "display_name": "Prism",
        "role": "marketing_creative",
        "status": "planned",
        "runtime_type": "planned",
        "allowed_tools": [],
        "owned_capabilities": [],
        "fallback_to": None,
        "description": "Planned marketing, media, and creative execution agent.",
    },
}


def get_agent_display_name(canonical_name: str | None) -> str | None:
    """Return display name for a canonical agent key, or None if unknown."""
    if not canonical_name:
        return None
    entry = AGENT_IDENTITY_REGISTRY.get((canonical_name or "").strip().lower())
    return entry.get("display_name") if entry else None


def get_agent_status(canonical_name: str | None) -> str | None:
    """Return status (active | planned) for a canonical agent key, or None if unknown."""
    if not canonical_name:
        return None
    entry = AGENT_IDENTITY_REGISTRY.get((canonical_name or "").strip().lower())
    return entry.get("status") if entry else None


def get_active_agent_canonical_names() -> list[str]:
    """Return canonical names of agents marked active."""
    return sorted(
        k for k, v in AGENT_IDENTITY_REGISTRY.items()
        if v.get("status") == "active"
    )


def get_planned_agent_canonical_names() -> list[str]:
    """Return canonical names of agents marked planned."""
    return sorted(
        k for k, v in AGENT_IDENTITY_REGISTRY.items()
        if v.get("status") == "planned"
    )
