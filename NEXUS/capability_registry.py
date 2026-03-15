CAPABILITY_REGISTRY = {
    "project_context_loading": {
        "implemented": True,
        "status": "active",
        "layer": "NEXUS",
        "owner": "nexus",
        "engine": "memory_loader",
        "category": "context",
        "reusable": True,
        "projects": ["jarvis", "paragon", "vector", "epoch", "genesis"],
        "description": "Load project-scoped docs, focus, memory, and task inputs into a normalized context object.",
    },
    "structured_planning": {
        "implemented": True,
        "status": "active",
        "layer": "NEXUS",
        "owner": "nexus",
        "engine": "planner_engine",
        "category": "planning",
        "reusable": True,
        "projects": ["jarvis", "paragon", "vector", "epoch", "genesis"],
        "description": "Generate structured implementation plans from user goals and project context.",
    },
    "plan_validation": {
        "implemented": True,
        "status": "active",
        "layer": "NEXUS",
        "owner": "nexus",
        "engine": "plan_validator",
        "category": "validation",
        "reusable": True,
        "projects": ["jarvis", "paragon", "vector", "epoch", "genesis"],
        "description": "Validate planner output, enforce schema, and normalize unsafe or incomplete plans.",
    },
    "planner_retry_recovery": {
        "implemented": True,
        "status": "active",
        "layer": "NEXUS",
        "owner": "nexus",
        "engine": "planner_engine",
        "category": "reliability",
        "reusable": True,
        "projects": ["jarvis", "paragon", "vector", "epoch", "genesis"],
        "description": "Retry planner generation when parsing or validation fails, then fall back safely if needed.",
    },
    "agent_handoff_routing": {
        "implemented": True,
        "status": "active",
        "layer": "NEXUS",
        "owner": "nexus",
        "engine": "agent_router",
        "category": "routing",
        "reusable": True,
        "projects": ["jarvis", "paragon", "vector", "epoch", "genesis"],
        "description": "Resolve the next safe runtime agent based on planner output.",
    },
    "cursor_codex_handoff_packets": {
        "implemented": True,
        "status": "active",
        "layer": "NEXUS",
        "owner": "nexus",
        "engine": "execution_bridge",
        "category": "execution",
        "reusable": True,
        "projects": ["jarvis", "paragon", "vector", "epoch", "genesis"],
        "description": "Generate structured Cursor/Codex/human handoff packets for external execution workflows.",
    },
    "allowlisted_terminal_execution": {
        "implemented": True,
        "status": "active",
        "layer": "NEXUS",
        "owner": "nexus",
        "engine": "terminal_control_engine",
        "category": "execution",
        "reusable": True,
        "projects": ["jarvis", "paragon", "vector", "epoch", "genesis"],
        "description": "Run allowlisted terminal commands and capture results safely.",
    },
    "browser_research_launch": {
        "implemented": True,
        "status": "active",
        "layer": "NEXUS",
        "owner": "nexus",
        "engine": "browser_research_engine",
        "category": "research",
        "reusable": True,
        "projects": ["jarvis", "paragon", "vector"],
        "description": "Launch safe research URLs and create research reports.",
    },
    "controlled_file_append_updates": {
        "implemented": True,
        "status": "active",
        "layer": "NEXUS",
        "owner": "nexus",
        "engine": "file_modification_engine",
        "category": "file_ops",
        "reusable": True,
        "projects": ["jarvis"],
        "description": "Apply safe append-style controlled updates to project files.",
    },
    "safe_diff_patch_editing": {
        "implemented": True,
        "status": "active",
        "layer": "NEXUS",
        "owner": "nexus",
        "engine": "diff_patch_engine",
        "category": "file_ops",
        "reusable": True,
        "projects": ["jarvis"],
        "description": "Apply narrow diff/patch updates with approval-style safety checks.",
    },
    "bounded_autonomous_cycles": {
        "implemented": True,
        "status": "active",
        "layer": "NEXUS",
        "owner": "nexus",
        "engine": "planner_engine",
        "category": "safety",
        "reusable": True,
        "projects": ["jarvis", "paragon", "vector", "epoch", "genesis"],
        "description": "Stop automation after a bounded number of cycles to prevent runaway execution.",
    },

    # Planned capabilities
    "multi_provider_model_routing": {
        "implemented": False,
        "status": "planned",
        "layer": "NEXUS",
        "owner": "nexus",
        "engine": "model_gateway",
        "category": "model_access",
        "reusable": True,
        "projects": ["jarvis", "paragon", "vector", "epoch", "genesis"],
        "description": "Route requests across multiple AI providers like OpenAI, Anthropic, and local models.",
    },
    "pricing_strategy_generation": {
        "implemented": False,
        "status": "planned",
        "layer": "studio",
        "owner": "forge",
        "engine": "pricing_engine",
        "category": "business",
        "reusable": True,
        "projects": [],
        "description": "Generate pricing strategies and subscription recommendations for products.",
    },
    "legal_doc_generation": {
        "implemented": False,
        "status": "planned",
        "layer": "studio",
        "owner": "forge",
        "engine": "legal_engine",
        "category": "legal",
        "reusable": True,
        "projects": [],
        "description": "Generate legal templates such as Terms, Privacy Policy, and AI disclaimers.",
    },
    "growth_content_generation": {
        "implemented": False,
        "status": "planned",
        "layer": "studio",
        "owner": "forge",
        "engine": "growth_engine",
        "category": "growth",
        "reusable": True,
        "projects": [],
        "description": "Generate SEO, content, and growth-support materials for product launches.",
    },
}


def list_active_capabilities() -> list[str]:
    return sorted([
        key for key, value in CAPABILITY_REGISTRY.items()
        if value.get("status") == "active"
    ])


def list_planned_capabilities() -> list[str]:
    return sorted([
        key for key, value in CAPABILITY_REGISTRY.items()
        if value.get("status") == "planned"
    ])


def get_capabilities_for_product(product_name: str | None) -> list[str]:
    if not product_name:
        return []

    lowered = str(product_name).strip().lower()
    results = []

    for capability_name, metadata in CAPABILITY_REGISTRY.items():
        products = [p.lower() for p in metadata.get("projects", [])]
        if lowered in products:
            results.append(capability_name)

    return sorted(results)