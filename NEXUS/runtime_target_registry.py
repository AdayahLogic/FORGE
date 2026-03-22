"""
NEXUS runtime target registry.

Models where work can run: local, cursor, codex, container/remote/cloud workers.
Read-only registry; no actual dispatching or implementation in this step.
"""

from __future__ import annotations

from typing import Any

RUNTIME_TARGET_REGISTRY: dict[str, dict[str, Any]] = {
    "local": {
        "canonical_name": "local",
        "display_name": "Local",
        "status": "active",
        "runtime_type": "local",
        "active_or_planned": "active",
        "capabilities": ["execute", "file_ops", "terminal", "planning"],
        "approval_level": "auto",
        "description": "Local process execution; default in-process runtime.",
    },
    "cursor": {
        "canonical_name": "cursor",
        "display_name": "Cursor",
        "status": "active",
        "runtime_type": "ide",
        "active_or_planned": "active",
        "capabilities": ["execute", "file_ops", "terminal", "planning", "agent_routing"],
        "approval_level": "human_review",
        "description": "Cursor IDE as execution target; agent and tool execution via Cursor.",
    },
    "codex": {
        "canonical_name": "codex",
        "display_name": "Codex",
        "status": "active",
        "runtime_type": "ide",
        "active_or_planned": "active",
        "capabilities": ["execute", "file_ops", "terminal", "planning", "agent_routing"],
        "approval_level": "human_review",
        "description": "Codex as execution target; agent and tool execution via Codex.",
    },
    "windows_review_package": {
        "canonical_name": "windows_review_package",
        "display_name": "Windows Review Package",
        "status": "active",
        "runtime_type": "local_review",
        "active_or_planned": "active",
        "capabilities": ["review_package", "execution_planning", "approval_handoff"],
        "approval_level": "human_review",
        "description": "Windows-local review-only execution package target; produces sealed packages and stops before execution.",
    },
    "container_worker": {
        "canonical_name": "container_worker",
        "display_name": "Container Worker",
        "status": "planned",
        "runtime_type": "container",
        "active_or_planned": "planned",
        "capabilities": ["execute", "terminal", "planning"],
        "approval_level": "auto",
        "description": "Containerized worker for isolated execution (planned).",
    },
    "remote_worker": {
        "canonical_name": "remote_worker",
        "display_name": "Remote Worker",
        "status": "planned",
        "runtime_type": "remote",
        "active_or_planned": "planned",
        "capabilities": ["execute", "terminal", "planning"],
        "approval_level": "human_review",
        "description": "Remote worker node for distributed execution (planned).",
    },
    "cloud_worker": {
        "canonical_name": "cloud_worker",
        "display_name": "Cloud Worker",
        "status": "planned",
        "runtime_type": "cloud",
        "active_or_planned": "planned",
        "capabilities": ["execute", "terminal", "planning"],
        "approval_level": "human_review",
        "description": "Cloud-hosted worker for scalable execution (planned).",
    },
}


def list_active_runtime_targets() -> list[str]:
    """Return canonical names of runtime targets marked active."""
    return sorted(
        name for name, meta in RUNTIME_TARGET_REGISTRY.items()
        if meta.get("active_or_planned") == "active"
    )


def list_planned_runtime_targets() -> list[str]:
    """Return canonical names of runtime targets marked planned."""
    return sorted(
        name for name, meta in RUNTIME_TARGET_REGISTRY.items()
        if meta.get("active_or_planned") == "planned"
    )


def get_target_capabilities(canonical_name: str | None) -> list[str]:
    """Return capabilities list for a runtime target, or [] if unknown."""
    if not canonical_name:
        return []
    entry = RUNTIME_TARGET_REGISTRY.get((canonical_name or "").strip().lower())
    return list(entry.get("capabilities", [])) if entry else []


def get_runtime_target_summary() -> dict[str, Any]:
    """Return a normalized summary of the runtime target registry."""
    active = list_active_runtime_targets()
    planned = list_planned_runtime_targets()
    targets = []
    for name in sorted(RUNTIME_TARGET_REGISTRY.keys()):
        entry = RUNTIME_TARGET_REGISTRY[name]
        targets.append({
            "canonical_name": entry.get("canonical_name", name),
            "display_name": entry.get("display_name", name),
            "status": entry.get("status"),
            "runtime_type": entry.get("runtime_type"),
            "active_or_planned": entry.get("active_or_planned"),
            "capabilities": list(entry.get("capabilities", [])),
            "approval_level": entry.get("approval_level"),
            "description": entry.get("description", ""),
        })
    return {
        "active_count": len(active),
        "planned_count": len(planned),
        "active_names": active,
        "planned_names": planned,
        "targets": targets,
    }
