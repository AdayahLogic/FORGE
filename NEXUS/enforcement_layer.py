"""
NEXUS enforcement evaluation layer.

Evaluates governance and lifecycle outcomes to produce workflow control state:
approval gates, manual review gates, and workflow_action. Evaluation-only;
no external approval services, no destructive enforcement.
"""

from __future__ import annotations

from typing import Any


def evaluate_enforcement_outcome(
    *,
    governance_status: str | None = None,
    governance_result: dict[str, Any] | None = None,
    project_lifecycle_status: str | None = None,
    project_lifecycle_result: dict[str, Any] | None = None,
    active_project: str | None = None,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Evaluate enforcement outcome from governance and lifecycle state.

    Returns stable schema:
    {
      "enforcement_status": "continue" | "manual_review_required" | "approval_required" | "blocked" | "hold" | "error_fallback",
      "approval_gate": bool,
      "manual_review_gate": bool,
      "downstream_blocked": bool,
      "workflow_action": "proceed" | "hold" | "stop_after_current_stage" | "manual_review" | "await_approval",
      "reason": str,
      "enforcement_tags": list[str]
    }
    """
    g_status = (governance_status or "").strip().lower()
    gr = governance_result or {}
    pl_status = (project_lifecycle_status or "").strip().lower()
    plr = project_lifecycle_result or {}

    blocked = gr.get("blocked") is True
    approval_required = gr.get("approval_required") is True
    review_required = gr.get("review_required") is True
    is_blocked = plr.get("is_blocked") is True
    is_active = plr.get("is_active") is True
    is_paused = pl_status == "paused"

    enforcement_tags: list[str] = []

    # Governance blocked or lifecycle blocked -> blocked / stop_after_current_stage
    if blocked or g_status == "blocked" or is_blocked:
        return {
            "enforcement_status": "blocked",
            "approval_gate": True,
            "manual_review_gate": True,
            "downstream_blocked": True,
            "workflow_action": "stop_after_current_stage",
            "reason": gr.get("decision_reason") or plr.get("reason") or "Governance or lifecycle blocked.",
            "enforcement_tags": ["blocked", "human_review"],
        }

    # Governance approval_required -> approval_required / await_approval
    if g_status == "approval_required" or approval_required:
        return {
            "enforcement_status": "approval_required",
            "approval_gate": True,
            "manual_review_gate": True,
            "downstream_blocked": True,
            "workflow_action": "await_approval",
            "reason": gr.get("decision_reason") or "Approval required before proceeding.",
            "enforcement_tags": ["approval_required", "human_review"],
        }

    # Governance review_required -> manual_review_required / manual_review
    if g_status == "review_required" or review_required:
        return {
            "enforcement_status": "manual_review_required",
            "approval_gate": False,
            "manual_review_gate": True,
            "downstream_blocked": False,
            "workflow_action": "manual_review",
            "reason": gr.get("decision_reason") or "Manual review required.",
            "enforcement_tags": ["manual_review"],
        }

    # Lifecycle paused -> hold / hold
    if is_paused:
        return {
            "enforcement_status": "hold",
            "approval_gate": False,
            "manual_review_gate": True,
            "downstream_blocked": False,
            "workflow_action": "hold",
            "reason": plr.get("reason") or "Project lifecycle paused.",
            "enforcement_tags": ["hold", "lifecycle_paused"],
        }

    # Governance approved + lifecycle active -> continue / proceed
    if g_status == "approved" and (is_active or pl_status == "active"):
        return {
            "enforcement_status": "continue",
            "approval_gate": False,
            "manual_review_gate": False,
            "downstream_blocked": False,
            "workflow_action": "proceed",
            "reason": "Governance approved; lifecycle active.",
            "enforcement_tags": [],
        }

    # Default: safe hold when state unclear
    return {
        "enforcement_status": "manual_review_required",
        "approval_gate": False,
        "manual_review_gate": True,
        "downstream_blocked": False,
        "workflow_action": "manual_review",
        "reason": "Enforcement evaluation: state unclear; manual review recommended.",
        "enforcement_tags": ["human_review"],
    }


def evaluate_enforcement_outcome_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises; returns error_fallback on exception."""
    try:
        return evaluate_enforcement_outcome(**kwargs)
    except Exception as e:
        return {
            "enforcement_status": "error_fallback",
            "approval_gate": True,
            "manual_review_gate": True,
            "downstream_blocked": True,
            "workflow_action": "hold",
            "reason": str(e),
            "enforcement_tags": ["error_fallback", "human_review"],
        }
