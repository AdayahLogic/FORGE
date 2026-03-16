"""
NEXUS project lifecycle evaluation layer.

Centralized evaluation of project lifecycle from orchestration state.
Produces normalized lifecycle status, stage, and recommended action.
Evaluation-only: no side effects, no destructive actions.
"""

from __future__ import annotations

from typing import Any


def evaluate_project_lifecycle(
    *,
    active_project: str | None = None,
    project_path: str | None = None,
    dispatch_status: str | None = None,
    runtime_execution_status: str | None = None,
    automation_status: str | None = None,
    governance_status: str | None = None,
    governance_result: dict[str, Any] | None = None,
    automation_result: dict[str, Any] | None = None,
    dispatch_result: dict[str, Any] | None = None,
    existing_project_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Evaluate current project lifecycle from orchestration and project state.

    Returns stable schema:
    {
      "lifecycle_status": "planned" | "active" | "paused" | "blocked" | "archived" | "error_fallback",
      "lifecycle_stage": "planning" | "routing" | "dispatch_ready" | "execution_ready" | "governance_review" | "stalled" | "archival_candidate" | "unknown",
      "recommended_lifecycle_action": str,
      "reason": str,
      "is_active": bool,
      "is_blocked": bool,
      "is_archived": bool
    }
    """
    g_status = (governance_status or "").strip().lower()
    gr = governance_result or {}
    ds = (dispatch_status or "").strip().lower()
    es = (runtime_execution_status or "").strip().lower()
    a_status = (automation_status or "").strip().lower()
    existing = existing_project_state or {}

    blocked = gr.get("blocked") is True

    # Governance blocked -> lifecycle blocked, governance_review
    if blocked or g_status == "blocked":
        return {
            "lifecycle_status": "blocked",
            "lifecycle_stage": "governance_review",
            "recommended_lifecycle_action": "resolve_blockers",
            "reason": gr.get("decision_reason") or "Governance blocked.",
            "is_active": False,
            "is_blocked": True,
            "is_archived": False,
        }

    # Review/approval required -> blocked for lifecycle purposes
    if g_status in ("review_required", "approval_required"):
        return {
            "lifecycle_status": "blocked",
            "lifecycle_stage": "governance_review",
            "recommended_lifecycle_action": "resolve_blockers",
            "reason": gr.get("decision_reason") or "Governance review or approval required.",
            "is_active": False,
            "is_blocked": True,
            "is_archived": False,
        }

    # Approved + accepted -> active, execution_ready
    if g_status == "approved" and ds == "accepted":
        return {
            "lifecycle_status": "active",
            "lifecycle_stage": "execution_ready",
            "recommended_lifecycle_action": "continue",
            "reason": "Governance approved; dispatch accepted.",
            "is_active": True,
            "is_blocked": False,
            "is_archived": False,
        }

    # Dispatch error -> blocked, stalled
    if ds == "error":
        return {
            "lifecycle_status": "blocked",
            "lifecycle_stage": "stalled",
            "recommended_lifecycle_action": "inspect_dispatch_error",
            "reason": (dispatch_result or {}).get("message") or "Dispatch error.",
            "is_active": False,
            "is_blocked": True,
            "is_archived": False,
        }

    # Skipped / no_adapter -> paused or blocked, stalled
    if ds in ("skipped", "no_adapter"):
        return {
            "lifecycle_status": "paused",
            "lifecycle_stage": "stalled",
            "recommended_lifecycle_action": "inspect_runtime_path",
            "reason": "Dispatch skipped or no adapter; runtime path needs attention.",
            "is_active": False,
            "is_blocked": False,
            "is_archived": False,
        }

    # Runtime execution blocked
    if es == "blocked":
        return {
            "lifecycle_status": "blocked",
            "lifecycle_stage": "governance_review",
            "recommended_lifecycle_action": "resolve_blockers",
            "reason": "Runtime execution is blocked.",
            "is_active": False,
            "is_blocked": True,
            "is_archived": False,
        }

    # Has meaningful state (dispatch_plan_summary ready, etc.) -> dispatch_ready or routing
    dps = existing.get("dispatch_plan_summary") or {}
    if dps.get("ready_for_dispatch"):
        return {
            "lifecycle_status": "active",
            "lifecycle_stage": "dispatch_ready",
            "recommended_lifecycle_action": "continue",
            "reason": "Dispatch plan ready; awaiting dispatch.",
            "is_active": True,
            "is_blocked": False,
            "is_archived": False,
        }

    # Has architect_plan or task_queue -> planning
    if existing.get("architect_plan") or existing.get("task_queue"):
        return {
            "lifecycle_status": "planned",
            "lifecycle_stage": "planning",
            "recommended_lifecycle_action": "continue_planning",
            "reason": "Project has plan or task queue; lifecycle in planning.",
            "is_active": False,
            "is_blocked": False,
            "is_archived": False,
        }

    # Minimal or no known state
    if active_project or project_path:
        return {
            "lifecycle_status": "planned",
            "lifecycle_stage": "planning",
            "recommended_lifecycle_action": "continue_planning",
            "reason": "Minimal orchestration state; project in planning stage.",
            "is_active": False,
            "is_blocked": False,
            "is_archived": False,
        }

    # No project context
    return {
        "lifecycle_status": "planned",
        "lifecycle_stage": "unknown",
        "recommended_lifecycle_action": "continue_planning",
        "reason": "No project context; lifecycle unknown.",
        "is_active": False,
        "is_blocked": False,
        "is_archived": False,
    }


def evaluate_project_lifecycle_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises; returns error_fallback result on exception."""
    try:
        return evaluate_project_lifecycle(**kwargs)
    except Exception:
        return {
            "lifecycle_status": "error_fallback",
            "lifecycle_stage": "unknown",
            "recommended_lifecycle_action": "inspect_state",
            "reason": "Lifecycle evaluation failed; safe fallback applied.",
            "is_active": False,
            "is_blocked": False,
            "is_archived": False,
        }
