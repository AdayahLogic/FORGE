"""
Phase 88 operator guidance contract and derivation logic.

Guidance is read-only and advisory. It must never trigger execution, mutate
state, or bypass governance controls.
"""

from __future__ import annotations

from typing import Any


GUIDANCE_STATUSES = {
    "idle",
    "ready_for_review",
    "awaiting_input",
    "blocked",
    "action_recommended",
}
SYSTEM_POSTURES = {"healthy", "caution", "blocked", "needs_attention"}
GUIDANCE_PRIORITIES = {"low", "medium", "high"}
GUIDANCE_SCOPES = {"project", "package", "system"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _normalize_guidance(result: dict[str, Any]) -> dict[str, Any]:
    guidance_status = _text(result.get("guidance_status")).lower()
    if guidance_status not in GUIDANCE_STATUSES:
        guidance_status = "idle"
    system_posture = _text(result.get("system_posture")).lower()
    if system_posture not in SYSTEM_POSTURES:
        system_posture = "healthy"
    priority = _text(result.get("recommended_priority")).lower()
    if priority not in GUIDANCE_PRIORITIES:
        priority = "low"
    scope = _text(result.get("guidance_scope")).lower()
    if scope not in GUIDANCE_SCOPES:
        scope = "project"
    return {
        "guidance_status": guidance_status,
        "system_posture": system_posture,
        "next_best_action": _text(result.get("next_best_action")),
        "action_reason": _text(result.get("action_reason")),
        "blocking_reason": _text(result.get("blocking_reason")),
        "recommended_priority": priority,
        "guidance_scope": scope,
        "governance_alignment": _text(result.get("governance_alignment")),
        "budget_context_note": _text(result.get("budget_context_note")),
        "routing_context_note": _text(result.get("routing_context_note")),
        "delivery_context_note": _text(result.get("delivery_context_note")),
    }


def _base(scope: str) -> dict[str, Any]:
    normalized_scope = _text(scope).lower()
    if normalized_scope not in GUIDANCE_SCOPES:
        normalized_scope = "project"
    return {
        "guidance_status": "idle",
        "system_posture": "healthy",
        "next_best_action": "No action is currently required.",
        "action_reason": "No active package, intake request, or blocking condition was detected.",
        "blocking_reason": "",
        "recommended_priority": "low",
        "guidance_scope": normalized_scope,
        "governance_alignment": (
            "Guidance is advisory only and does not override authority, policy, "
            "or package lifecycle controls."
        ),
        "budget_context_note": "Budget posture is within expected bounds.",
        "routing_context_note": "Model routing remains policy-governed.",
        "delivery_context_note": "No delivery action is currently required.",
    }


def _governance_signals(
    *,
    project_state: dict[str, Any],
    package: dict[str, Any],
    latest_self_change_entry: dict[str, Any],
) -> dict[str, Any]:
    state = _as_dict(project_state)
    pkg = _as_dict(package)
    audit = _as_dict(latest_self_change_entry)

    freeze_required = bool(
        state.get("freeze_required")
        or pkg.get("freeze_required")
        or audit.get("freeze_required")
    )
    recovery_only_mode = bool(
        state.get("recovery_only_mode")
        or pkg.get("recovery_only_mode")
        or audit.get("recovery_only_mode")
    )
    manual_hold_active = bool(
        state.get("manual_hold_active")
        or pkg.get("manual_hold_active")
        or audit.get("manual_hold_active")
    )
    checkpoint_required = bool(
        state.get("checkpoint_required")
        or pkg.get("checkpoint_required")
        or audit.get("checkpoint_required")
    )

    checkpoint_status = (
        _text(state.get("checkpoint_status"))
        or _text(pkg.get("checkpoint_status"))
        or _text(audit.get("checkpoint_status"))
        or "not_required"
    ).lower()
    hold_reason = (
        _text(state.get("hold_reason"))
        or _text(pkg.get("hold_reason"))
        or _text(audit.get("hold_reason"))
    )
    freeze_scope = (
        _text(state.get("freeze_scope"))
        or _text(pkg.get("freeze_scope"))
        or _text(audit.get("freeze_scope"))
        or "project_scoped"
    ).lower()

    return {
        "freeze_required": freeze_required,
        "recovery_only_mode": recovery_only_mode,
        "manual_hold_active": manual_hold_active,
        "checkpoint_required": checkpoint_required,
        "checkpoint_status": checkpoint_status,
        "hold_reason": hold_reason,
        "freeze_scope": freeze_scope,
    }


def _blocked_by_budget(budget_status: str) -> bool:
    return budget_status in {"cap_exceeded", "kill_switch_triggered", "kill_switch_active"}


def build_operator_guidance(
    *,
    scope: str,
    project_state: dict[str, Any] | None = None,
    intake_preview: dict[str, Any] | None = None,
    delivery_summary: dict[str, Any] | None = None,
    model_routing_policy: dict[str, Any] | None = None,
    budget_status: str = "",
    budget_reason: str = "",
    has_active_package: bool = False,
    package: dict[str, Any] | None = None,
    latest_self_change_entry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = _base(scope)
    state = _as_dict(project_state)
    preview = _as_dict(intake_preview)
    delivery = _as_dict(delivery_summary)
    routing = _as_dict(model_routing_policy)
    pkg = _as_dict(package)
    latest_audit = _as_dict(latest_self_change_entry)

    normalized_budget_status = _text(budget_status or preview.get("budget_status") or pkg.get("budget_status")).lower()
    normalized_budget_reason = _text(budget_reason or preview.get("budget_reason") or pkg.get("budget_reason"))
    routing_status = _text(routing.get("routing_status") or preview.get("model_routing_policy", {}).get("routing_status")).lower()
    routing_reason = _text(routing.get("routing_reason") or preview.get("model_routing_policy", {}).get("routing_reason"))
    delivery_state = _text(delivery.get("delivery_progress_state")).lower()

    gov = _governance_signals(
        project_state=state,
        package=pkg,
        latest_self_change_entry=latest_audit,
    )

    if normalized_budget_status:
        out["budget_context_note"] = (
            f"Budget posture is {normalized_budget_status}."
            + (f" {normalized_budget_reason}" if normalized_budget_reason else "")
        )
    if routing_status:
        out["routing_context_note"] = (
            f"Routing policy status is {routing_status}."
            + (f" {routing_reason}" if routing_reason else "")
        )
    if delivery_state:
        out["delivery_context_note"] = f"Delivery summary state is {delivery_state}."

    # Hard blockers first.
    if _blocked_by_budget(normalized_budget_status):
        out.update(
            {
                "guidance_status": "blocked",
                "system_posture": "blocked",
                "next_best_action": "Resolve budget cap before continuing.",
                "action_reason": "Progression is budget-gated and requires explicit operator intervention.",
                "blocking_reason": normalized_budget_reason
                or "Budget controls blocked progression under cap/kill-switch policy.",
                "recommended_priority": "high",
            }
        )
        return _normalize_guidance(out)

    if gov["manual_hold_active"]:
        out.update(
            {
                "guidance_status": "blocked",
                "system_posture": "blocked",
                "next_best_action": "Complete manual hold release requirements before continuing.",
                "action_reason": "A manual hold is actively enforcing a governance pause.",
                "blocking_reason": gov["hold_reason"] or "Manual hold is active.",
                "recommended_priority": "high",
            }
        )
        return _normalize_guidance(out)

    if gov["freeze_required"] or gov["recovery_only_mode"]:
        out.update(
            {
                "guidance_status": "blocked",
                "system_posture": "blocked",
                "next_best_action": "Clear freeze or recovery-only conditions before normal progression.",
                "action_reason": "Governance stability controls require freeze/recovery handling.",
                "blocking_reason": (
                    f"Freeze scope is {gov['freeze_scope']}."
                    if gov["freeze_required"]
                    else "Recovery-only mode is active."
                ),
                "recommended_priority": "high",
            }
        )
        return _normalize_guidance(out)

    if gov["checkpoint_required"] and gov["checkpoint_status"] in {
        "checkpoint_required",
        "blocked_by_hold",
        "hold_release_pending",
        "pending",
    }:
        out.update(
            {
                "guidance_status": "blocked",
                "system_posture": "needs_attention",
                "next_best_action": "Complete executive checkpoint approval.",
                "action_reason": "Checkpoint governance is required before progression.",
                "blocking_reason": f"Checkpoint status is {gov['checkpoint_status']}.",
                "recommended_priority": "high",
            }
        )
        return _normalize_guidance(out)

    # Intake/revenue progression.
    composition = _as_dict(preview.get("composition_status"))
    missing_fields = [str(item) for item in (composition.get("missing_fields") or []) if str(item).strip()]
    readiness = _text(preview.get("readiness")).lower()
    request_kind = _text(preview.get("request_kind")).lower()
    response_status = _text(_as_dict(preview.get("response_summary")).get("response_status")).lower()
    conversion_status = _text(_as_dict(preview.get("conversion_summary")).get("conversion_status")).lower()
    revenue_lane_status = _text(pkg.get("revenue_lane_status")).lower()
    revenue_lane_truth = _as_dict(pkg.get("revenue_lane_truth"))

    if missing_fields or readiness == "needs_input":
        out.update(
            {
                "guidance_status": "awaiting_input",
                "system_posture": "needs_attention",
                "next_best_action": "Provide missing lead details to continue qualification."
                if request_kind == "lead_intake"
                else "Provide missing request composition fields to continue.",
                "action_reason": (
                    "Required intake fields are missing."
                    if request_kind == "lead_intake"
                    else "Required request fields are missing."
                ),
                "blocking_reason": "Missing required fields: " + ", ".join(missing_fields[:6]),
                "recommended_priority": "high",
            }
        )
        return _normalize_guidance(out)

    if revenue_lane_status in {"awaiting_approval", "approved_to_send"} or bool(revenue_lane_truth.get("awaiting_approval")):
        out.update(
            {
                "guidance_status": "awaiting_input",
                "system_posture": "needs_attention",
                "next_best_action": "Approve governed send request before outreach.",
                "action_reason": "Revenue lane is explicitly waiting for human approval before live send.",
                "recommended_priority": "high",
            }
        )
        return _normalize_guidance(out)

    if revenue_lane_status in {"blocked", "failed"} or bool(revenue_lane_truth.get("failed")):
        out.update(
            {
                "guidance_status": "blocked",
                "system_posture": "blocked",
                "next_best_action": "Review failed/blocked send receipt and correct the channel input.",
                "action_reason": "Live revenue channel reported a blocked or failed send attempt.",
                "recommended_priority": "high",
            }
        )
        return _normalize_guidance(out)

    if revenue_lane_status == "send_receipt_exists" and not bool(revenue_lane_truth.get("response_received")):
        out.update(
            {
                "guidance_status": "action_recommended",
                "system_posture": "caution",
                "next_best_action": "Track follow-up and monitor for inbound response.",
                "action_reason": "A governed send receipt exists and response tracking is still pending.",
                "recommended_priority": "medium",
            }
        )
        return _normalize_guidance(out)

    if response_status in {"response_ready", "high_touch_required"}:
        out.update(
            {
                "guidance_status": "ready_for_review",
                "system_posture": "healthy",
                "next_best_action": "Review generated response before client communication.",
                "action_reason": "A response draft exists and should be reviewed under governance.",
                "recommended_priority": "medium",
            }
        )
        return _normalize_guidance(out)

    if conversion_status == "conversion_ready":
        out.update(
            {
                "guidance_status": "action_recommended",
                "system_posture": "healthy",
                "next_best_action": "Approve project conversion to proceed.",
                "action_reason": "Revenue intake progression is ready for governed conversion review.",
                "recommended_priority": "medium",
            }
        )
        return _normalize_guidance(out)

    if delivery_state in {
        "delivery_summary_ready",
        "client_safe_packaging_ready",
        "internal_review_required",
    } or _text(pkg.get("review_status")).lower() in {"ready_for_review", "review_pending", "reviewed", "pending"}:
        out.update(
            {
                "guidance_status": "ready_for_review",
                "system_posture": "caution",
                "next_best_action": "Review delivery package before final approval.",
                "action_reason": "Outputs are available and awaiting explicit review decision.",
                "recommended_priority": "medium",
            }
        )
        return _normalize_guidance(out)

    if has_active_package:
        out.update(
            {
                "guidance_status": "action_recommended",
                "system_posture": "caution",
                "next_best_action": "Complete executive checkpoint approval."
                if gov["checkpoint_required"]
                else "Continue governed package progression in the next review gate.",
                "action_reason": "An active package exists and awaits operator-governed progression.",
                "recommended_priority": "medium",
            }
        )
        return _normalize_guidance(out)

    if readiness == "ready_for_governed_request":
        out.update(
            {
                "guidance_status": "action_recommended",
                "system_posture": "healthy",
                "next_best_action": "Submit the governed intake package for review.",
                "action_reason": "Intake composition is complete and ready for governed review.",
                "recommended_priority": "medium",
            }
        )
        return _normalize_guidance(out)

    return _normalize_guidance(out)


def build_system_operator_guidance(
    *,
    project_rows: list[dict[str, Any]] | None = None,
    self_evolution_governance_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = _base("system")
    rows = [row for row in (project_rows or []) if isinstance(row, dict)]
    governance = _as_dict(self_evolution_governance_summary)

    if not rows:
        out.update(
            {
                "guidance_status": "idle",
                "system_posture": "healthy",
                "next_best_action": "No active project action is required.",
                "action_reason": "No project rows were available for system guidance.",
            }
        )
        return _normalize_guidance(out)

    blocked_budget = [
        row for row in rows if _blocked_by_budget(_text(row.get("budget_status")).lower())
    ]
    if blocked_budget:
        names = ", ".join(str(row.get("project_key") or "") for row in blocked_budget[:3])
        out.update(
            {
                "guidance_status": "blocked",
                "system_posture": "blocked",
                "next_best_action": "Resolve budget cap before continuing.",
                "action_reason": "At least one project is blocked by budget controls.",
                "blocking_reason": f"Budget blocker detected in: {names or 'one or more projects'}.",
                "recommended_priority": "high",
                "budget_context_note": "System-wide budget posture requires intervention.",
            }
        )
        return _normalize_guidance(out)

    hold_count = int(_as_dict(governance.get("manual_hold_active_count_total")).get("active") or 0)
    checkpoint_count = int(_as_dict(governance.get("checkpoint_required_count_total")).get("required") or 0)
    freeze_count = int(governance.get("freeze_required_count_total") or 0)
    if hold_count > 0 or checkpoint_count > 0 or freeze_count > 0:
        out.update(
            {
                "guidance_status": "blocked",
                "system_posture": "needs_attention",
                "next_best_action": "Complete executive checkpoint approval.",
                "action_reason": "Governance controls indicate holds/checkpoints/freezes requiring operator action.",
                "blocking_reason": (
                    f"manual_hold_active={hold_count}, checkpoint_required={checkpoint_count}, "
                    f"freeze_required={freeze_count}"
                ),
                "recommended_priority": "high",
            }
        )
        return _normalize_guidance(out)

    review_ready = [
        row
        for row in rows
        if _text(row.get("routing_status")).lower() in {"deferred_for_review"}
        or _text(row.get("latest_evaluation_status")).lower() in {"pending", "review_pending"}
    ]
    if review_ready:
        out.update(
            {
                "guidance_status": "ready_for_review",
                "system_posture": "caution",
                "next_best_action": "Review generated response before client communication.",
                "action_reason": "One or more projects have review-pending policy or evaluation posture.",
                "recommended_priority": "medium",
            }
        )
        return _normalize_guidance(out)

    out.update(
        {
            "guidance_status": "action_recommended",
            "system_posture": "healthy",
            "next_best_action": "Advance the next governed project gate based on queue priority.",
            "action_reason": "Projects are active with no explicit blockers detected.",
            "recommended_priority": "medium",
        }
    )
    return _normalize_guidance(out)


def build_operator_guidance_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return build_operator_guidance(**kwargs)
    except Exception as exc:
        out = _base(_text(kwargs.get("scope") or "project") or "project")
        out.update(
            {
                "guidance_status": "blocked",
                "system_posture": "needs_attention",
                "next_best_action": "Review operator guidance inputs.",
                "action_reason": "Guidance derivation failed safely.",
                "blocking_reason": f"Guidance error: {exc}",
                "recommended_priority": "high",
            }
        )
        return _normalize_guidance(out)


def build_system_operator_guidance_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return build_system_operator_guidance(**kwargs)
    except Exception as exc:
        out = _base("system")
        out.update(
            {
                "guidance_status": "blocked",
                "system_posture": "needs_attention",
                "next_best_action": "Review system guidance inputs.",
                "action_reason": "System guidance derivation failed safely.",
                "blocking_reason": f"Guidance error: {exc}",
                "recommended_priority": "high",
            }
        )
        return _normalize_guidance(out)
