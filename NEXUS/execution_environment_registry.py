"""
NEXUS execution environment registry (Phase 17).

Models execution context posture: isolation level, mutation allowance, network posture,
and review requirements. Distinct from runtime targets (where work runs) and AEGIS
environment (local_dev/staging/production). This layer prepares for future sandbox/
container isolation without pretending it exists.

Environment types:
- local_current: Active in-process execution; no isolation; bounded by AEGIS.
- local_bounded: Active IDE-mediated execution; bounded mutation; no real isolation.
- isolated_planned: Planned sandbox/isolated execution; not yet implemented.
- container_planned: Planned container execution; not yet implemented.
- external_runtime_planned: Planned external runtime; not yet implemented.
"""

from __future__ import annotations

from typing import Any

# -----------------------------------------------------------------------------
# Execution environment contract shape
# -----------------------------------------------------------------------------
# Each environment definition has:
#   environment_id: str
#   status: "active" | "planned"
#   isolation_level: "none" | "bounded" | "planned_isolated" | "planned_container" | "planned_external"
#   mutation_posture: "allowed" | "bounded" | "planned_restricted" | "planned_none"
#   network_posture: "allowed" | "restricted" | "planned_restricted" | "planned_none"
#   human_review_required: bool
#   bounded_execution: bool
#   notes: str
# -----------------------------------------------------------------------------

EXECUTION_ENVIRONMENT_REGISTRY: dict[str, dict[str, Any]] = {
    "local_current": {
        "environment_id": "local_current",
        "display_name": "Local Current",
        "status": "active",
        "isolation_level": "none",
        "mutation_posture": "allowed",
        "network_posture": "allowed",
        "human_review_required": False,
        "bounded_execution": True,
        "notes": "In-process execution; no isolation; bounded by AEGIS and file_guard.",
    },
    "local_bounded": {
        "environment_id": "local_bounded",
        "display_name": "Local Bounded",
        "status": "active",
        "isolation_level": "bounded",
        "mutation_posture": "bounded",
        "network_posture": "allowed",
        "human_review_required": True,
        "bounded_execution": True,
        "notes": "IDE-mediated execution; bounded mutation via tool gateway; no real isolation.",
    },
    "isolated_planned": {
        "environment_id": "isolated_planned",
        "display_name": "Isolated (Planned)",
        "status": "planned",
        "isolation_level": "planned_isolated",
        "mutation_posture": "planned_restricted",
        "network_posture": "planned_restricted",
        "human_review_required": True,
        "bounded_execution": True,
        "notes": "Planned sandbox/isolated execution; not yet implemented.",
    },
    "container_planned": {
        "environment_id": "container_planned",
        "display_name": "Container (Planned)",
        "status": "planned",
        "isolation_level": "planned_container",
        "mutation_posture": "planned_restricted",
        "network_posture": "planned_restricted",
        "human_review_required": True,
        "bounded_execution": True,
        "notes": "Planned container execution; not yet implemented.",
    },
    "external_runtime_planned": {
        "environment_id": "external_runtime_planned",
        "display_name": "External Runtime (Planned)",
        "status": "planned",
        "isolation_level": "planned_external",
        "mutation_posture": "planned_restricted",
        "network_posture": "planned_restricted",
        "human_review_required": True,
        "bounded_execution": True,
        "notes": "Planned external runtime execution; not yet implemented.",
    },
}

# Mapping: runtime target canonical name -> execution environment id
RUNTIME_TARGET_TO_ENVIRONMENT: dict[str, str] = {
    "local": "local_current",
    "cursor": "local_bounded",
    "codex": "local_bounded",
    "windows_review_package": "local_bounded",
    "container_worker": "container_planned",
    "remote_worker": "external_runtime_planned",
    "cloud_worker": "external_runtime_planned",
}


def get_environment_for_runtime_target(runtime_target: str | None) -> str | None:
    """Return execution environment id for a runtime target, or None if unknown."""
    if not runtime_target:
        return None
    key = str(runtime_target).strip().lower()
    return RUNTIME_TARGET_TO_ENVIRONMENT.get(key)


def get_environment_definition(environment_id: str | None) -> dict[str, Any] | None:
    """Return full environment definition, or None if unknown."""
    if not environment_id:
        return None
    key = str(environment_id).strip().lower()
    return dict(EXECUTION_ENVIRONMENT_REGISTRY.get(key, {}))


def list_active_environments() -> list[str]:
    """Return environment ids marked active."""
    return sorted(
        eid for eid, meta in EXECUTION_ENVIRONMENT_REGISTRY.items()
        if meta.get("status") == "active"
    )


def list_planned_environments() -> list[str]:
    """Return environment ids marked planned."""
    return sorted(
        eid for eid, meta in EXECUTION_ENVIRONMENT_REGISTRY.items()
        if meta.get("status") == "planned"
    )


def get_all_environment_definitions() -> list[dict[str, Any]]:
    """Return normalized list of all environment definitions for visibility."""
    result = []
    for eid in sorted(EXECUTION_ENVIRONMENT_REGISTRY.keys()):
        meta = EXECUTION_ENVIRONMENT_REGISTRY[eid]
        result.append({
            "environment_id": meta.get("environment_id", eid),
            "display_name": meta.get("display_name", eid),
            "status": meta.get("status"),
            "isolation_level": meta.get("isolation_level"),
            "mutation_posture": meta.get("mutation_posture"),
            "network_posture": meta.get("network_posture"),
            "human_review_required": meta.get("human_review_required"),
            "bounded_execution": meta.get("bounded_execution"),
            "notes": meta.get("notes", ""),
        })
    return result
