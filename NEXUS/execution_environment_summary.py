"""
NEXUS execution environment summary layer (Phase 17).

Builds deterministic summaries for dashboard, command surface, and per-project
visibility. Read-only; no execution capability.
"""

from __future__ import annotations

from typing import Any

from NEXUS.execution_environment_registry import (
    EXECUTION_ENVIRONMENT_REGISTRY,
    RUNTIME_TARGET_TO_ENVIRONMENT,
    get_all_environment_definitions,
    get_environment_definition,
    get_environment_for_runtime_target,
    list_active_environments,
    list_planned_environments,
)
from NEXUS.registry import PROJECTS
from NEXUS.runtime_target_registry import (
    RUNTIME_TARGET_REGISTRY,
    get_runtime_target_summary,
    list_active_runtime_targets,
)


def build_execution_environment_summary(
    *,
    runtime_target_summary: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Build execution environment summary for dashboard/visibility.

    Returns:
        execution_environment_status: str
        active_environments: list[str]
        planned_environments: list[str]
        runtime_target_mapping: list[dict]  # target -> env_id
        environments: list[dict]  # full definitions
        reason: str
    """
    rt = runtime_target_summary or get_runtime_target_summary()
    active_targets = rt.get("active_names") or list_active_runtime_targets()
    planned_targets = rt.get("planned_names") or []

    active_envs = list_active_environments()
    planned_envs = list_planned_environments()

    runtime_target_mapping = []
    for target_name in sorted(RUNTIME_TARGET_REGISTRY.keys()):
        env_id = get_environment_for_runtime_target(target_name)
        runtime_target_mapping.append({
            "runtime_target": target_name,
            "execution_environment_id": env_id,
        })

    if active_envs:
        status = "available"
        reason = f"Active execution environments: {active_envs}; planned: {planned_envs}."
    else:
        status = "error_fallback"
        reason = "No active execution environments in registry."

    per_project_summaries: dict[str, dict[str, Any]] = {}
    for proj_key in sorted(PROJECTS.keys()):
        proj = PROJECTS[proj_key]
        per_project_summaries[proj_key] = build_per_project_environment_summary(
            project_name=proj.get("name") or proj_key,
            project_path=proj.get("path"),
            active_runtime_target="local",
            runtime_target_summary=rt,
        )

    return {
        "execution_environment_status": status,
        "active_environments": active_envs,
        "planned_environments": planned_envs,
        "runtime_target_mapping": runtime_target_mapping,
        "environments": get_all_environment_definitions(),
        "per_project_summaries": per_project_summaries,
        "reason": reason,
    }


def build_execution_environment_summary_safe(
    *,
    runtime_target_summary: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return build_execution_environment_summary(
            runtime_target_summary=runtime_target_summary,
            **kwargs,
        )
    except Exception:
        return {
            "execution_environment_status": "error_fallback",
            "active_environments": [],
            "planned_environments": [],
            "runtime_target_mapping": [],
            "environments": [],
            "per_project_summaries": {},
            "reason": "Execution environment summary evaluation failed.",
        }


def build_per_project_environment_summary(
    project_name: str | None = None,
    project_path: str | None = None,
    active_runtime_target: str | None = None,
    *,
    runtime_target_summary: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Deterministic per-project execution environment summary.

    Evaluates what execution environment posture the active project currently has.
    Does not change behavior; read-only visibility.

    Returns:
        project_name: str | None
        project_path: str | None
        active_runtime_target: str | None
        execution_environment_id: str | None
        environment_posture: dict | None  # full env definition
        is_isolated: bool  # True only if actually isolated (currently always False)
        is_planned_isolated: bool  # True if env is planned isolated/container/external
        reason: str
    """
    rt = runtime_target_summary or get_runtime_target_summary()
    env_id = get_environment_for_runtime_target(active_runtime_target)
    env_def = get_environment_definition(env_id) if env_id else None

    isolation_level = (env_def or {}).get("isolation_level") or "none"
    is_isolated = isolation_level in ("planned_isolated", "planned_container", "planned_external") and (
        (env_def or {}).get("status") == "active"
    )
    # Currently no active isolated envs, so is_isolated is always False.
    is_planned_isolated = isolation_level in (
        "planned_isolated",
        "planned_container",
        "planned_external",
    )

    reason = f"Project env: runtime_target={active_runtime_target}; env_id={env_id}; isolation={isolation_level}."

    return {
        "project_name": project_name,
        "project_path": project_path,
        "active_runtime_target": active_runtime_target,
        "execution_environment_id": env_id,
        "environment_posture": env_def,
        "is_isolated": is_isolated,
        "is_planned_isolated": is_planned_isolated,
        "reason": reason,
    }
