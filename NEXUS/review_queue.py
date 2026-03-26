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
    mission_status: str | None = None,
    mission_id: str | None = None,
    mission_title: str | None = None,
    mission_risk_level: str | None = None,
    mission_stop_condition_hit: bool | None = None,
    mission_stop_condition_reason: str | None = None,
    mission_requires_initial_approval: bool | None = None,
    mission_requires_final_approval: bool | None = None,
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
    m_status = (mission_status or "").strip().lower()
    m_risk = (mission_risk_level or "").strip().lower() or "medium"
    m_id = str(mission_id or "").strip()
    m_title = str(mission_title or "").strip()
    m_stop_hit = bool(mission_stop_condition_hit)
    m_stop_reason = str(mission_stop_condition_reason or "").strip()
    m_requires_initial = bool(mission_requires_initial_approval) if mission_requires_initial_approval is not None else True
    m_requires_final = bool(mission_requires_final_approval) if mission_requires_final_approval is not None else True

    if m_stop_hit:
        return {
            "queue_status": "queued",
            "queue_type": "mission_escalation_review",
            "queue_reason": m_stop_reason or workflow_route_reason or er.get("reason") or "Mission stop condition triggered.",
            "resume_action": "resolve_escalation",
            "resume_condition": "escalation_resolved",
            "active_project": active_project or "",
            "run_id": run_id or "",
            "requires_human_action": True,
            "approval_queue_item_type": "mission_escalation_review",
            "approval_queue_risk_class": m_risk,
            "approval_queue_reason": m_stop_reason or "Mission escalation requires operator review.",
            "approval_queue_batchable": False,
            "approval_queue_requires_initial_approval": m_requires_initial,
            "approval_queue_requires_final_approval": m_requires_final,
            "approval_queue_escalation_reason": m_stop_reason or "mission_stop_condition_hit",
            "mission_id": m_id,
            "mission_title": m_title,
            "mission_status": m_status or "paused",
        }

    if m_status in ("proposed", "awaiting_initial_approval") and m_requires_initial:
        return {
            "queue_status": "queued",
            "queue_type": "mission_initial_approval",
            "queue_reason": workflow_route_reason or er.get("reason") or "Mission start approval required.",
            "resume_action": "await_mission_initial_approval",
            "resume_condition": "mission_initial_approval_granted",
            "active_project": active_project or "",
            "run_id": run_id or "",
            "requires_human_action": True,
            "approval_queue_item_type": "mission_initial_approval",
            "approval_queue_risk_class": m_risk,
            "approval_queue_reason": "Mission boundary approval required before execution.",
            "approval_queue_batchable": True,
            "approval_queue_requires_initial_approval": True,
            "approval_queue_requires_final_approval": m_requires_final,
            "approval_queue_escalation_reason": "",
            "mission_id": m_id,
            "mission_title": m_title,
            "mission_status": m_status,
        }

    if m_status in ("awaiting_final_review",) and m_requires_final:
        return {
            "queue_status": "queued",
            "queue_type": "mission_final_acceptance",
            "queue_reason": workflow_route_reason or er.get("reason") or "Mission final acceptance required.",
            "resume_action": "await_mission_final_acceptance",
            "resume_condition": "mission_final_acceptance_granted",
            "active_project": active_project or "",
            "run_id": run_id or "",
            "requires_human_action": True,
            "approval_queue_item_type": "mission_final_acceptance",
            "approval_queue_risk_class": m_risk,
            "approval_queue_reason": "Mission execution complete; final acceptance required.",
            "approval_queue_batchable": True,
            "approval_queue_requires_initial_approval": m_requires_initial,
            "approval_queue_requires_final_approval": True,
            "approval_queue_escalation_reason": "",
            "mission_id": m_id,
            "mission_title": m_title,
            "mission_status": m_status,
        }

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
        "approval_queue_item_type": "none",
        "approval_queue_risk_class": m_risk,
        "approval_queue_reason": "",
        "approval_queue_batchable": False,
        "approval_queue_requires_initial_approval": m_requires_initial,
        "approval_queue_requires_final_approval": m_requires_final,
        "approval_queue_escalation_reason": "",
        "mission_id": m_id,
        "mission_title": m_title,
        "mission_status": m_status or "",
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
