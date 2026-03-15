ENGINE_REGISTRY = {
    "planner_engine": {
        "implemented": True,
        "status": "active",
        "layer": "core",
        "category": "planning",
        "owner": "nexus",
        "reusable": True,
        "products": ["jarvis", "paragon", "vector", "epoch", "genesis"],
        "description": "Builds structured implementation plans from project context and user goals.",
    },
    "model_gateway": {
        "implemented": True,
        "status": "active",
        "layer": "core",
        "category": "model_access",
        "owner": "nexus",
        "reusable": True,
        "products": ["jarvis", "paragon", "vector", "epoch", "genesis"],
        "description": "Central interface for calling AI model providers through a unified adapter layer.",
    },
    "memory_loader": {
        "implemented": True,
        "status": "active",
        "layer": "core",
        "category": "memory",
        "owner": "nexus",
        "reusable": True,
        "products": ["jarvis", "paragon", "vector", "epoch", "genesis"],
        "description": "Loads project-scoped docs, memory, and tasks into a normalized context object.",
    },
    "plan_validator": {
        "implemented": True,
        "status": "active",
        "layer": "core",
        "category": "validation",
        "owner": "nexus",
        "reusable": True,
        "products": ["jarvis", "paragon", "vector", "epoch", "genesis"],
        "description": "Validates structured planner output and enforces required fields and safety rules.",
    },
    "agent_router": {
        "implemented": True,
        "status": "active",
        "layer": "core",
        "category": "routing",
        "owner": "nexus",
        "reusable": True,
        "products": ["jarvis", "paragon", "vector", "epoch", "genesis"],
        "description": "Resolves safe next-agent handoff decisions from planner output.",
    },
    "execution_bridge": {
        "implemented": True,
        "status": "active",
        "layer": "core",
        "category": "execution",
        "owner": "nexus",
        "reusable": True,
        "products": ["jarvis", "paragon", "vector", "epoch", "genesis"],
        "description": "Maps internal runtime routing to Cursor/Codex/human execution packets.",
    },
    "file_modification_engine": {
        "implemented": True,
        "status": "active",
        "layer": "core",
        "category": "file_ops",
        "owner": "nexus",
        "reusable": True,
        "products": ["jarvis"],
        "description": "Performs controlled append/update operations on project files.",
    },
    "diff_patch_engine": {
        "implemented": True,
        "status": "active",
        "layer": "core",
        "category": "file_ops",
        "owner": "nexus",
        "reusable": True,
        "products": ["jarvis"],
        "description": "Performs narrowly scoped, approval-gated diff/patch operations.",
    },
    "browser_research_engine": {
        "implemented": True,
        "status": "active",
        "layer": "core",
        "category": "research",
        "owner": "nexus",
        "reusable": True,
        "products": ["jarvis", "paragon", "vector"],
        "description": "Provides safe research URL launch and research reporting support.",
    },
    "terminal_control_engine": {
        "implemented": True,
        "status": "active",
        "layer": "core",
        "category": "execution",
        "owner": "nexus",
        "reusable": True,
        "products": ["jarvis", "paragon", "vector", "epoch", "genesis"],
        "description": "Runs allowlisted terminal commands and records execution results.",
    },

    # Planned engines
    "pricing_engine": {
        "implemented": False,
        "status": "planned",
        "layer": "studio",
        "category": "business",
        "owner": "forge",
        "reusable": True,
        "products": [],
        "description": "Future pricing strategy engine for products and subscription models.",
    },
    "legal_engine": {
        "implemented": False,
        "status": "planned",
        "layer": "studio",
        "category": "legal",
        "owner": "forge",
        "reusable": True,
        "products": [],
        "description": "Future engine for generating product legal docs and compliance templates.",
    },
    "analytics_engine": {
        "implemented": False,
        "status": "planned",
        "layer": "studio",
        "category": "analytics",
        "owner": "forge",
        "reusable": True,
        "products": [],
        "description": "Future engine for product metrics, usage analysis, and performance insights.",
    },
    "growth_engine": {
        "implemented": False,
        "status": "planned",
        "layer": "studio",
        "category": "growth",
        "owner": "forge",
        "reusable": True,
        "products": [],
        "description": "Future engine for SEO, content, and growth automation.",
    },
}


def list_active_engines() -> list[str]:
    return sorted([
        key for key, value in ENGINE_REGISTRY.items()
        if value.get("status") == "active"
    ])


def list_planned_engines() -> list[str]:
    return sorted([
        key for key, value in ENGINE_REGISTRY.items()
        if value.get("status") == "planned"
    ])


def get_engines_for_product(product_name: str | None) -> list[str]:
    if not product_name:
        return []

    lowered = str(product_name).strip().lower()
    results = []

    for engine_name, metadata in ENGINE_REGISTRY.items():
        products = [p.lower() for p in metadata.get("products", [])]
        if lowered in products:
            results.append(engine_name)

    return sorted(results)