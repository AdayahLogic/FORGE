"""
Phase 91 execution handoff review synthesis.

Read-only contract that derives governed execution handoff readiness without
triggering execution, approvals, or lifecycle transitions.
"""

from __future__ import annotations

from typing import Any


HANDOFF_STATUSES = {
    "not_ready",
    "needs_review",
    "awaiting_approval",
    "ready_for_handoff",
    "handoff_blocked",
}
HANDOFF_READINESS_LEVELS = {"low", "medium", "high"}
HANDOFF_SCOPES = {"project", "package"}
_BUDGET_BLOCKED = {"cap_exceeded", "kill_switch_triggered", "kill_switch_active", "blocked_by_budget"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _normalize_status(value: str) -> str:
    status = _text(value).lower()
    return status if status in HANDOFF_STATUSES else "not_ready"


def _normalize_readiness(value: str) -> str:
    readiness = _text(value).lower()
    return readiness if readiness in HANDOFF_READINESS_LEVELS else "low"


def _normalize_scope(value: str) -> str:
    scope = _text(value).lower()
    return scope if scope in HANDOFF_SCOPES else "project"


def _dedupe(values: list[str]) -> list[str]:
    seen: list[str] = []
    for item in values:
        text = _text(item)
        if text and text not in seen:
            seen.append(text)
    return seen


def _governance_flags(project_state: dict[str, Any], package: dict[str, Any]) -> dict[str, bool | str]:
    checkpoint_status = (
        _text(project_state.get("checkpoint_status"))
        or _text(package.get("checkpoint_status"))
        or "not_required"
    ).lower()
    return {
        "manual_hold_active": bool(project_state.get("manual_hold_active") or package.get("manual_hold_active")),
        "freeze_required": bool(project_state.get("freeze_required") or package.get("freeze_required")),
        "recovery_only_mode": bool(project_state.get("recovery_only_mode") or package.get("recovery_only_mode")),
        "checkpoint_required": bool(project_state.get("checkpoint_required") or package.get("checkpoint_required")),
        "checkpoint_status": checkpoint_status,
    }


def _approval_posture(*, approval_required: bool, decision_status: str, checkpoint_pending: bool) -> str:
    if checkpoint_pending:
        return "checkpoint_pending"
    if approval_required and decision_status in {"", "pending", "review_pending", "not_started"}:
        return "approval_required"
    if decision_status == "approved":
        return "approved"
    return "review_in_progress"


def build_execution_handoff_review(
    *,
    scope: str,
    project_state: dict[str, Any] | None = None,
    package: dict[str, Any] | None = None,
    intake_preview: dict[str, Any] | None = None,
    operator_guidance: dict[str, Any] | None = None,
    live_operation_status: dict[str, Any] | None = None,
    review_center_context: dict[str, Any] | None = None,
    model_routing_policy: dict[str, Any] | None = None,
    delivery_summary: dict[str, Any] | None = None,
    budget_status: str = "",
    budget_reason: str = "",
    has_active_package: bool = False,
) -> dict[str, Any]:
    normalized_scope = _normalize_scope(scope)
    state = _as_dict(project_state)
    pkg = _as_dict(package)
    preview = _as_dict(intake_preview)
    guidance = _as_dict(operator_guidance)
    live = _as_dict(live_operation_status)
    review = _as_dict(review_center_context)
    routing = _as_dict(model_routing_policy)
    delivery = _as_dict(delivery_summary)

    approval_context = _as_dict(review.get("approval_ready_context"))
    review_checklist = [str(item) for item in _as_list(approval_context.get("review_checklist")) if _text(item)]
    review_status = _text(approval_context.get("review_status") or pkg.get("review_status")).lower()
    decision_status = _text(approval_context.get("decision_status") or pkg.get("decision_status")).lower()
    release_status = _text(approval_context.get("release_status") or pkg.get("release_status")).lower()
    requires_human_approval = bool(
        approval_context.get("requires_human_approval")
        or pkg.get("requires_human_approval")
    )
    package_id = _text(pkg.get("package_id") or state.get("execution_package_id"))
    routing_status = _text(routing.get("routing_status")).lower()
    normalized_budget_status = _text(budget_status or preview.get("budget_status") or pkg.get("budget_status")).lower()
    normalized_budget_reason = _text(budget_reason or preview.get("budget_reason") or pkg.get("budget_reason"))
    gov = _governance_flags(state, pkg)
    checkpoint_pending = bool(gov["checkpoint_required"]) and _text(gov["checkpoint_status"]) in {
        "checkpoint_required",
        "blocked_by_hold",
        "hold_release_pending",
        "pending",
    }

    blockers: list[str] = []
    requirements: list[str] = []

    if normalized_scope == "package" and not package_id:
        blockers.append("No active execution package is available for handoff review.")
    if normalized_scope == "project" and not (package_id or has_active_package):
        requirements.append("Prepare or select an execution package before handoff review.")

    if normalized_budget_status in _BUDGET_BLOCKED:
        blockers.append(
            normalized_budget_reason
            or f"Budget posture is {normalized_budget_status} and blocks handoff progression."
        )
    if bool(gov["manual_hold_active"]):
        blockers.append("Manual hold is active and must be released before handoff.")
    if bool(gov["freeze_required"]):
        blockers.append("Freeze controls are active and block handoff progression.")
    if bool(gov["recovery_only_mode"]):
        blockers.append("Recovery-only mode is active; normal handoff is blocked.")
    if checkpoint_pending:
        requirements.append("Complete executive checkpoint approval before handoff.")
    if routing_status == "blocked_by_budget":
        blockers.append("Routing policy is blocked by budget controls.")
    elif routing_status == "deferred_for_review":
        requirements.append("Resolve routing policy review before handoff.")

    if review_status in {"pending", "review_pending", "ready_for_review"}:
        requirements.append("Complete package review before handoff.")
    if review_checklist and review_status not in {"reviewed", "approved", "completed"}:
        requirements.append("Satisfy review checklist requirements before handoff.")
    if _text(guidance.get("guidance_status")).lower() == "awaiting_input":
        requirements.append("Provide missing operator-requested input before handoff.")
    if _text(live.get("operation_status")).lower() == "blocked":
        blockers.append(_text(live.get("idle_reason")) or "Live operation is blocked by governance controls.")

    approval_pending = (
        checkpoint_pending
        or (requires_human_approval and decision_status in {"", "pending", "review_pending", "not_started"})
        or decision_status in {"pending", "review_pending"}
        or release_status in {"pending", "not_started"}
    )

    blockers = _dedupe(blockers)
    requirements = _dedupe(requirements)

    if blockers:
        handoff_status = "handoff_blocked"
        readiness = "low"
        next_action = blockers[0]
    elif normalized_scope == "package" and not package_id:
        handoff_status = "not_ready"
        readiness = "low"
        next_action = "Select or create an execution package for governed handoff review."
    elif requirements and any("Prepare or select an execution package" in item for item in requirements):
        handoff_status = "not_ready"
        readiness = "low"
        next_action = "Prepare or select an execution package before handoff review."
    elif approval_pending:
        handoff_status = "awaiting_approval"
        readiness = "medium"
        next_action = "Obtain required approvals/checkpoints before handoff."
    elif requirements:
        handoff_status = "needs_review"
        readiness = "medium"
        next_action = requirements[0]
    else:
        handoff_status = "ready_for_handoff"
        readiness = "high"
        next_action = "Ready for governed execution handoff review."

    approval_posture = _approval_posture(
        approval_required=requires_human_approval,
        decision_status=decision_status,
        checkpoint_pending=checkpoint_pending,
    )
    budget_note = (
        f"Budget posture: {normalized_budget_status or 'within_budget'}."
        + (f" {normalized_budget_reason}" if normalized_budget_reason else "")
    )
    governance_note = (
        "Governance controls are satisfied for explicit handoff review."
        if not blockers
        else "Governance blockers are present and require explicit operator action."
    )
    routing_note = (
        f"Routing posture: {routing_status}."
        + (f" {_text(routing.get('routing_reason'))}" if _text(routing.get("routing_reason")) else "")
        if routing_status
        else "Routing posture is not explicitly set."
    )
    review_summary = (
        "Handoff blockers detected."
        if handoff_status == "handoff_blocked"
        else "Handoff prerequisites are incomplete."
        if handoff_status == "not_ready"
        else "Awaiting explicit approval/checkpoint signals."
        if handoff_status == "awaiting_approval"
        else "Additional review actions are required before handoff."
        if handoff_status == "needs_review"
        else "All governed checks indicate handoff review readiness."
    )
    if _text(delivery.get("delivery_progress_state")).lower() == "internal_review_required":
        requirements = _dedupe(requirements + ["Complete delivery packaging review before handoff."])
        if handoff_status == "ready_for_handoff":
            handoff_status = "needs_review"
            readiness = "medium"
            next_action = "Complete delivery packaging review before handoff."
            review_summary = "Additional review actions are required before handoff."

    return {
        "handoff_status": _normalize_status(handoff_status),
        "handoff_readiness": _normalize_readiness(readiness),
        "handoff_blockers": blockers,
        "handoff_requirements": requirements,
        "approval_posture": approval_posture,
        "review_summary": review_summary,
        "next_handoff_action": next_action,
        "handoff_scope": normalized_scope,
        "budget_handoff_note": budget_note,
        "governance_handoff_note": governance_note,
        "routing_handoff_note": routing_note,
    }


def build_execution_handoff_review_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return build_execution_handoff_review(**kwargs)
    except Exception as exc:
        return {
            "handoff_status": "handoff_blocked",
            "handoff_readiness": "low",
            "handoff_blockers": [f"Handoff synthesis failed safely: {exc}"],
            "handoff_requirements": [],
            "approval_posture": "unknown",
            "review_summary": "Execution handoff review failed safely and requires operator inspection.",
            "next_handoff_action": "Inspect execution handoff review inputs and retry.",
            "handoff_scope": _normalize_scope(_text(kwargs.get("scope") or "project")),
            "budget_handoff_note": "Budget posture unavailable during handoff synthesis failure.",
            "governance_handoff_note": "Fallback safety posture applied.",
            "routing_handoff_note": "Routing posture unavailable during handoff synthesis failure.",
        }


def build_overview_execution_handoff_review(project_rows: list[dict[str, Any]] | None) -> dict[str, Any]:
    rows = [row for row in _as_list(project_rows) if isinstance(row, dict)]
    if not rows:
        return {
            "handoff_status": "not_ready",
            "handoff_readiness": "low",
            "handoff_blockers": ["No projects are currently available for handoff review."],
            "handoff_requirements": [],
            "approval_posture": "review_in_progress",
            "review_summary": "System has no active project handoff candidates.",
            "next_handoff_action": "Select a project and prepare package context.",
            "handoff_scope": "project",
            "budget_handoff_note": "No budget posture available from project rows.",
            "governance_handoff_note": "No active handoff candidates.",
            "routing_handoff_note": "No routing posture available from project rows.",
        }

    blocked = 0
    review_needed = 0
    approval_pending = 0
    for row in rows:
        budget_status = _text(row.get("budget_status")).lower()
        routing_status = _text(row.get("routing_status")).lower()
        package_id = _text(row.get("current_package_id"))
        if budget_status in _BUDGET_BLOCKED:
            blocked += 1
        elif routing_status in {"deferred_for_review"}:
            review_needed += 1
        elif package_id:
            approval_pending += 1
        else:
            review_needed += 1

    if blocked > 0:
        status = "handoff_blocked"
        readiness = "low"
        summary = f"{blocked} project(s) are blocked for handoff."
        next_action = "Resolve project budget/governance blockers."
    elif approval_pending > 0:
        status = "awaiting_approval"
        readiness = "medium"
        summary = f"{approval_pending} project(s) are awaiting explicit approval before handoff."
        next_action = "Complete pending approvals and checkpoints."
    elif review_needed > 0:
        status = "needs_review"
        readiness = "medium"
        summary = f"{review_needed} project(s) need additional handoff review."
        next_action = "Review package/project readiness details."
    else:
        status = "ready_for_handoff"
        readiness = "high"
        summary = "Projects are ready for governed handoff review."
        next_action = "Proceed with governed execution handoff review."

    return {
        "handoff_status": status,
        "handoff_readiness": readiness,
        "handoff_blockers": [summary] if status == "handoff_blocked" else [],
        "handoff_requirements": [summary] if status in {"needs_review", "awaiting_approval"} else [],
        "approval_posture": "approval_required" if status == "awaiting_approval" else "review_in_progress",
        "review_summary": summary,
        "next_handoff_action": next_action,
        "handoff_scope": "project",
        "budget_handoff_note": "Overview reflects project-level budget and routing posture only.",
        "governance_handoff_note": "Overview is advisory and does not trigger execution.",
        "routing_handoff_note": "Routing decisions remain governed in NEXUS.",
    }


def build_overview_execution_handoff_review_safe(project_rows: list[dict[str, Any]] | None) -> dict[str, Any]:
    try:
        return build_overview_execution_handoff_review(project_rows)
    except Exception as exc:
        return {
            "handoff_status": "handoff_blocked",
            "handoff_readiness": "low",
            "handoff_blockers": [f"Overview handoff synthesis failed safely: {exc}"],
            "handoff_requirements": [],
            "approval_posture": "unknown",
            "review_summary": "System handoff review failed safely.",
            "next_handoff_action": "Inspect overview handoff inputs and retry.",
            "handoff_scope": "project",
            "budget_handoff_note": "Budget posture unavailable.",
            "governance_handoff_note": "Fallback safety posture applied.",
            "routing_handoff_note": "Routing posture unavailable.",
        }
