"""
NEXUS review and approval queue layer.

Builds a normalized queue entry from enforcement/routing outcomes for runs
routed to manual review, approval hold, hold, or blocked. Consumes existing
outcomes; does not recalculate. No external approval systems; record creation
and persistence only.
"""

from __future__ import annotations

from typing import Any


def build_review_queue_entry(
    *,
    active_project: str | None = None,
    run_id: str | None = None,
    enforcement_status: str | None = None,
    enforcement_result: dict[str, Any] | None = None,
    workflow_route_status: str | None = None,
    workflow_route_reason: str | None = None,
    governance_status: str | None = None,
    project_lifecycle_status: str | None = None,
) -> dict[str, Any]:
    """
    Build a normalized review queue entry from enforcement and routing state.

    Returns stable schema:
    - queue_status: queued | not_queued | error_fallback
    - queue_type: manual_review | approval | hold | blocked | none
    - queue_reason: str
    - resume_action: str
    - resume_condition: str
    - active_project: str
    - run_id: str
    - requires_human_action: bool
    """
    e_status = (enforcement_status or "").strip().lower()
    route = (workflow_route_status or "").strip().lower()
    er = enforcement_result or {}

    # manual_review_required / manual_review_hold
    if e_status == "manual_review_required" or route == "manual_review_hold":
        return {
            "queue_status": "queued",
            "queue_type": "manual_review",
            "queue_reason": workflow_route_reason or er.get("reason") or "Manual review required.",
            "resume_action": "manual_review",
            "resume_condition": "human_review_completed",
            "active_project": active_project or "",
            "run_id": run_id or "",
            "requires_human_action": True,
        }

    # approval_required / approval_hold
    if e_status == "approval_required" or route == "approval_hold":
        return {
            "queue_status": "queued",
            "queue_type": "approval",
            "queue_reason": workflow_route_reason or er.get("reason") or "Approval required.",
            "resume_action": "await_approval",
            "resume_condition": "approval_granted",
            "active_project": active_project or "",
            "run_id": run_id or "",
            "requires_human_action": True,
        }

    # hold / hold_state
    if e_status == "hold" or route == "hold_state":
        return {
            "queue_status": "queued",
            "queue_type": "hold",
            "queue_reason": workflow_route_reason or er.get("reason") or "Workflow held.",
            "resume_action": "hold",
            "resume_condition": "hold_released",
            "active_project": active_project or "",
            "run_id": run_id or "",
            "requires_human_action": False,
        }

    # blocked / blocked_stop
    if e_status == "blocked" or route == "blocked_stop":
        return {
            "queue_status": "queued",
            "queue_type": "blocked",
            "queue_reason": workflow_route_reason or er.get("reason") or "Workflow blocked.",
            "resume_action": "resolve_blockers",
            "resume_condition": "blockers_cleared",
            "active_project": active_project or "",
            "run_id": run_id or "",
            "requires_human_action": True,
        }

    # Proceed path or unknown: not queued
    return {
        "queue_status": "not_queued",
        "queue_type": "none",
        "queue_reason": "Workflow proceeded normally.",
        "resume_action": "none",
        "resume_condition": "none",
        "active_project": active_project or "",
        "run_id": run_id or "",
        "requires_human_action": False,
    }


def build_review_queue_entry_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises; returns error_fallback entry on exception."""
    try:
        return build_review_queue_entry(**kwargs)
    except Exception:
        return {
            "queue_status": "error_fallback",
            "queue_type": "none",
            "queue_reason": "Queue entry build failed.",
            "resume_action": "none",
            "resume_condition": "none",
            "active_project": kwargs.get("active_project") or "",
            "run_id": kwargs.get("run_id") or "",
            "requires_human_action": True,
        }
