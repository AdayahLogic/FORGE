"""
NEXUS controlled re-execution evaluation layer.

Determines whether one safe next project cycle should be run. Consumes
scheduler, recovery, resume, queue, lifecycle. Bounded and explicit only;
no automatic launch.
"""

from __future__ import annotations

from typing import Any


def evaluate_reexecution_outcome(
    *,
    active_project: str | None = None,
    run_id: str | None = None,
    scheduler_status: str | None = None,
    scheduler_result: dict[str, Any] | None = None,
    recovery_status: str | None = None,
    recovery_result: dict[str, Any] | None = None,
    resume_status: str | None = None,
    resume_result: dict[str, Any] | None = None,
    review_queue_entry: dict[str, Any] | None = None,
    autonomous_cycle_summary: dict[str, Any] | None = None,
    project_lifecycle_status: str | None = None,
    project_lifecycle_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Evaluate re-execution outcome from scheduler, recovery, resume, queue, lifecycle.

    Returns stable schema:
    - reexecution_status: ready | waiting | blocked | idle | error_fallback
    - reexecution_action: run_project_cycle | resume_project | defer | stop | idle
    - reexecution_reason: str
    - target_project: str | None
    - run_permitted: bool
    - bounded_execution: bool
    """
    sr = scheduler_result or {}
    rr = recovery_result or {}
    qe = review_queue_entry or {}
    r_status = (recovery_status or "").strip().lower()
    queue_status = (qe.get("queue_status") or "").strip().lower()

    if r_status == "blocked":
        return {
            "reexecution_status": "blocked",
            "reexecution_action": "stop",
            "reexecution_reason": "Recovery status blocked.",
            "target_project": None,
            "run_permitted": False,
            "bounded_execution": True,
        }

    if queue_status == "queued" and r_status == "waiting":
        return {
            "reexecution_status": "waiting",
            "reexecution_action": "defer",
            "reexecution_reason": "Work queued; recovery waiting.",
            "target_project": None,
            "run_permitted": False,
            "bounded_execution": True,
        }

    if sr.get("next_cycle_permitted") and rr.get("retry_permitted"):
        action = "resume_project" if rr.get("recovery_action") == "retry_project" else "run_project_cycle"
        return {
            "reexecution_status": "ready",
            "reexecution_action": action,
            "reexecution_reason": sr.get("scheduler_reason") or rr.get("recovery_reason") or "Next cycle permitted.",
            "target_project": active_project or sr.get("scheduled_project") or "",
            "run_permitted": True,
            "bounded_execution": True,
        }

    return {
        "reexecution_status": "idle",
        "reexecution_action": "idle",
        "reexecution_reason": "Re-execution conditions not met.",
        "target_project": None,
        "run_permitted": False,
        "bounded_execution": True,
    }


def evaluate_reexecution_outcome_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises; returns error_fallback on exception."""
    try:
        return evaluate_reexecution_outcome(**kwargs)
    except Exception:
        return {
            "reexecution_status": "error_fallback",
            "reexecution_action": "stop",
            "reexecution_reason": "Re-execution evaluation failed.",
            "target_project": None,
            "run_permitted": False,
            "bounded_execution": True,
        }
