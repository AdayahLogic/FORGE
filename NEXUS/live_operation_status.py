"""
Phase 89: Live operation loop visibility.

Read-only synthesis of current operation posture from existing governed state.
This module does not mutate project, package, or workflow records.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


LIVE_OPERATION_STATES = {"idle", "running", "awaiting_review", "blocked", "completed"}
MAX_ACTIVITY_ENTRIES = 8
MAX_ACTIVITY_SUMMARY_LEN = 140


def _now_iso() -> str:
    return datetime.now().isoformat()


def _clean_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    compact = " ".join(text.replace("\n", " ").replace("\r", " ").split())
    return compact


def _status_key(value: Any) -> str:
    return _clean_text(value).lower()


def _pretty(value: str) -> str:
    text = _clean_text(value)
    if not text:
        return "Unknown"
    return " ".join(part.capitalize() for part in text.replace("_", " ").replace("-", " ").split())


def _activity(timestamp: str, activity_type: str, summary: str) -> dict[str, str]:
    safe_summary = _clean_text(summary)
    if len(safe_summary) > MAX_ACTIVITY_SUMMARY_LEN:
        safe_summary = safe_summary[: MAX_ACTIVITY_SUMMARY_LEN - 3].rstrip() + "..."
    return {
        "timestamp": _clean_text(timestamp, _now_iso()),
        "activity_type": _clean_text(activity_type, "status_update"),
        "activity_summary": safe_summary or "Status updated.",
    }


def _derive_block_reason(
    *,
    project_state: dict[str, Any],
    package: dict[str, Any],
    cost_summary: dict[str, Any],
) -> str:
    budget_status = _status_key(cost_summary.get("budget_status"))
    if budget_status in {"cap_exceeded", "kill_switch_triggered"} or bool(cost_summary.get("kill_switch_active")):
        return "Blocked by budget."
    if _status_key(package.get("release_status")) == "blocked":
        return "Blocked by executive checkpoint."
    if _status_key(package.get("handoff_status")) == "blocked":
        return "Blocked by handoff authorization."
    if _status_key(package.get("execution_status")) in {"blocked", "failed", "error_fallback", "rolled_back"}:
        return "Blocked by execution controls."
    enforcement_status = _status_key(project_state.get("enforcement_status"))
    if enforcement_status in {"blocked", "hold", "frozen", "quarantined"}:
        return f"Blocked by enforcement: {_pretty(enforcement_status)}."
    governance_status = _status_key(project_state.get("governance_status"))
    if governance_status in {"blocked", "hold", "frozen", "denied"}:
        return f"Blocked by governance: {_pretty(governance_status)}."
    return "Blocked by governance controls."


def _derive_idle_reason(
    *,
    project_key: str,
    project_state: dict[str, Any],
    package: dict[str, Any],
    cost_summary: dict[str, Any],
) -> str:
    if not _clean_text(project_key):
        return "No active project."
    if _status_key(cost_summary.get("budget_status")) in {"cap_exceeded", "kill_switch_triggered"}:
        return "Blocked by budget."
    if bool(cost_summary.get("kill_switch_active")):
        return "Blocked by budget."
    review_status = _status_key(package.get("review_status"))
    if review_status in {"pending", "review_pending", "ready_for_review"}:
        return "Awaiting review."
    if _status_key(package.get("release_status")) == "blocked":
        return "Blocked by executive checkpoint."
    if _status_key(package.get("package_id")):
        return "Awaiting operator input."
    if not _status_key(project_state.get("execution_package_id")):
        return "No active package."
    return "Awaiting operator input."


def _derive_operation_status(
    *,
    project_state: dict[str, Any],
    package: dict[str, Any],
    cost_summary: dict[str, Any],
) -> str:
    blocked_states = {"blocked", "failed", "denied", "rejected", "error_fallback", "rolled_back"}
    if _status_key(cost_summary.get("budget_status")) in {"cap_exceeded", "kill_switch_triggered"}:
        return "blocked"
    if bool(cost_summary.get("kill_switch_active")):
        return "blocked"
    for field in ("review_status", "decision_status", "release_status", "handoff_status", "execution_status"):
        if _status_key(package.get(field)) in blocked_states:
            return "blocked"
    if _status_key(project_state.get("enforcement_status")) in {"blocked", "hold", "frozen", "quarantined"}:
        return "blocked"
    if _status_key(project_state.get("governance_status")) in {"blocked", "hold", "frozen", "denied"}:
        return "blocked"

    review_status = _status_key(package.get("review_status"))
    if review_status in {"pending", "review_pending", "ready_for_review"}:
        return "awaiting_review"

    execution_status = _status_key(package.get("execution_status"))
    decision_status = _status_key(package.get("decision_status"))
    release_status = _status_key(package.get("release_status"))
    if (
        execution_status in {"succeeded", "completed"}
        or decision_status == "approved"
        or release_status == "released"
    ):
        return "completed"

    has_active_package = bool(_clean_text(package.get("package_id")) or _clean_text(project_state.get("execution_package_id")))
    lifecycle_status = _status_key(project_state.get("project_lifecycle_status"))
    if has_active_package or lifecycle_status in {"active", "running", "queued"}:
        return "running"
    return "idle"


def _derive_phase_step(
    *,
    operation_status: str,
    package: dict[str, Any],
    project_state: dict[str, Any],
) -> tuple[str, str]:
    if operation_status == "blocked":
        if _status_key(package.get("release_status")) == "blocked":
            return "release", "Checkpoint block"
        if _status_key(package.get("execution_status")) in {"blocked", "failed", "rolled_back"}:
            return "execution", "Blocked execution"
        return "governance", "Control block"
    if operation_status == "awaiting_review":
        return "review", "Awaiting review"
    if operation_status == "completed":
        if _status_key(package.get("release_status")) == "released":
            return "delivery", "Released"
        if _status_key(package.get("decision_status")) == "approved":
            return "approval", "Approved"
        return "execution", "Completed"

    execution_status = _status_key(package.get("execution_status"))
    if execution_status in {"ready", "running", "pending", "in_progress"}:
        return "execution", _pretty(execution_status)
    handoff_status = _status_key(package.get("handoff_status"))
    if handoff_status and handoff_status not in {"pending", "not_started"}:
        return "handoff", _pretty(handoff_status)
    release_status = _status_key(package.get("release_status"))
    if release_status and release_status not in {"pending", "not_started"}:
        return "release", _pretty(release_status)
    decision_status = _status_key(package.get("decision_status"))
    if decision_status and decision_status not in {"pending", "not_started"}:
        return "approval", _pretty(decision_status)
    if _clean_text(project_state.get("execution_package_id")):
        return "planning", "Package active"
    if operation_status == "idle":
        return "idle", "Waiting for input"
    return "planning", "Planning"


def _derive_last_action(
    *,
    package: dict[str, Any],
    project_state: dict[str, Any],
    delivery_summary: dict[str, Any],
) -> str:
    if _status_key(package.get("execution_status")) in {"succeeded", "completed"}:
        return "Execution completed."
    if _status_key(package.get("release_status")) == "released":
        return "Package released."
    if _status_key(package.get("decision_status")) == "approved":
        return "Package approved."
    if _status_key(package.get("review_status")) in {"pending", "review_pending", "ready_for_review"}:
        return "Review requested."
    if _status_key(delivery_summary.get("delivery_progress_state")) in {"delivery_summary_ready", "client_safe_packaging_ready"}:
        return "Delivery summary ready."
    if _clean_text(project_state.get("workflow_route_reason")):
        return _clean_text(project_state.get("workflow_route_reason"))
    if _clean_text(package.get("package_id")):
        return "Package created."
    return "Waiting for input."


def _build_recent_activity(
    *,
    package: dict[str, Any],
    project_state: dict[str, Any],
    cost_summary: dict[str, Any],
    delivery_summary: dict[str, Any],
) -> list[dict[str, str]]:
    created_at = _clean_text(package.get("created_at"), _clean_text(project_state.get("saved_at"), _now_iso()))
    activity: list[dict[str, str]] = []
    package_id = _clean_text(package.get("package_id") or project_state.get("execution_package_id"))
    if package_id:
        activity.append(_activity(created_at, "package_created", "Execution package created."))
    if _status_key(package.get("review_status")) in {"pending", "review_pending", "ready_for_review"}:
        activity.append(_activity(created_at, "review_awaited", "Package is awaiting review."))
    if _status_key(cost_summary.get("budget_status")) in {"cap_exceeded", "kill_switch_triggered"} or bool(cost_summary.get("kill_switch_active")):
        activity.append(_activity(created_at, "budget_block", "Budget control blocked progression."))
    progress = _status_key(delivery_summary.get("delivery_progress_state"))
    if progress in {"delivery_summary_ready", "client_safe_packaging_ready"}:
        activity.append(_activity(created_at, "delivery_summary_ready", "Delivery summary is ready."))
    analysis_summary = package.get("local_analysis_summary")
    if isinstance(analysis_summary, dict) and _clean_text(analysis_summary.get("suggested_next_action")):
        activity.append(_activity(created_at, "operator_guidance_updated", "Operator guidance was updated."))
    if not activity:
        activity.append(_activity(_clean_text(project_state.get("saved_at"), _now_iso()), "idle", "No recent governed activity."))
    return activity[:MAX_ACTIVITY_ENTRIES]


def build_live_operation_status(
    *,
    project_key: str,
    project_name: str,
    project_state: dict[str, Any] | None,
    package: dict[str, Any] | None,
    cost_summary: dict[str, Any] | None = None,
    delivery_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = dict(project_state or {})
    pkg = dict(package or {})
    costs = dict(cost_summary or {})
    delivery = dict(delivery_summary or {})

    operation_status = _derive_operation_status(project_state=state, package=pkg, cost_summary=costs)
    phase, step = _derive_phase_step(operation_status=operation_status, package=pkg, project_state=state)
    last_action = _derive_last_action(package=pkg, project_state=state, delivery_summary=delivery)

    idle_reason = ""
    if operation_status == "idle":
        idle_reason = _derive_idle_reason(
            project_key=project_key,
            project_state=state,
            package=pkg,
            cost_summary=costs,
        )
    elif operation_status == "blocked":
        idle_reason = _derive_block_reason(
            project_state=state,
            package=pkg,
            cost_summary=costs,
        )

    payload = {
        "operation_status": operation_status if operation_status in LIVE_OPERATION_STATES else "idle",
        "current_phase": phase,
        "current_step": step,
        "last_action": last_action,
        "idle_reason": idle_reason,
        "active_project": _clean_text(project_name or project_key),
        "active_package_id": _clean_text(pkg.get("package_id") or state.get("execution_package_id")),
        "recent_activity": _build_recent_activity(
            package=pkg,
            project_state=state,
            cost_summary=costs,
            delivery_summary=delivery,
        ),
    }
    return payload


def build_overview_live_operation_status(
    *,
    project_rows: list[dict[str, Any]] | None,
    dashboard: dict[str, Any] | None,
) -> dict[str, Any]:
    rows = [row for row in list(project_rows or []) if isinstance(row, dict)]
    dash = dict(dashboard or {})
    if not rows:
        return {
            "operation_status": "idle",
            "current_phase": "idle",
            "current_step": "Waiting for input",
            "last_action": "No active project.",
            "idle_reason": "No active project.",
            "active_project": "",
            "active_package_id": "",
            "recent_activity": [_activity(_clean_text(dash.get("summary_generated_at"), _now_iso()), "idle", "No active projects in queue.")],
        }

    def _priority(row: dict[str, Any]) -> tuple[int, int]:
        if _status_key(row.get("budget_status")) in {"cap_exceeded", "kill_switch_triggered"} or bool(row.get("kill_switch_active")):
            return (5, 1)
        if _status_key(row.get("routing_status")) in {"blocked_by_budget", "deferred_for_review"}:
            return (4, 1)
        if _clean_text(row.get("current_package_id")):
            return (3, 1)
        lifecycle = _status_key(row.get("lifecycle_status"))
        if lifecycle in {"active", "running", "queued"}:
            return (2, 1)
        return (1, 0)

    selected = sorted(rows, key=_priority, reverse=True)[0]
    operation_status = "running"
    idle_reason = ""
    budget_status = _status_key(selected.get("budget_status"))
    routing_status = _status_key(selected.get("routing_status"))
    if budget_status in {"cap_exceeded", "kill_switch_triggered"} or bool(selected.get("kill_switch_active")):
        operation_status = "blocked"
        idle_reason = "Blocked by budget."
    elif routing_status == "deferred_for_review":
        operation_status = "awaiting_review"
        idle_reason = "Awaiting review."
    elif routing_status == "blocked_by_budget":
        operation_status = "blocked"
        idle_reason = "Blocked by budget."
    elif not _clean_text(selected.get("current_package_id")) and _status_key(selected.get("lifecycle_status")) not in {"active", "running", "queued"}:
        operation_status = "idle"
        idle_reason = "No active package."

    recent_activity = [
        _activity(
            _clean_text(dash.get("summary_generated_at"), _now_iso()),
            "overview_status",
            f"Overview synchronized for project {_clean_text(selected.get('project_name') or selected.get('project_key'), 'unknown')}.",
        )
    ]
    if operation_status == "awaiting_review":
        recent_activity.append(
            _activity(
                _clean_text(dash.get("summary_generated_at"), _now_iso()),
                "review_awaited",
                "At least one package is awaiting review.",
            )
        )
    if operation_status == "blocked":
        recent_activity.append(
            _activity(
                _clean_text(dash.get("summary_generated_at"), _now_iso()),
                "blocker",
                idle_reason or "At least one project is blocked.",
            )
        )

    return {
        "operation_status": operation_status,
        "current_phase": "overview",
        "current_step": "Monitoring governed workflow",
        "last_action": "Dashboard summary refreshed.",
        "idle_reason": idle_reason,
        "active_project": _clean_text(selected.get("project_name") or selected.get("project_key")),
        "active_package_id": _clean_text(selected.get("current_package_id")),
        "recent_activity": recent_activity[:MAX_ACTIVITY_ENTRIES],
    }
