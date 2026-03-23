"""
NEXUS recovery / retry / failure repair evaluation layer.

Determines whether a project is retry-ready, waiting, blocked, or requires
state repair. Consumes completion, resume, scheduler, governance, lifecycle.
Evaluation only; no automatic retry or destructive recovery.
"""

from __future__ import annotations

from typing import Any

RETRY_COUNT_THRESHOLD = 3


def evaluate_recovery_outcome(
    *,
    active_project: str | None = None,
    run_id: str | None = None,
    review_queue_entry: dict[str, Any] | None = None,
    completion_result: dict[str, Any] | None = None,
    resume_result: dict[str, Any] | None = None,
    heartbeat_result: dict[str, Any] | None = None,
    scheduler_result: dict[str, Any] | None = None,
    governance_status: str | None = None,
    governance_result: dict[str, Any] | None = None,
    project_lifecycle_status: str | None = None,
    project_lifecycle_result: dict[str, Any] | None = None,
    enforcement_status: str | None = None,
    enforcement_result: dict[str, Any] | None = None,
    retry_count: int = 0,
    evaluation_status: str | None = None,
    local_analysis_status: str | None = None,
) -> dict[str, Any]:
    """
    Evaluate recovery outcome from completion, resume, scheduler, governance, lifecycle.

    Returns stable schema:
    - recovery_status: retry_ready | waiting | repair_required | blocked | error_fallback
    - recovery_action: retry_project | repair_state | await_review | await_approval | stop | none
    - recovery_reason: str
    - retry_permitted: bool
    - repair_required: bool
    - retry_count_exceeded: bool
    """
    qe = review_queue_entry or {}
    cr = completion_result or {}
    rr = resume_result or {}
    sr = scheduler_result or {}
    queue_status = (qe.get("queue_status") or "").strip().lower()
    queue_type = (qe.get("queue_type") or "").strip().lower()
    comp_status = (cr.get("completion_status") or "").strip().lower()
    r_status = (rr.get("resume_status") or "").strip().lower()
    pl_status = (project_lifecycle_status or "").strip().lower()
    g_status = (governance_status or "").strip().lower()
    e_status = (enforcement_status or "").strip().lower()
    ev_status = (evaluation_status or "").strip().lower()
    la_status = (local_analysis_status or "").strip().lower()
    governance_conflict = bool(
        (g_status == "approval_required" and e_status == "continue")
        or (g_status == "approved" and e_status in ("blocked", "hold"))
    )

    retry_count_exceeded = retry_count > RETRY_COUNT_THRESHOLD

    if governance_conflict:
        return {
            "recovery_status": "blocked",
            "recovery_action": "pause_system",
            "recovery_reason": "Governance and enforcement conflict requires a system pause.",
            "retry_permitted": False,
            "repair_required": False,
            "retry_count_exceeded": False,
            "conflict_escalation_status": "system_pause_required",
            "system_pause_required": True,
            "recovery_pipeline": ["pause_system", "resolve_governance_conflict", "await_operator_review"],
        }

    if retry_count_exceeded:
        return {
            "recovery_status": "blocked",
            "recovery_action": "stop",
            "recovery_reason": f"Retry count ({retry_count}) exceeds safe threshold ({RETRY_COUNT_THRESHOLD}).",
            "retry_permitted": False,
            "repair_required": False,
            "retry_count_exceeded": True,
            "conflict_escalation_status": "resolved_or_none",
            "system_pause_required": False,
            "recovery_pipeline": ["stop"],
        }

    if pl_status == "blocked" or g_status == "blocked":
        return {
            "recovery_status": "blocked",
            "recovery_action": "stop",
            "recovery_reason": "Project or governance blocked.",
            "retry_permitted": False,
            "repair_required": False,
            "retry_count_exceeded": False,
            "conflict_escalation_status": "resolved_or_none",
            "system_pause_required": False,
            "recovery_pipeline": ["stop"],
        }

    if ev_status == "error_fallback" or la_status == "error_fallback":
        return {
            "recovery_status": "repair_required",
            "recovery_action": "repair_state",
            "recovery_reason": "Evaluation/local analysis failed and requires recovery handling.",
            "retry_permitted": False,
            "repair_required": True,
            "retry_count_exceeded": False,
            "conflict_escalation_status": "resolved_or_none",
            "system_pause_required": False,
            "recovery_pipeline": ["collect_failure_evidence", "repair_state", "re_evaluate"],
        }

    if queue_type == "manual_review" and comp_status != "completed":
        return {
            "recovery_status": "waiting",
            "recovery_action": "await_review",
            "recovery_reason": "Manual review not yet completed.",
            "retry_permitted": False,
            "repair_required": False,
            "retry_count_exceeded": False,
            "conflict_escalation_status": "resolved_or_none",
            "system_pause_required": False,
            "recovery_pipeline": ["await_review"],
        }

    if queue_type == "approval" and comp_status != "completed":
        return {
            "recovery_status": "waiting",
            "recovery_action": "await_approval",
            "recovery_reason": "Approval not yet completed.",
            "retry_permitted": False,
            "repair_required": False,
            "retry_count_exceeded": False,
            "conflict_escalation_status": "resolved_or_none",
            "system_pause_required": False,
            "recovery_pipeline": ["await_approval"],
        }

    if comp_status == "completed" and r_status in ("resumable", "not_applicable") and sr.get("next_cycle_permitted"):
        return {
            "recovery_status": "retry_ready",
            "recovery_action": "retry_project",
            "recovery_reason": "Completion recorded; resume and scheduler permit next cycle.",
            "retry_permitted": True,
            "repair_required": False,
            "retry_count_exceeded": False,
            "conflict_escalation_status": "resolved_or_none",
            "system_pause_required": False,
            "recovery_pipeline": ["retry_project"],
        }

    if queue_status == "queued" and comp_status == "completed" and r_status == "waiting":
        return {
            "recovery_status": "repair_required",
            "recovery_action": "repair_state",
            "recovery_reason": "Completion recorded but queue/resume state inconsistent.",
            "retry_permitted": False,
            "repair_required": True,
            "retry_count_exceeded": False,
            "conflict_escalation_status": "resolved_or_none",
            "system_pause_required": False,
            "recovery_pipeline": ["repair_state", "reconcile_queue", "reassess_resume"],
        }

    return {
        "recovery_status": "waiting",
        "recovery_action": "none",
        "recovery_reason": "Recovery conditions not met.",
        "retry_permitted": False,
        "repair_required": False,
        "retry_count_exceeded": False,
        "conflict_escalation_status": "resolved_or_none",
        "system_pause_required": False,
        "recovery_pipeline": ["none"],
    }


def evaluate_recovery_outcome_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises; returns error_fallback on exception."""
    try:
        return evaluate_recovery_outcome(**kwargs)
    except Exception:
        return {
            "recovery_status": "error_fallback",
            "recovery_action": "stop",
            "recovery_reason": "Recovery evaluation failed.",
            "retry_permitted": False,
            "repair_required": False,
            "retry_count_exceeded": False,
            "conflict_escalation_status": "system_pause_required",
            "system_pause_required": True,
            "recovery_pipeline": ["pause_system"],
        }
