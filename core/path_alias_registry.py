"""
Nexus core path alias and migration mapping registry.

Maps legacy path names to intended logical names for transition.
No physical renames in this module; reporting and translation only.
"""

from __future__ import annotations

from typing import Any

# logical_role: studio_root | project_path | project_folder
# migration_status: alias_only | physical_unchanged | pending_rename | migrated
PATH_ALIAS_REGISTRY: list[dict[str, Any]] = [
    {
        "legacy_name": "AI_STUDIO",
        "current_name": "FORGE",
        "logical_role": "studio_root",
        "migration_status": "alias_only",
        "notes": "Legacy root folder name; FORGE is the intended name. Physical rename deferred.",
    },
    {
        "legacy_name": "projects/nexus",
        "current_name": "projects/nexus",
        "logical_role": "project_path",
        "migration_status": "physical_unchanged",
        "notes": "Physical path for logical project jarvis. Folder still named nexus.",
    },
    {
        "legacy_name": "nexus",
        "current_name": "jarvis",
        "logical_role": "project_folder",
        "migration_status": "physical_unchanged",
        "notes": "Logical project jarvis is served by physical folder nexus. Rename when safe.",
    },
]

# Intended root display name for reports and UI
INTENDED_ROOT_NAME = "FORGE"

# Legacy root name for detection in path strings
LEGACY_ROOT_NAMES = ("AI_STUDIO", "AI-STUDIO")

# Legacy project path segments that indicate alias (physical folder name)
LEGACY_PROJECT_PATH_SEGMENTS = ("nexus",)
