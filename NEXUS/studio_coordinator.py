"""
NEXUS multi-project studio coordination layer.

Builds a studio-level summary from loaded project states: counts, priority
project, and deterministic project order. Summary-only; no execution.
"""

from __future__ import annotations

from typing import Any

# Project key -> loaded state dict (from load_project_state)
StatesByProject = dict[str, dict[str, Any]]


def build_studio_coordination_summary(
    states_by_project: StatesByProject | None = None,
) -> dict[str, Any]:
    """
    Build studio coordination summary from loaded project states.

    states_by_project: dict mapping project key (e.g. "jarvis") to loaded
    project state dict. If None or empty, returns idle/zero summary.

    Returns stable schema:
    - coordination_status: ready | waiting | idle | error_fallback
    - active_project_count: int
    - queued_project_count: int
    - blocked_project_count: int
    - priority_project: str | None
    - priority_reason: str
    - project_order: list[str]
    """
    states_by_project = states_by_project or {}
    if not states_by_project:
        return {
            "coordination_status": "idle",
            "active_project_count": 0,
            "queued_project_count": 0,
            "blocked_project_count": 0,
            "priority_project": None,
            "priority_reason": "No project states loaded.",
            "project_order": [],
        }

    active_count = 0
    queued_count = 0
    blocked_count = 0
    # Priority tiers: 1=highest (scheduled), 2=resumable, 3=active+continue, 4=queued, 5=blocked/paused last
    tier_scheduled: list[str] = []
    tier_resumable: list[str] = []
    tier_active_continue: list[str] = []
    tier_queued: list[str] = []
    tier_other: list[str] = []

    for key, state in states_by_project.items():
        if not isinstance(state, dict) or state.get("load_error"):
            tier_other.append(key)
            continue

        pl_status = (state.get("project_lifecycle_status") or (state.get("project_lifecycle_result") or {}).get("lifecycle_status") or "").strip().lower()
        g_status = (state.get("governance_status") or (state.get("governance_result") or {}).get("governance_status") or "").strip().lower()
        sched_status = (state.get("scheduler_status") or (state.get("scheduler_result") or {}).get("scheduler_status") or "").strip().lower()
        r_status = (state.get("resume_status") or (state.get("resume_result") or {}).get("resume_status") or "").strip().lower()
        h_status = (state.get("heartbeat_status") or (state.get("heartbeat_result") or {}).get("heartbeat_status") or "").strip().lower()
        qe = state.get("review_queue_entry") or {}
        queue_status = (qe.get("queue_status") or "").strip().lower()

        if pl_status == "active":
            active_count += 1
        if queue_status == "queued":
            queued_count += 1
        if pl_status == "blocked" or g_status == "blocked":
            blocked_count += 1

        if sched_status == "scheduled":
            tier_scheduled.append(key)
        elif r_status == "resumable":
            tier_resumable.append(key)
        elif pl_status == "active" and h_status == "continue_cycle":
            tier_active_continue.append(key)
        elif queue_status == "queued":
            tier_queued.append(key)
        elif pl_status == "blocked" or g_status == "blocked":
            tier_other.append(key)
        else:
            tier_other.append(key)

    # Deterministic order: scheduled, resumable, active+continue, queued, other
    project_order = tier_scheduled + tier_resumable + tier_active_continue + tier_queued + tier_other
    priority_project = project_order[0] if project_order else None

    if tier_scheduled:
        priority_reason = "Project has scheduler_status scheduled."
        coordination_status = "ready"
    elif tier_resumable:
        priority_reason = "Project is resumable."
        coordination_status = "ready"
    elif tier_active_continue:
        priority_reason = "Project active and heartbeat continue_cycle."
        coordination_status = "ready"
    elif tier_queued:
        priority_reason = "Project has queued work."
        coordination_status = "waiting"
    elif tier_other and (active_count or queued_count or blocked_count):
        priority_reason = "No higher-priority project; showing first by order."
        coordination_status = "idle"
    else:
        priority_reason = "No project states or all idle."
        coordination_status = "idle"

    return {
        "coordination_status": coordination_status,
        "active_project_count": active_count,
        "queued_project_count": queued_count,
        "blocked_project_count": blocked_count,
        "priority_project": priority_project,
        "priority_reason": priority_reason,
        "project_order": project_order,
    }


def build_studio_coordination_summary_safe(
    states_by_project: StatesByProject | None = None,
) -> dict[str, Any]:
    """Safe wrapper: never raises; returns error_fallback summary on exception."""
    try:
        return build_studio_coordination_summary(states_by_project=states_by_project)
    except Exception:
        return {
            "coordination_status": "error_fallback",
            "active_project_count": 0,
            "queued_project_count": 0,
            "blocked_project_count": 0,
            "priority_project": None,
            "priority_reason": "Studio coordination failed.",
            "project_order": [],
        }
