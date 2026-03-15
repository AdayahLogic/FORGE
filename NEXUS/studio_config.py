from pathlib import Path
import os


def _resolve_studio_root() -> Path:
    """
    Resolve the current studio root safely.

    Priority:
    1. FORGE_ROOT env var
    2. AI_STUDIO_ROOT env var
    3. Parent directory of this file's folder
       (works for current layout: C:\\AI_STUDIO\\NEXUS\\studio_config.py)
    """
    forge_root = os.getenv("FORGE_ROOT")
    if forge_root:
        return Path(forge_root).resolve()

    legacy_root = os.getenv("AI_STUDIO_ROOT")
    if legacy_root:
        return Path(legacy_root).resolve()

    return Path(__file__).resolve().parent.parent


STUDIO_ROOT = _resolve_studio_root()
NEXUS_DIR = STUDIO_ROOT / "NEXUS"
# Legacy: core/ was renamed to NEXUS/; keep for path resolution of legacy paths
CORE_DIR = STUDIO_ROOT / "NEXUS"
PROJECTS_DIR = STUDIO_ROOT / "projects"
LOGS_DIR = STUDIO_ROOT / "logs"
DOCS_DIR = STUDIO_ROOT / "docs"
CONFIG_DIR = STUDIO_ROOT / "config"
SCRIPTS_DIR = STUDIO_ROOT / "scripts"
SHARED_DIR = STUDIO_ROOT / "shared"

# Logical names
STUDIO_NAME = "FORGE"
CORE_SYSTEM_NAME = "NEXUS"

# Optional legacy display name for transition messaging
LEGACY_STUDIO_FOLDER_NAME = "AI_STUDIO"

# Project identity: single source of truth in NEXUS.project_identity_registry.
# Below built from it for backward compatibility with existing imports.
from NEXUS.project_identity_registry import PROJECT_IDENTITY_REGISTRY

LOGICAL_PROJECT_NAMES = {
    k: v["display_name"] for k, v in PROJECT_IDENTITY_REGISTRY.items()
}

PROJECT_ALIASES = {
    k: set(v["aliases"]) for k, v in PROJECT_IDENTITY_REGISTRY.items()
}

PROJECT_FOLDER_MAP = {
    k: v["folder_name"] for k, v in PROJECT_IDENTITY_REGISTRY.items()
}