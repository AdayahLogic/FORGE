"""
NEXUS project identity registry.

Single source of truth for managed project identity: canonical name,
display name, physical folder, aliases, and metadata. Used by studio_config,
path_utils, and reporting so identity is consistent across routing,
paths, and display.
"""

from __future__ import annotations

from typing import Any

# status: active | planned | deprecated
# project_type: internal | external
# orchestrated_by: NEXUS (orchestrator), not a project key
PROJECT_IDENTITY_REGISTRY: dict[str, dict[str, Any]] = {
    "jarvis": {
        "canonical_name": "jarvis",
        "display_name": "Jarvis",
        "folder_name": "jarvis",
        "aliases": frozenset({"jarvis", "nexus"}),
        "status": "active",
        "project_type": "internal",
        "orchestrated_by": "nexus",
    },
    "paragon": {
        "canonical_name": "paragon",
        "display_name": "Paragon",
        "folder_name": "negotiateai",
        "aliases": frozenset({"paragon", "negotiateai"}),
        "status": "active",
        "project_type": "internal",
        "orchestrated_by": "nexus",
    },
    "vector": {
        "canonical_name": "vector",
        "display_name": "Vector",
        "folder_name": "vector",
        "aliases": frozenset({"vector", "blofin-bot", "blofin", "trading bot", "trading_system", "trading systems"}),
        "status": "active",
        "project_type": "internal",
        "orchestrated_by": "nexus",
    },
    "epoch": {
        "canonical_name": "epoch",
        "display_name": "Epoch",
        "folder_name": "epoch",
        "aliases": frozenset({"epoch"}),
        "status": "active",
        "project_type": "internal",
        "orchestrated_by": "nexus",
    },
    "genesis": {
        "canonical_name": "genesis",
        "display_name": "Genesis",
        "folder_name": "genesis",
        "aliases": frozenset({"genesis"}),
        "status": "active",
        "project_type": "internal",
        "orchestrated_by": "nexus",
    },
    "game_dev": {
        "canonical_name": "game_dev",
        "display_name": "Game Dev",
        "folder_name": "game_dev",
        "aliases": frozenset({"game_dev", "game dev"}),
        "status": "active",
        "project_type": "internal",
        "orchestrated_by": "nexus",
    },
    "rpg_project": {
        "canonical_name": "rpg_project",
        "display_name": "RPG Project",
        "folder_name": "rpg_project",
        "aliases": frozenset({"rpg_project", "rpg", "rpg project"}),
        "status": "active",
        "project_type": "internal",
        "orchestrated_by": "nexus",
    },
}


def get_display_name(canonical_name: str | None) -> str | None:
    """Return display name for a canonical project key, or None if unknown."""
    if not canonical_name:
        return None
    entry = PROJECT_IDENTITY_REGISTRY.get(canonical_name.strip().lower())
    return entry.get("display_name") if entry else None


def get_folder_name(canonical_name: str | None) -> str | None:
    """Return physical folder name for a canonical project key, or None if unknown."""
    if not canonical_name:
        return None
    entry = PROJECT_IDENTITY_REGISTRY.get(canonical_name.strip().lower())
    return entry.get("folder_name") if entry else None


def get_aliases(canonical_name: str | None) -> frozenset[str]:
    """Return aliases for a canonical project key; empty if unknown."""
    if not canonical_name:
        return frozenset()
    entry = PROJECT_IDENTITY_REGISTRY.get(canonical_name.strip().lower())
    return entry.get("aliases", frozenset()) if entry else frozenset()


def get_all_canonical_names() -> list[str]:
    """Return all canonical project keys in registry order."""
    return list(PROJECT_IDENTITY_REGISTRY.keys())
