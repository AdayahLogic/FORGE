"""
Runtime agent registry for NEXUS routing and node resolution.

Routing and runtime_node names stay here. For agent display names and
identity metadata (role, status, allowed_tools), see agent_identity_registry.
"""
RUNTIME_AGENT_REGISTRY = {
    "planner": {
        "implemented": True,
        "routable": False,
        "runtime_node": "architect",
        "description": "Structured planning and architecture generation.",
    },
    "coder": {
        "implemented": True,
        "routable": True,
        "runtime_node": "coder",
        "description": "Primary implementation and code-writing agent.",
    },
    "tester": {
        "implemented": True,
        "routable": True,
        "runtime_node": "tester",
        "description": "Validation and testing agent.",
    },
    "docs": {
        "implemented": True,
        "routable": True,
        "runtime_node": "docs",
        "description": "Documentation and knowledge output agent.",
    },
    "executor": {
        "implemented": True,
        "routable": False,
        "runtime_node": "executor",
        "description": "Safe command execution agent.",
    },
    "workspace": {
        "implemented": True,
        "routable": False,
        "runtime_node": "workspace",
        "description": "Workspace scanning and intelligence agent.",
    },
    "operator": {
        "implemented": True,
        "routable": False,
        "runtime_node": "operator",
        "description": "Structured internal tool/operator agent.",
    },
    "supervisor": {
        "implemented": True,
        "routable": False,
        "runtime_node": "supervisor",
        "description": "Project-level supervisor agent.",
    },
    "studio_supervisor": {
        "implemented": True,
        "routable": False,
        "runtime_node": "studio_supervisor",
        "description": "Studio-wide summary and prioritization agent.",
    },
    "autonomous_cycle": {
        "implemented": True,
        "routable": False,
        "runtime_node": "autonomous_cycle",
        "description": "Bounded autonomous cycle management agent.",
    },
    "computer_use": {
        "implemented": True,
        "routable": False,
        "runtime_node": "computer_use",
        "description": "Controlled computer-use foundation agent.",
    },
    "tool_execution": {
        "implemented": True,
        "routable": False,
        "runtime_node": "tool_execution",
        "description": "Structured tool execution agent.",
    },
    "terminal": {
        "implemented": True,
        "routable": False,
        "runtime_node": "terminal",
        "description": "Allowlisted terminal execution agent.",
    },
    "browser_research": {
        "implemented": True,
        "routable": False,
        "runtime_node": "browser_research",
        "description": "Safe browser research agent.",
    },
    "file_modification": {
        "implemented": True,
        "routable": False,
        "runtime_node": "file_modification",
        "description": "Controlled append/update file modification agent.",
    },
    "diff_patch": {
        "implemented": True,
        "routable": False,
        "runtime_node": "diff_patch",
        "description": "Controlled diff/patch editing agent.",
    },
    "full_automation": {
        "implemented": True,
        "routable": False,
        "runtime_node": "full_automation",
        "description": "Combined automation summary agent.",
    },
}

FUTURE_AGENT_REGISTRY = {
    "architect": {
        "implemented": False,
        "routable": False,
        "mapped_runtime_agent": "planner",
        "description": "Conceptual architecture role; currently handled by planner.",
    },
    "builder": {
        "implemented": False,
        "routable": False,
        "mapped_runtime_agent": "coder",
        "description": "Conceptual builder role; currently handled by coder.",
    },
    "inspector": {
        "implemented": False,
        "routable": False,
        "mapped_runtime_agent": "tester",
        "description": "Conceptual testing role; currently handled by tester.",
    },
    "scribe": {
        "implemented": False,
        "routable": False,
        "mapped_runtime_agent": "docs",
        "description": "Conceptual docs role; currently handled by docs.",
    },
    "surgeon": {
        "implemented": False,
        "routable": False,
        "mapped_runtime_agent": None,
        "description": "Planned debugging and repair specialist.",
    },
    "helix": {
        "implemented": False,
        "routable": False,
        "mapped_runtime_agent": None,
        "description": "Planned senior engineering and systems intelligence agent.",
    },
    "prism": {
        "implemented": False,
        "routable": False,
        "mapped_runtime_agent": None,
        "description": "Planned marketing, media, and creative execution agent.",
    },
}

AGENT_ALIASES = {
    "planner": "planner",
    "architect": "planner",
    "builder": "coder",
    "coder": "coder",
    "tester": "tester",
    "inspector": "tester",
    "scribe": "docs",
    "docs": "docs",
    "surgeon": "surgeon",
    "helix": "helix",
    "prism": "prism",
}


def get_runtime_routable_agents() -> list[str]:
    return sorted([
        key for key, value in RUNTIME_AGENT_REGISTRY.items()
        if value.get("routable", False)
    ])


def resolve_agent_alias(agent_name: str | None) -> str | None:
    if not agent_name:
        return None

    lowered = str(agent_name).strip().lower()
    return AGENT_ALIASES.get(lowered, lowered)