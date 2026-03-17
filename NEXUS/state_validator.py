"""
NEXUS project-state validator.

Compact deterministic validation for persisted project state. Not a schema
framework; provides a few high-value consistency checks for stability.
"""

from __future__ import annotations

from typing import Any


def _issue(code: str, message: str, severity: str = "warning", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "severity": severity,
        "metadata": metadata or {},
    }


def validate_project_state(*, state: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Validate loaded project state dict. Returns stable shape:
    { validation_status, validation_reason, state_repair_recommended, issues }
    """
    s = state or {}
    issues: list[dict[str, Any]] = []

    if not isinstance(s, dict):
        return {
            "validation_status": "blocked",
            "validation_reason": "Project state is not a dict.",
            "state_repair_recommended": True,
            "issues": [_issue("state_not_dict", "Project state is not a dict.", "blocked")],
        }

    # Missing essential fields (only warn; older states may lack fields)
    if not s.get("saved_at"):
        issues.append(_issue("missing_saved_at", "Missing saved_at.", "warning"))
    if not s.get("active_project"):
        issues.append(_issue("missing_active_project", "Missing active_project.", "warning"))

    qe = s.get("review_queue_entry") or {}
    rec = s.get("recovery_result") or {}
    sr = s.get("scheduler_result") or {}
    rex = s.get("reexecution_result") or {}
    lr = s.get("launch_result") or {}

    # 1) Queue cleared but recovery still awaiting review/approval
    q_status = (qe.get("queue_status") or "").strip().lower()
    rec_action = (rec.get("recovery_action") or "").strip().lower()
    rec_status = (rec.get("recovery_status") or "").strip().lower()
    if q_status == "cleared" and rec_status in ("waiting", "blocked") and rec_action in ("await_review", "await_approval"):
        issues.append(
            _issue(
                "queue_cleared_recovery_waiting",
                "Queue is cleared but recovery still indicates await_review/await_approval.",
                "warning",
                {"queue_status": q_status, "recovery_status": rec_status, "recovery_action": rec_action},
            )
        )

    # 2) Scheduler says scheduled but reexecution run_permitted is false
    sched_status = (s.get("scheduler_status") or sr.get("scheduler_status") or "").strip().lower()
    if sched_status == "scheduled" and rex.get("run_permitted") is False:
        issues.append(
            _issue(
                "scheduled_but_run_not_permitted",
                "Scheduler indicates scheduled but reexecution.run_permitted is false.",
                "warning",
                {"scheduler_status": sched_status, "run_permitted": rex.get("run_permitted")},
            )
        )

    # 3) launch_status says launched but launch_result.execution_started is false
    launch_status = (s.get("launch_status") or lr.get("launch_status") or "").strip().lower()
    if launch_status == "launched" and lr.get("execution_started") is False:
        issues.append(
            _issue(
                "launched_but_not_started",
                "launch_status is launched but launch_result.execution_started is false.",
                "warning",
                {"launch_status": launch_status, "execution_started": lr.get("execution_started")},
            )
        )

    # 4) Unknown / malformed enum-like values in key fields (only if present)
    allowed_queue_status = {"queued", "not_queued", "cleared", "none", "error_fallback", ""}
    if q_status and q_status not in allowed_queue_status:
        issues.append(_issue("unknown_queue_status", f"Unknown queue_status '{q_status}'.", "warning"))

    allowed_reexecution_status = {"ready", "waiting", "blocked", "idle", "error_fallback", "none", ""}
    rex_status = (s.get("reexecution_status") or rex.get("reexecution_status") or "").strip().lower()
    if rex_status and rex_status not in allowed_reexecution_status:
        issues.append(_issue("unknown_reexecution_status", f"Unknown reexecution_status '{rex_status}'.", "warning"))

    # Severity aggregation
    blocked = any(i.get("severity") == "blocked" for i in issues)
    has_issues = len(issues) > 0
    if blocked:
        return {
            "validation_status": "blocked",
            "validation_reason": "Blocked by validation issues.",
            "state_repair_recommended": True,
            "issues": issues,
        }
    if has_issues:
        return {
            "validation_status": "warning",
            "validation_reason": "State has validation warnings.",
            "state_repair_recommended": any(i.get("code") in ("queue_cleared_recovery_waiting",) for i in issues),
            "issues": issues,
        }
    return {
        "validation_status": "passed",
        "validation_reason": "",
        "state_repair_recommended": False,
        "issues": [],
    }


def validate_project_state_safe(state: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises; returns error_fallback on exception."""
    try:
        return validate_project_state(state=state)
    except Exception:
        return {
            "validation_status": "error_fallback",
            "validation_reason": "State validation failed.",
            "state_repair_recommended": False,
            "issues": [],
        }

