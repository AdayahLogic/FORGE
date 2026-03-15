"""
Nexus core workspace layer definitions.

Defines logical layers (core, projects, shared, docs, generated, state, etc.)
with write policy and owner scope for boundary checks. No path migration;
inspection and classification only.
"""

from __future__ import annotations

from typing import Any

# write_policy: allowed | restricted | review_required
# owner_scope: nexus | project | shared | runtime
LAYER_REGISTRY: dict[str, dict[str, Any]] = {
    "core": {
        "description": "NEXUS core code and config under core/.",
        "write_policy": "restricted",
        "owner_scope": "nexus",
    },
    "projects": {
        "description": "Project root under projects/.",
        "write_policy": "allowed",
        "owner_scope": "project",
    },
    "shared": {
        "description": "Shared studio resources under shared/.",
        "write_policy": "review_required",
        "owner_scope": "shared",
    },
    "docs": {
        "description": "Documentation (studio-level or project docs/).",
        "write_policy": "review_required",
        "owner_scope": "nexus",  # overridden to project when path is under projects/X/docs
    },
    "generated": {
        "description": "Generated outputs under project generated/.",
        "write_policy": "allowed",
        "owner_scope": "runtime",
    },
    "state": {
        "description": "Persisted state under project state/.",
        "write_policy": "allowed",
        "owner_scope": "runtime",
    },
    "memory": {
        "description": "Project memory under project memory/.",
        "write_policy": "allowed",
        "owner_scope": "project",
    },
    "tasks": {
        "description": "Project tasks under project tasks/.",
        "write_policy": "allowed",
        "owner_scope": "project",
    },
    "unknown": {
        "description": "Path could not be classified or is outside known layers.",
        "write_policy": "restricted",
        "owner_scope": "nexus",
    },
}
