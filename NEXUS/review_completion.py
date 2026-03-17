"""
NEXUS human review / approval completion flow.

Lightweight completion result builder for explicitly marking manual-review or
approval as complete and unlocking resume. Command-driven only; no auto-completion.
"""

from __future__ import annotations

from typing import Any


def build_completion_result(
    *,
    active_project: str | None = None,
    run_id: str | None = None,
    review_queue_entry: dict[str, Any] | None = None,
    completion_type: str | None = None,
    completion_requested: bool = False,
    completion_reason: str | None = None,
    enforcement_result: dict[str, Any] | None = None,
    resume_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build completion result from queue state and completion request.

    Returns stable schema:
    - completion_status: completed | waiting | not_applicable | error_fallback
    - completion_type: manual_review | approval | none
    - completion_reason: str
    - queue_cleared: bool
    - resume_unlocked: bool
    - completion_recorded: bool
    """
    qe = review_queue_entry or {}
    queue_status = (qe.get("queue_status") or "").strip().lower()
    queue_type = (qe.get("queue_type") or "").strip().lower()
    ctype = (completion_type or "").strip().lower()

    if not completion_requested:
        if queue_status == "queued":
            return {
                "completion_status": "waiting",
                "completion_type": ctype or "none",
                "completion_reason": completion_reason or "No completion requested; work remains queued.",
                "queue_cleared": False,
                "resume_unlocked": False,
                "completion_recorded": False,
            }
        return {
            "completion_status": "not_applicable",
            "completion_type": "none",
            "completion_reason": "No completion requested.",
            "queue_cleared": False,
            "resume_unlocked": False,
            "completion_recorded": False,
        }

    if queue_type == "manual_review" and ctype == "manual_review":
        return {
            "completion_status": "completed",
            "completion_type": "manual_review",
            "completion_reason": completion_reason or "Manual review completed.",
            "queue_cleared": True,
            "resume_unlocked": True,
            "completion_recorded": True,
        }

    if queue_type == "approval" and ctype == "approval":
        return {
            "completion_status": "completed",
            "completion_type": "approval",
            "completion_reason": completion_reason or "Approval completed.",
            "queue_cleared": True,
            "resume_unlocked": True,
            "completion_recorded": True,
        }

    if queue_status != "queued":
        return {
            "completion_status": "not_applicable",
            "completion_type": ctype or "none",
            "completion_reason": "No matching queued work to complete.",
            "queue_cleared": False,
            "resume_unlocked": False,
            "completion_recorded": False,
        }

    return {
        "completion_status": "waiting",
        "completion_type": ctype or queue_type or "none",
        "completion_reason": completion_reason or f"Completion type '{ctype}' does not match queue type '{queue_type}'.",
        "queue_cleared": False,
        "resume_unlocked": False,
        "completion_recorded": False,
    }


def build_completion_result_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises; returns error_fallback on exception."""
    try:
        return build_completion_result(**kwargs)
    except Exception:
        return {
            "completion_status": "error_fallback",
            "completion_type": "none",
            "completion_reason": "Completion evaluation failed.",
            "queue_cleared": False,
            "resume_unlocked": False,
            "completion_recorded": False,
        }
