"""
NEXUS governance evaluation layer.

Centralized evaluation of orchestration state after dispatch and automation.
Produces normalized governance result: status, approval/review flags, risk, decision reason.
Recommendation/decision-oriented only; no execution, no side effects.
"""

from __future__ import annotations

from typing import Any


def evaluate_governance_outcome(
    *,
    dispatch_status: str | None = None,
    runtime_execution_status: str | None = None,
    dispatch_result: dict[str, Any] | None = None,
    automation_status: str | None = None,
    automation_result: dict[str, Any] | None = None,
    agent_selection_summary: dict[str, Any] | None = None,
    dispatch_plan_summary: dict[str, Any] | None = None,
    active_project: str | None = None,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Evaluate current orchestration state and return normalized governance result.

    Returns stable schema:
    {
      "governance_status": "approved" | "review_required" | "approval_required" | "blocked" | "error_fallback",
      "approval_required": bool,
      "review_required": bool,
      "risk_level": "low" | "medium" | "high" | "unknown",
      "decision_reason": str,
      "blocked": bool,
      "policy_tags": list[str]
    }
    """
    ds = (dispatch_status or "").strip().lower()
    es = (runtime_execution_status or "").strip().lower()
    a_status = (automation_status or "").strip().lower()
    dr = dispatch_result or {}
    ar = automation_result or {}

    policy_tags: list[str] = []

    # Blocked execution: hard stop
    if es == "blocked":
        return {
            "governance_status": "blocked",
            "approval_required": True,
            "review_required": True,
            "risk_level": "high",
            "decision_reason": "Runtime execution is blocked.",
            "blocked": True,
            "policy_tags": ["blocked_execution", "human_review"],
        }

    # Dispatch error: high risk, approval/review
    if ds == "error":
        msg = str(dr.get("message") or "Dispatch error.")
        return {
            "governance_status": "approval_required",
            "approval_required": True,
            "review_required": True,
            "risk_level": "high",
            "decision_reason": msg,
            "blocked": False,
            "policy_tags": ["dispatch_error", "human_review"],
        }

    # No adapter: review required
    if ds == "no_adapter":
        return {
            "governance_status": "review_required",
            "approval_required": False,
            "review_required": True,
            "risk_level": "medium",
            "decision_reason": "No runtime adapter available for selected target.",
            "blocked": False,
            "policy_tags": ["no_adapter", "human_review"],
        }

    # Dispatch skipped: readiness issue
    if ds == "skipped":
        return {
            "governance_status": "review_required",
            "approval_required": False,
            "review_required": True,
            "risk_level": "medium",
            "decision_reason": "Dispatch skipped; plan not ready for dispatch.",
            "blocked": False,
            "policy_tags": ["readiness_issue", "human_review"],
        }

    # Automation layer says human review required
    if a_status == "human_review_required" or ar.get("human_review_required"):
        reason = str(ar.get("reason") or "Automation layer recommends human review.")
        return {
            "governance_status": "review_required",
            "approval_required": False,
            "review_required": True,
            "risk_level": "medium",
            "decision_reason": reason,
            "blocked": False,
            "policy_tags": ["human_review"],
        }

    # Accepted + simulated execution: approved, low risk
    if ds == "accepted" and es == "simulated_execution":
        return {
            "governance_status": "approved",
            "approval_required": False,
            "review_required": False,
            "risk_level": "low",
            "decision_reason": "Dispatch accepted; execution simulated.",
            "blocked": False,
            "policy_tags": ["safe_simulation"],
        }

    # Accepted (other execution outcomes): approved or light review depending on execution
    if ds == "accepted":
        if es in ("success", "completed", "ok"):
            return {
                "governance_status": "approved",
                "approval_required": False,
                "review_required": False,
                "risk_level": "low",
                "decision_reason": "Dispatch accepted; execution completed.",
                "blocked": False,
                "policy_tags": [],
            }
        # accepted but execution status unclear
        return {
            "governance_status": "review_required",
            "approval_required": False,
            "review_required": True,
            "risk_level": "medium",
            "decision_reason": f"Dispatch accepted; execution status: {es or 'unknown'}.",
            "blocked": False,
            "policy_tags": ["human_review"],
        }

    # Default: unknown or no dispatch data
    return {
        "governance_status": "review_required",
        "approval_required": False,
        "review_required": True,
        "risk_level": "unknown",
        "decision_reason": "Governance evaluation: insufficient or unknown dispatch/execution state.",
        "blocked": False,
        "policy_tags": ["human_review"],
    }


def evaluate_governance_outcome_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises; returns error_fallback result on exception."""
    try:
        return evaluate_governance_outcome(**kwargs)
    except Exception:
        return {
            "governance_status": "error_fallback",
            "approval_required": True,
            "review_required": True,
            "risk_level": "unknown",
            "decision_reason": "Governance evaluation failed; safe fallback applied.",
            "blocked": False,
            "policy_tags": ["human_review"],
        }
