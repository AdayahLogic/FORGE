"""
NEXUS bounded cycle scheduler evaluation layer.

Determines whether another safe cycle should be permitted for the active project.
Consumes heartbeat, resume, queue, and lifecycle state; does not launch cycles.
Evaluation only; no daemon or infinite loop.
"""

from __future__ import annotations

from typing import Any


def evaluate_cycle_scheduler(
    *,
    active_project: str | None = None,
    run_id: str | None = None,
    heartbeat_status: str | None = None,
    heartbeat_result: dict[str, Any] | None = None,
    resume_status: str | None = None,
    resume_result: dict[str, Any] | None = None,
    review_queue_entry: dict[str, Any] | None = None,
    project_lifecycle_status: str | None = None,
    project_lifecycle_result: dict[str, Any] | None = None,
    governance_status: str | None = None,
    governance_result: dict[str, Any] | None = None,
    autonomous_cycle_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Evaluate whether a next cycle is permitted for the active project.

    Returns stable schema:
    - scheduler_status: scheduled | waiting | idle | blocked | error_fallback
    - scheduler_action: run_next_cycle | resume_project | defer | stop | idle
    - scheduler_reason: str
    - next_cycle_permitted: bool
    - scheduled_project: str | None
    - cycle_limit_reached: bool
    """
    h_status = (heartbeat_status or "").strip().lower()
    hr = heartbeat_result or {}
    r_status = (resume_status or "").strip().lower()
    qe = review_queue_entry or {}
    queue_status = (qe.get("queue_status") or "").strip().lower()
    pl_status = (project_lifecycle_status or "").strip().lower()
    g_status = (governance_status or "").strip().lower()
    ac = autonomous_cycle_summary or {}

    next_cycle_permitted = hr.get("next_cycle_allowed", False)
    cycle_limit_reached = False
    stopped_reason = (ac.get("stopped_reason") or "").lower()
    if "cycle limit" in stopped_reason or (
        ac.get("cycles_run") is not None
        and ac.get("max_cycles_allowed") is not None
        and ac.get("cycles_run", 0) >= ac.get("max_cycles_allowed", 0)
    ):
        cycle_limit_reached = True

    # Cycle limit reached
    if cycle_limit_reached:
        return {
            "scheduler_status": "idle",
            "scheduler_action": "stop",
            "scheduler_reason": ac.get("stopped_reason") or "Safe max cycle limit reached.",
            "next_cycle_permitted": False,
            "scheduled_project": None,
            "cycle_limit_reached": True,
        }

    # Blocked
    if pl_status == "blocked" or g_status == "blocked":
        return {
            "scheduler_status": "blocked",
            "scheduler_action": "stop",
            "scheduler_reason": "Project or governance blocked.",
            "next_cycle_permitted": False,
            "scheduled_project": None,
            "cycle_limit_reached": False,
        }

    # Queued + waiting -> defer
    if queue_status == "queued" and r_status == "waiting":
        return {
            "scheduler_status": "waiting",
            "scheduler_action": "defer",
            "scheduler_reason": "Work queued; waiting for review or approval.",
            "next_cycle_permitted": False,
            "scheduled_project": None,
            "cycle_limit_reached": False,
        }

    # Continue cycle + next allowed -> scheduled
    if h_status == "continue_cycle" and next_cycle_permitted:
        action = "resume_project" if hr.get("heartbeat_action") == "resume_project" else "run_next_cycle"
        return {
            "scheduler_status": "scheduled",
            "scheduler_action": action,
            "scheduler_reason": hr.get("heartbeat_reason") or "Next cycle permitted.",
            "next_cycle_permitted": True,
            "scheduled_project": active_project or "",
            "cycle_limit_reached": False,
        }

    # Default: idle
    return {
        "scheduler_status": "idle",
        "scheduler_action": "idle",
        "scheduler_reason": "No next cycle scheduled.",
        "next_cycle_permitted": False,
        "scheduled_project": None,
        "cycle_limit_reached": False,
    }


def evaluate_cycle_scheduler_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises; returns error_fallback on exception."""
    try:
        return evaluate_cycle_scheduler(**kwargs)
    except Exception:
        return {
            "scheduler_status": "error_fallback",
            "scheduler_action": "stop",
            "scheduler_reason": "Scheduler evaluation failed.",
            "next_cycle_permitted": False,
            "scheduled_project": None,
            "cycle_limit_reached": False,
        }
