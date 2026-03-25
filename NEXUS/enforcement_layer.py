"""
NEXUS enforcement evaluation layer.

Evaluates governance and lifecycle outcomes to produce workflow control state:
approval gates, manual review gates, and workflow_action. Evaluation-only;
no external approval services, no destructive enforcement.
"""

from __future__ import annotations

from typing import Any


def evaluate_execution_package_enforcement_state(
    *,
    package: dict[str, Any] | None = None,
    governance_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Package-level enforcement projection used by queue intelligence.
    Never authorizes execution; only classifies queue suitability.
    """
    p = package if isinstance(package, dict) else {}
    g = governance_state if isinstance(governance_state, dict) else {}
    governance_status = str(g.get("governance_status") or "review_required").strip().lower()
    hard_block = bool(g.get("hard_block"))
    execution_status = str(p.get("execution_status") or "").strip().lower()
    if hard_block or execution_status == "blocked":
        return {
            "enforcement_status": "blocked",
            "queue_eligible": False,
            "reason": "Hard block propagated from governance or execution status.",
        }
    if governance_status == "approval_required":
        return {
            "enforcement_status": "approval_required",
            "queue_eligible": True,
            "reason": "Approval is required before any progression.",
        }
    if governance_status == "approved":
        return {
            "enforcement_status": "continue",
            "queue_eligible": True,
            "reason": "Package is eligible for governed queue ranking.",
        }
    return {
        "enforcement_status": "manual_review_required",
        "queue_eligible": True,
        "reason": "Manual review required before progression.",
    }


def evaluate_execution_package_enforcement_state_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return evaluate_execution_package_enforcement_state(**kwargs)
    except Exception as e:
        return {
            "enforcement_status": "manual_review_required",
            "queue_eligible": False,
            "reason": f"Package enforcement projection failed: {e}",
        }


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
    governance_workflow_action = str(gr.get("workflow_action") or "").strip().lower()
    governance_routing_outcome = str(gr.get("routing_outcome") or "").strip().lower()

    enforcement_tags: list[str] = []

    if governance_routing_outcome in ("stop", "pause", "escalate") and governance_workflow_action:
        if governance_workflow_action == "stop_after_current_stage":
            return {
                "enforcement_status": "blocked",
                "approval_gate": True,
                "manual_review_gate": True,
                "downstream_blocked": True,
                "workflow_action": governance_workflow_action,
                "reason": gr.get("decision_reason") or gr.get("reason") or "Governance stop required.",
                "enforcement_tags": ["governance_propagated", "blocked", "human_review"],
            }
        if governance_workflow_action == "await_approval":
            return {
                "enforcement_status": "approval_required",
                "approval_gate": True,
                "manual_review_gate": True,
                "downstream_blocked": True,
                "workflow_action": governance_workflow_action,
                "reason": gr.get("decision_reason") or gr.get("reason") or "Governance escalation requires approval.",
                "enforcement_tags": ["governance_propagated", "approval_required", "human_review"],
            }
        if governance_workflow_action == "manual_review":
            return {
                "enforcement_status": "manual_review_required",
                "approval_gate": False,
                "manual_review_gate": True,
                "downstream_blocked": True,
                "workflow_action": governance_workflow_action,
                "reason": gr.get("decision_reason") or gr.get("reason") or "Governance escalation requires manual review.",
                "enforcement_tags": ["governance_propagated", "manual_review"],
            }
        return {
            "enforcement_status": "hold",
            "approval_gate": False,
            "manual_review_gate": True,
            "downstream_blocked": True,
            "workflow_action": "hold",
            "reason": gr.get("decision_reason") or gr.get("reason") or "Governance pause propagated.",
            "enforcement_tags": ["governance_propagated", "hold", "lifecycle_paused"],
        }

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
