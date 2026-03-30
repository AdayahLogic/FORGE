"""
Phase 90 operator quick actions.

Quick actions are context-derived suggestions only.
They never execute governance, approval, or package mutations automatically.
"""

from __future__ import annotations

from typing import Any


ALLOWED_ACTION_KINDS = {"navigate", "refresh", "review", "input_request", "inspect"}
ALLOWED_ACTION_SCOPES = {"system", "project", "package"}

_BUDGET_BLOCKED_STATES = {
    "cap_exceeded",
    "kill_switch_active",
    "kill_switch_triggered",
    "blocked_by_budget",
}


def _to_text(value: Any) -> str:
    return str(value or "").strip()


def _budget_state(value: Any) -> str:
    state = _to_text(value).lower()
    if state == "kill_switch_triggered":
        return "kill_switch_active"
    return state


def _budget_blocked(value: Any) -> bool:
    return _budget_state(value) in _BUDGET_BLOCKED_STATES


def _action(
    *,
    action_id: str,
    action_label: str,
    action_kind: str,
    action_scope: str,
    action_enabled: bool,
    action_reason: str,
    blocked_reason: str = "",
) -> dict[str, Any]:
    kind = action_kind if action_kind in ALLOWED_ACTION_KINDS else "inspect"
    scope = action_scope if action_scope in ALLOWED_ACTION_SCOPES else "project"
    enabled = bool(action_enabled)
    blocked = _to_text(blocked_reason)
    reason = _to_text(action_reason)
    if not enabled and not blocked:
        blocked = reason or "Action is currently blocked by governed state."
    return {
        "action_id": _to_text(action_id),
        "action_label": _to_text(action_label),
        "action_kind": kind,
        "action_scope": scope,
        "action_enabled": enabled,
        "action_reason": reason,
        "blocked_reason": blocked if not enabled else "",
    }


def _contract(actions: list[dict[str, Any]], none_reason: str) -> dict[str, Any]:
    normalized = [item for item in actions if isinstance(item, dict) and _to_text(item.get("action_id"))]
    if not normalized:
        return {
            "quick_actions_status": "none",
            "available_actions": [],
            "quick_actions_reason": _to_text(none_reason) or "No relevant operator quick actions are available.",
        }
    if any(bool(item.get("action_enabled")) for item in normalized):
        status = "available"
        reason = "Context-derived operator quick actions are available."
    else:
        status = "blocked"
        reason = "Quick actions exist but are blocked by current governed constraints."
    return {
        "quick_actions_status": status,
        "available_actions": normalized,
        "quick_actions_reason": reason,
    }


