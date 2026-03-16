"""
NEXUS Forge heartbeat evaluation layer.

Evaluates whether Forge should continue, resume, wait, or idle. Consumes
queue, resume, governance, and lifecycle state. Evaluation only; no
background daemon or infinite loop.
"""

from __future__ import annotations

from typing import Any


def evaluate_heartbeat(
    *,
    active_project: str | None = None,
    run_id: str | None = None,
    review_queue_entry: dict[str, Any] | None = None,
    resume_result: dict[str, Any] | None = None,
    governance_status: str | None = None,
    governance_result: dict[str, Any] | None = None,
    project_lifecycle_status: str | None = None,
    project_lifecycle_result: dict[str, Any] | None = None,
    autonomous_cycle_summary: dict[str, Any] | None = None,
    dispatch_status: str | None = None,
) -> dict[str, Any]:
    """
    Evaluate heartbeat from queue, resume, governance, and lifecycle state.

    Returns stable schema:
    - heartbeat_status: continue_cycle | waiting | idle | blocked | error_fallback
    - heartbeat_action: resume_project | continue_project | await_review | await_approval | idle | stop
    - heartbeat_reason: str
    - next_cycle_allowed: bool
    - queue_detected: bool
    - resume_detected: bool
    """
    qe = review_queue_entry or {}
    rr = resume_result or {}
    queue_status = (qe.get("queue_status") or "").strip().lower()
    queue_type = (qe.get("queue_type") or "").strip().lower()
    resume_status = (rr.get("resume_status") or "").strip().lower()
    g_status = (governance_status or "").strip().lower()
    pl_status = (project_lifecycle_status or "").strip().lower()

    # Queued + waiting + manual_review
    if queue_status == "queued" and resume_status == "waiting" and queue_type == "manual_review":
        return {
            "heartbeat_status": "waiting",
            "heartbeat_action": "await_review",
            "heartbeat_reason": "Queued for manual review.",
            "next_cycle_allowed": False,
            "queue_detected": True,
            "resume_detected": False,
        }

    # Queued + waiting + approval
    if queue_status == "queued" and resume_status == "waiting" and queue_type == "approval":
        return {
            "heartbeat_status": "waiting",
            "heartbeat_action": "await_approval",
            "heartbeat_reason": "Queued for approval.",
            "next_cycle_allowed": False,
            "queue_detected": True,
            "resume_detected": False,
        }

    # Queued + resumable
    if queue_status == "queued" and resume_status == "resumable":
        return {
            "heartbeat_status": "continue_cycle",
            "heartbeat_action": "resume_project",
            "heartbeat_reason": "Resumable work queued; next cycle may resume.",
            "next_cycle_allowed": True,
            "queue_detected": True,
            "resume_detected": True,
        }

    # Blocked
    if pl_status == "blocked" or g_status == "blocked":
        return {
            "heartbeat_status": "blocked",
            "heartbeat_action": "stop",
            "heartbeat_reason": "Project or governance blocked.",
            "next_cycle_allowed": False,
            "queue_detected": queue_status == "queued",
            "resume_detected": False,
        }

    # Active + approved
    if pl_status == "active" and g_status == "approved":
        return {
            "heartbeat_status": "continue_cycle",
            "heartbeat_action": "continue_project",
            "heartbeat_reason": "Project active and approved.",
            "next_cycle_allowed": True,
            "queue_detected": False,
            "resume_detected": False,
        }

    # Default: idle or waiting
    return {
        "heartbeat_status": "idle",
        "heartbeat_action": "idle",
        "heartbeat_reason": "No active cycle or queued resume.",
        "next_cycle_allowed": False,
        "queue_detected": queue_status == "queued",
        "resume_detected": False,
    }


def evaluate_heartbeat_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises; returns error_fallback on exception."""
    try:
        return evaluate_heartbeat(**kwargs)
    except Exception:
        return {
            "heartbeat_status": "error_fallback",
            "heartbeat_action": "stop",
            "heartbeat_reason": "Heartbeat evaluation failed.",
            "next_cycle_allowed": False,
            "queue_detected": False,
            "resume_detected": False,
        }
