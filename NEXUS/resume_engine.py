"""
NEXUS resume / re-entry evaluation layer.

Evaluates whether queued/stopped work can be resumed and how. Consumes
review queue, enforcement, and lifecycle state; does not recalculate.
Evaluation only; no automatic re-entry or execution.
"""

from __future__ import annotations

from typing import Any


def evaluate_resume_outcome(
    *,
    active_project: str | None = None,
    run_id: str | None = None,
    review_queue_entry: dict[str, Any] | None = None,
    enforcement_status: str | None = None,
    enforcement_result: dict[str, Any] | None = None,
    workflow_route_status: str | None = None,
    workflow_route_reason: str | None = None,
    governance_status: str | None = None,
    project_lifecycle_status: str | None = None,
) -> dict[str, Any]:
    """
    Evaluate resume outcome from queue and enforcement state.

    Returns stable schema:
    - resume_status: resumable | waiting | not_applicable | blocked | error_fallback
    - resume_type: manual_review | approval | hold | blocked | none
    - resume_reason: str
    - resume_action: str
    - target_workflow_action: str | None
    - requires_human_action: bool
    """
    qe = review_queue_entry or {}
    queue_status = (qe.get("queue_status") or "").strip().lower()
    queue_type = (qe.get("queue_type") or "").strip().lower()
    route = (workflow_route_status or "").strip().lower()

    if queue_status != "queued":
        return {
            "resume_status": "not_applicable",
            "resume_type": "none",
            "resume_reason": "No queued work requires resume handling.",
            "resume_action": "none",
            "target_workflow_action": None,
            "requires_human_action": False,
        }

    if queue_type == "manual_review":
        return {
            "resume_status": "waiting",
            "resume_type": "manual_review",
            "resume_reason": "Queued for manual review.",
            "resume_action": "await_manual_review",
            "target_workflow_action": None,
            "requires_human_action": True,
        }

    if queue_type == "approval":
        return {
            "resume_status": "waiting",
            "resume_type": "approval",
            "resume_reason": "Queued for approval.",
            "resume_action": "await_approval",
            "target_workflow_action": None,
            "requires_human_action": True,
        }

    if queue_type == "hold":
        # Resumable when on hold path; target proceed for future re-entry
        resumable = route == "hold_state"
        return {
            "resume_status": "resumable" if resumable else "waiting",
            "resume_type": "hold",
            "resume_reason": "Workflow is on hold and may be resumed when hold conditions are released.",
            "resume_action": "resume_from_hold",
            "target_workflow_action": "proceed" if resumable else None,
            "requires_human_action": False,
        }

    if queue_type == "blocked":
        return {
            "resume_status": "blocked",
            "resume_type": "blocked",
            "resume_reason": "Workflow is blocked until blockers are cleared.",
            "resume_action": "resolve_blockers",
            "target_workflow_action": None,
            "requires_human_action": True,
        }

    return {
        "resume_status": "not_applicable",
        "resume_type": "none",
        "resume_reason": "No queued work requires resume handling.",
        "resume_action": "none",
        "target_workflow_action": None,
        "requires_human_action": False,
    }


def evaluate_resume_outcome_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises; returns error_fallback on exception."""
    try:
        return evaluate_resume_outcome(**kwargs)
    except Exception:
        return {
            "resume_status": "error_fallback",
            "resume_type": "none",
            "resume_reason": "Resume evaluation failed.",
            "resume_action": "none",
            "target_workflow_action": None,
            "requires_human_action": True,
        }
