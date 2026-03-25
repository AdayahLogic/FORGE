"""
NEXUS model routing policy.

Phase 86 introduces a single, explicit routing-policy helper that maps task,
complexity, governance sensitivity, and budget posture into a normalized model
lane decision. This module is policy-only; it does not execute or orchestrate
provider runtimes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


MODEL_LANES = {
    "low_cost_lane",
    "balanced_lane",
    "high_reasoning_lane",
    "governed_high_sensitivity_lane",
}

ROUTING_OUTCOMES = {
    "route_low_cost",
    "route_balanced",
    "route_high_reasoning",
    "route_governed_high_sensitivity",
    "route_blocked_by_budget",
    "route_deferred_for_review",
}


def _now_iso() -> str:
    return datetime.now().isoformat()


def _norm(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    return text or fallback


def _lane_for_outcome(outcome: str) -> str:
    mapping = {
        "route_low_cost": "low_cost_lane",
        "route_balanced": "balanced_lane",
        "route_high_reasoning": "high_reasoning_lane",
        "route_governed_high_sensitivity": "governed_high_sensitivity_lane",
    }
    return mapping.get(outcome, "")


def resolve_model_routing_policy(
    *,
    task_type: str,
    task_complexity: str,
    task_risk_level: str,
    cost_sensitivity: str,
    budget_status: str,
    is_routine_task: bool = False,
    is_high_impact_task: bool = False,
    authority_trace: dict[str, Any] | None = None,
    governance_trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_task_type = _norm(task_type, "implementation")
    normalized_complexity = _norm(task_complexity, "medium")
    normalized_risk = _norm(task_risk_level, "medium")
    normalized_cost_sensitivity = _norm(cost_sensitivity, "medium")
    normalized_budget_status = _norm(budget_status, "within_cap")

    governance_sensitive = (
        normalized_task_type in {"governance_sensitive_evaluation", "governance-sensitive_evaluation"}
        or normalized_risk in {"high", "critical", "governance_sensitive"}
    )
    high_reasoning_needed = (
        normalized_task_type in {"planning", "review"}
        or normalized_complexity in {"high", "very_high"}
        or bool(is_high_impact_task)
    )

    route = "route_balanced"
    reason = "Balanced routing chosen for standard implementation posture."
    routing_status = "routed"
    budget_note = ""

    if normalized_budget_status == "kill_switch_active":
        route = "route_blocked_by_budget"
        routing_status = "blocked_by_budget"
        reason = "Routing blocked because budget kill switch is active."
        budget_note = "Kill switch active; model routing cannot continue."
    elif normalized_budget_status == "cap_exceeded":
        if governance_sensitive:
            route = "route_deferred_for_review"
            routing_status = "deferred_for_review"
            reason = "Routing deferred: cap exceeded and governance-sensitive review is required."
            budget_note = "Budget cap exceeded; governance-sensitive work requires explicit review."
        else:
            route = "route_blocked_by_budget"
            routing_status = "blocked_by_budget"
            reason = "Routing blocked because budget cap is exceeded."
            budget_note = "Budget cap exceeded; routing is blocked."
    elif governance_sensitive:
        route = "route_governed_high_sensitivity"
        reason = "Governance-sensitive task requires governed high-sensitivity routing lane."
    elif high_reasoning_needed:
        route = "route_high_reasoning"
        reason = "Task complexity or impact requires high-reasoning routing lane."
    elif normalized_cost_sensitivity == "high" or bool(is_routine_task):
        route = "route_low_cost"
        reason = "Routine or cost-sensitive task routed to low-cost lane."
    else:
        route = "route_balanced"
        reason = "Balanced lane selected for non-routine, non-high-risk task."

    if (
        normalized_budget_status == "approaching_cap"
        and routing_status == "routed"
        and not governance_sensitive
    ):
        if route == "route_high_reasoning" and normalized_complexity not in {"very_high"}:
            route = "route_balanced"
            reason = "Approaching cap: safely biased from high-reasoning to balanced lane."
            budget_note = "Approaching cap; routed to a lower-cost lane where safe."
        elif route == "route_balanced":
            route = "route_low_cost"
            reason = "Approaching cap: safely biased from balanced to low-cost lane."
            budget_note = "Approaching cap; routed to a lower-cost lane where safe."
        elif route == "route_low_cost":
            budget_note = "Approaching cap; low-cost routing preserved."

    if route not in ROUTING_OUTCOMES:
        route = "route_deferred_for_review"
        routing_status = "deferred_for_review"
        reason = "Routing policy encountered unsupported state; deferred for review."

    selected_lane = _lane_for_outcome(route)
    if selected_lane and selected_lane not in MODEL_LANES:
        selected_lane = ""

    authority_payload = dict(authority_trace or {})
    authority_payload.setdefault("routing_authority", "NEXUS")
    authority_payload.setdefault("policy_source", "model_routing_policy")
    authority_payload.setdefault("policy_version", "phase86_v1")
    authority_payload.setdefault("decision_mode", "explicit_policy_output")

    governance_payload = dict(governance_trace or {})
    governance_payload.setdefault(
        "guards",
        [
            "no_ui_routing_authority",
            "no_hidden_model_selection",
            "budget_and_governance_constraints_enforced",
        ],
    )
    governance_payload.setdefault("recorded_at", _now_iso())

    return {
        "task_type": normalized_task_type,
        "task_complexity": normalized_complexity,
        "task_risk_level": normalized_risk,
        "cost_sensitivity": normalized_cost_sensitivity,
        "budget_status": normalized_budget_status,
        "selected_model_lane": selected_lane,
        "routing_reason": reason,
        "routing_status": routing_status,
        "routing_outcome": route,
        "budget_aware_note": budget_note,
        "authority_trace": authority_payload,
        "governance_trace": governance_payload,
    }


def resolve_model_routing_policy_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return resolve_model_routing_policy(**kwargs)
    except Exception as exc:
        return {
            "task_type": _norm(kwargs.get("task_type"), "implementation"),
            "task_complexity": _norm(kwargs.get("task_complexity"), "medium"),
            "task_risk_level": _norm(kwargs.get("task_risk_level"), "medium"),
            "cost_sensitivity": _norm(kwargs.get("cost_sensitivity"), "medium"),
            "budget_status": _norm(kwargs.get("budget_status"), "within_cap"),
            "selected_model_lane": "",
            "routing_reason": f"Routing policy fallback due to error: {exc}",
            "routing_status": "deferred_for_review",
            "routing_outcome": "route_deferred_for_review",
            "budget_aware_note": "",
            "authority_trace": {
                "routing_authority": "NEXUS",
                "policy_source": "model_routing_policy",
                "policy_version": "phase86_v1",
                "decision_mode": "fallback_error_path",
            },
            "governance_trace": {
                "guards": [
                    "no_ui_routing_authority",
                    "no_hidden_model_selection",
                    "budget_and_governance_constraints_enforced",
                ],
                "recorded_at": _now_iso(),
            },
        }
