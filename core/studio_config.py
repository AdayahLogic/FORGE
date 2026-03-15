from pathlib import Path
import os


def _resolve_studio_root() -> Path:
    """
    Resolve the current studio root safely.

    Priority:
    1. FORGE_ROOT env var
    2. AI_STUDIO_ROOT env var
    3. Parent directory of this file's folder
       (works for current layout: C:\\AI_STUDIO\\core\\studio_config.py)
    """
    forge_root = os.getenv("FORGE_ROOT")
    if forge_root:
        return Path(forge_root).resolve()

    legacy_root = os.getenv("AI_STUDIO_ROOT")
    if legacy_root:
        return Path(legacy_root).resolve()

    return Path(__file__).resolve().parent.parent


STUDIO_ROOT = _resolve_studio_root()
CORE_DIR = STUDIO_ROOT / "core"
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

# Current logical product rename map
# IMPORTANT:
# - physical folders do NOT change yet
# - logical names can change immediately
LOGICAL_PROJECT_NAMES = {
    "jarvis": "Jarvis",
    "paragon": "Paragon",
    "vector": "Vector",
    "epoch": "Epoch",
    "genesis": "Genesis",
    "game_dev": "Game Dev",
    "rpg_project": "RPG Project",
}

# Old names / aliases that should still route correctly during transition
PROJECT_ALIASES = {
    "jarvis": {"jarvis", "nexus"},
    "paragon": {"paragon", "negotiateai"},
    "vector": {"vector", "blofin-bot", "blofin", "trading bot", "trading_system", "trading systems"},
    "epoch": {"epoch"},
    "genesis": {"genesis"},
    "game_dev": {"game_dev", "game dev"},
    "rpg_project": {"rpg_project", "rpg", "rpg project"},
}

# Physical folder mapping
# IMPORTANT:
# The key is the logical project key.
# The value is the CURRENT physical folder name on disk.
PROJECT_FOLDER_MAP = {
    "jarvis": "nexus",
    "paragon": "negotiateai",
    "vector": "vector",   # change later if/when you create or rename the folder
    "epoch": "epoch",
    "genesis": "genesis",
    "game_dev": "game_dev",
    "rpg_project": "rpg_project",
}