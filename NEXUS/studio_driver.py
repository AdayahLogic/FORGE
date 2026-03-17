"""
NEXUS studio driver (top-level orchestrator evaluation).

Decides which project should run next from coordination and project states.
Evaluation only; does not launch runs.
"""

from __future__ import annotations

from typing import Any

StatesByProject = dict[str, dict[str, Any]]


def build_studio_driver_result(
    *,
    studio_coordination_summary: dict[str, Any] | None = None,
    states_by_project: StatesByProject | None = None,
) -> dict[str, Any]:
    """
    Build studio driver result from coordination summary and project states.

    Returns stable schema:
    - driver_status: ready | waiting | idle | blocked | error_fallback
    - driver_action: run_priority_project | resume_priority_project | defer | stop | idle
    - driver_reason: str
    - target_project: str | None
    - execution_permitted: bool
    """
    coord = studio_coordination_summary or {}
    states = states_by_project or {}
    priority_project = coord.get("priority_project")
    coordination_status = (coord.get("coordination_status") or "").strip().lower()

    if coordination_status == "waiting":
        return {
            "driver_status": "waiting",
            "driver_action": "defer",
            "driver_reason": coord.get("priority_reason") or "Coordination waiting.",
            "target_project": None,
            "execution_permitted": False,
        }

    if not priority_project:
        return {
            "driver_status": "idle",
            "driver_action": "idle",
            "driver_reason": coord.get("priority_reason") or "No priority project.",
            "target_project": None,
            "execution_permitted": False,
        }

    state = states.get(priority_project) or {}
    sched_status = (state.get("scheduler_status") or (state.get("scheduler_result") or {}).get("scheduler_status") or "").strip().lower()
    r_status = (state.get("resume_status") or (state.get("resume_result") or {}).get("resume_status") or "").strip().lower()

    if sched_status == "scheduled":
        return {
            "driver_status": "ready",
            "driver_action": "run_priority_project",
            "driver_reason": coord.get("priority_reason") or "Priority project scheduled.",
            "target_project": priority_project,
            "execution_permitted": True,
        }

    if r_status == "resumable":
        return {
            "driver_status": "ready",
            "driver_action": "resume_priority_project",
            "driver_reason": coord.get("priority_reason") or "Priority project resumable.",
            "target_project": priority_project,
            "execution_permitted": True,
        }

    return {
        "driver_status": "idle",
        "driver_action": "idle",
        "driver_reason": coord.get("priority_reason") or "Priority project not runnable.",
        "target_project": priority_project,
        "execution_permitted": False,
    }


def build_studio_driver_result_safe(
    *,
    studio_coordination_summary: dict[str, Any] | None = None,
    states_by_project: StatesByProject | None = None,
) -> dict[str, Any]:
    """Safe wrapper: never raises; returns error_fallback on exception."""
    try:
        return build_studio_driver_result(
            studio_coordination_summary=studio_coordination_summary,
            states_by_project=states_by_project,
        )
    except Exception:
        return {
            "driver_status": "error_fallback",
            "driver_action": "stop",
            "driver_reason": "Studio driver evaluation failed.",
            "target_project": None,
            "execution_permitted": False,
        }