def build_intake_preview_quick_actions(preview: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(preview or {})
    actions: list[dict[str, Any]] = []
    composition = dict(payload.get("composition_status") or {})
    missing_fields = [str(item) for item in list(composition.get("missing_fields") or []) if _to_text(item)]
    warnings = [str(item) for item in list(payload.get("warnings") or []) if _to_text(item)]
    request_kind = _to_text(payload.get("request_kind"))
    response_status = _to_text((payload.get("response_summary") or {}).get("response_status")).lower()
    conversion_status = _to_text((payload.get("conversion_summary") or {}).get("conversion_status")).lower()
    budget_status = _budget_state(payload.get("budget_status"))

    if missing_fields:
        actions.append(
            _action(
                action_id="input_request_missing_fields",
                action_label="Provide missing qualification fields" if request_kind == "lead_intake" else "Provide missing intake fields",
                action_kind="input_request",
                action_scope="project",
                action_enabled=True,
                action_reason=f"Missing required inputs: {', '.join(missing_fields[:4])}.",
            )
        )
    if warnings:
        actions.append(
            _action(
                action_id="inspect_preview_warnings",
                action_label="Inspect preview warnings",
                action_kind="inspect",
                action_scope="project",
                action_enabled=True,
                action_reason="Preview warnings are present and need operator attention.",
            )
        )
    if response_status in {"response_ready", "high_touch_required", "needs_more_info"}:
        actions.append(
            _action(
                action_id="review_generated_response",
                action_label="Review generated response",
                action_kind="review",
                action_scope="project",
                action_enabled=True,
                action_reason="A governed response draft is available for operator review.",
            )
        )
    if conversion_status in {"conversion_ready", "conversion_needs_review", "high_touch_conversion_required"}:
        actions.append(
            _action(
                action_id="inspect_conversion_preview",
                action_label="Inspect project conversion preview",
                action_kind="inspect",
                action_scope="project",
                action_enabled=True,
                action_reason="Conversion preview context is available for manual review.",
            )
        )
    if _budget_blocked(budget_status):
        actions.append(
            _action(
                action_id="inspect_budget_blockers",
                action_label="View budget blocker details",
                action_kind="inspect",
                action_scope="project",
                action_enabled=False,
                action_reason="Budget controls are currently blocking progression.",
                blocked_reason=f"Budget status is {budget_status}.",
            )
        )
    return _contract(actions, "No intake quick actions are relevant yet.")


def build_overview_quick_actions(project_rows: list[dict[str, Any]] | None) -> dict[str, Any]:
    rows = [item for item in list(project_rows or []) if isinstance(item, dict)]
    actions: list[dict[str, Any]] = []
    blocked_budget_rows = [
        row for row in rows if _budget_blocked(row.get("budget_status")) or bool(row.get("kill_switch_active"))
    ]
    review_ready_rows = [
        row
        for row in rows
        if _to_text(row.get("current_package_id")) and _to_text(row.get("latest_evaluation_status")).lower() in {"pending", "ready_for_review", "review_pending"}
    ]
    if review_ready_rows:
        actions.append(
            _action(
                action_id="navigate_review_center",
                action_label="Open review center",
                action_kind="navigate",
                action_scope="system",
                action_enabled=True,
                action_reason="At least one project has an active package needing review context.",
            )
        )
    if blocked_budget_rows:
        actions.append(
            _action(
                action_id="inspect_budget_blockers",
                action_label="View budget blocker details",
                action_kind="inspect",
                action_scope="system",
                action_enabled=False,
                action_reason="One or more projects are blocked by budget controls.",
                blocked_reason=f"{len(blocked_budget_rows)} project(s) are budget-blocked.",
            )
        )
    if rows:
        actions.append(
            _action(
                action_id="refresh_system_overview",
                action_label="Refresh system overview",
                action_kind="refresh",
                action_scope="system",
                action_enabled=True,
                action_reason="Refresh to pull latest governed status and queue updates.",
            )
        )
    return _contract(actions, "No system-level quick actions are currently relevant.")


def build_project_quick_actions(
    *,
    project_state: dict[str, Any] | None,
    workflow_activity: dict[str, Any] | None,
    intake_preview: dict[str, Any] | None,
    delivery_summary: dict[str, Any] | None,
    cost_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    state = dict(project_state or {})
    workflow = dict(workflow_activity or {})
    preview = dict(intake_preview or {})
    delivery = dict(delivery_summary or {})
    costs = dict(cost_summary or {})
    actions: list[dict[str, Any]] = []
    missing_fields = [str(item) for item in list((preview.get("composition_status") or {}).get("missing_fields") or []) if _to_text(item)]
    budget_status = _budget_state(costs.get("budget_status") or preview.get("budget_status") or state.get("budget_status"))
    active_package_id = _to_text(workflow.get("active_package_id") or state.get("execution_package_id"))
    lane_status = _to_text(state.get("revenue_lane_status")).lower()

    if missing_fields:
        actions.append(
            _action(
                action_id="input_request_missing_fields",
                action_label="Provide missing qualification fields" if _to_text(preview.get("request_kind")) == "lead_intake" else "Provide missing intake fields",
                action_kind="input_request",
                action_scope="project",
                action_enabled=True,
                action_reason=f"Missing fields prevent a complete governed preview: {', '.join(missing_fields[:4])}.",
            )
        )
    if active_package_id:
        actions.append(
            _action(
                action_id="inspect_current_package",
                action_label="Inspect package details",
                action_kind="inspect",
                action_scope="package",
                action_enabled=True,
                action_reason="An active package is present for this project.",
            )
        )
        actions.append(
            _action(
                action_id="open_review_context",
                action_label="Open review context",
                action_kind="review",
                action_scope="package",
                action_enabled=True,
                action_reason="Review center can be used to inspect approval and evidence context.",
            )
        )
    if lane_status in {"awaiting_approval", "approved_to_send"}:
        actions.append(
            _action(
                action_id="approve_revenue_send",
                action_label="Approve revenue send",
                action_kind="review",
                action_scope="package",
                action_enabled=True,
                action_reason="Revenue lane is waiting for explicit approval before live send.",
            )
        )
    if lane_status in {"blocked", "failed"}:
        actions.append(
            _action(
                action_id="inspect_send_failure",
                action_label="Inspect send failure receipts",
                action_kind="inspect",
                action_scope="package",
                action_enabled=True,
                action_reason="Revenue send attempt was blocked or failed and needs operator correction.",
            )
        )
    if int(delivery.get("delivered_artifact_count") or 0) > 0:
        actions.append(
            _action(
                action_id="open_delivery_summary",
                action_label="Open delivery summary",
                action_kind="inspect",
                action_scope="project",
                action_enabled=True,
                action_reason="Client-ready delivery summary artifacts are available.",
            )
        )
    if _budget_blocked(budget_status):
        actions.append(
            _action(
                action_id="inspect_budget_blockers",
                action_label="View budget blocker details",
                action_kind="inspect",
                action_scope="project",
                action_enabled=False,
                action_reason="Budget controls are blocking governed progression.",
                blocked_reason=f"Budget status is {budget_status}.",
            )
        )
    actions.append(
        _action(
            action_id="refresh_project_snapshot",
            action_label="Refresh project state",
            action_kind="refresh",
            action_scope="project",
            action_enabled=True,
            action_reason="Refresh to update project, package, and policy visibility.",
        )
    )
    return _contract(actions, "No project quick actions are currently relevant.")


def build_review_center_quick_actions(
    *,
    review_center: dict[str, Any] | None,
    package_json: dict[str, Any] | None,
    cost_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    center = dict(review_center or {})
    package = dict(package_json or {})
    costs = dict(cost_summary or {})
    approval = dict(center.get("approval_ready_context") or {})
    actions: list[dict[str, Any]] = []
    review_status = _to_text(approval.get("review_status") or package.get("review_status")).lower()
    requires_approval = bool(approval.get("requires_human_approval"))
    attachment_count = len(list(center.get("related_attachments") or []))
    delivery_state = _to_text((center.get("delivery_summary") or {}).get("delivery_progress_state")).lower()
    budget_status = _budget_state(costs.get("budget_status") or package.get("budget_status"))

    if requires_approval or review_status in {"pending", "review_pending", "ready_for_review", "reviewed"}:
        actions.append(
            _action(
                action_id="review_generated_response",
                action_label="Review generated response",
                action_kind="review",
                action_scope="package",
                action_enabled=True,
                action_reason="Package review context is active and requires manual operator review.",
            )
        )
    if attachment_count > 0:
        actions.append(
            _action(
                action_id="inspect_package_attachments",
                action_label="View blocker details",
                action_kind="inspect",
                action_scope="package",
                action_enabled=True,
                action_reason="Related attachments are available for deeper review context.",
            )
        )
    if delivery_state in {"delivery_summary_ready", "client_safe_packaging_ready", "internal_review_required"}:
        actions.append(
            _action(
                action_id="open_delivery_summary",
                action_label="Open delivery summary",
                action_kind="inspect",
                action_scope="package",
                action_enabled=True,
                action_reason="Delivery summary packaging context is available.",
            )
        )
    if _budget_blocked(budget_status):
        actions.append(
            _action(
                action_id="inspect_budget_blockers",
                action_label="View budget blocker details",
                action_kind="inspect",
                action_scope="package",
                action_enabled=False,
                action_reason="Budget controls currently block package progression.",
                blocked_reason=f"Budget status is {budget_status}.",
            )
        )
    actions.append(
        _action(
            action_id="refresh_package_snapshot",
            action_label="Refresh package review state",
            action_kind="refresh",
            action_scope="package",
            action_enabled=True,
            action_reason="Refresh to sync review evidence and package lifecycle state.",
        )
    )
    return _contract(actions, "No package review quick actions are currently relevant.")

