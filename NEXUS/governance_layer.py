"""
NEXUS governance evaluation layer.

Centralized evaluation of orchestration state after dispatch and automation.
Produces normalized governance result: status, approval/review flags, risk, decision reason.
Recommendation/decision-oriented only; no execution, no destructive side effects.
"""

from __future__ import annotations

from typing import Any

from NEXUS.project_state import load_project_state
from NEXUS.registry import PROJECTS
from NEXUS.self_evolution_governance import (
    evaluate_self_change_mutation_budget_safe,
    evaluate_self_change_comparative_scoring_safe,
    evaluate_self_change_governance_safe,
    evaluate_self_change_post_promotion_monitoring_safe,
    evaluate_self_change_rollback_execution_safe,
    evaluate_self_change_release_gate_safe,
    evaluate_self_change_sandbox_promotion_safe,
)
from NEXUS.studio_coordinator import build_studio_coordination_summary_safe
from NEXUS.studio_driver import build_studio_driver_result_safe


def _evaluate_dispatch_governance(
    *,
    dispatch_status: str | None = None,
    runtime_execution_status: str | None = None,
    dispatch_result: dict[str, Any] | None = None,
    automation_status: str | None = None,
    automation_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ds = (dispatch_status or "").strip().lower()
    es = (runtime_execution_status or "").strip().lower()
    a_status = (automation_status or "").strip().lower()
    dr = dispatch_result or {}
    ar = automation_result or {}
    package_id = str(dr.get("execution_package_id") or "").strip()
    package_review_required = bool(dr.get("package_review_required"))

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

    if ds == "skipped":
        if package_id or package_review_required:
            return {
                "governance_status": "review_required",
                "approval_required": bool(dr.get("approval_required")),
                "review_required": True,
                "risk_level": "medium",
                "decision_reason": "Dispatch stopped at a sealed review-only execution package.",
                "blocked": False,
                "policy_tags": ["review_package", "human_review"],
            }
        return {
            "governance_status": "review_required",
            "approval_required": False,
            "review_required": True,
            "risk_level": "medium",
            "decision_reason": "Dispatch skipped; plan not ready for dispatch.",
            "blocked": False,
            "policy_tags": ["readiness_issue", "human_review"],
        }

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

    if ds == "accepted":
        if (package_id or package_review_required) and es == "queued":
            return {
                "governance_status": "review_required",
                "approval_required": bool(dr.get("approval_required")),
                "review_required": True,
                "risk_level": "medium",
                "decision_reason": "Dispatch accepted into a review-only package state; no live execution occurred.",
                "blocked": False,
                "policy_tags": ["review_package", "human_review"],
            }
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
        return {
            "governance_status": "review_required",
            "approval_required": False,
            "review_required": True,
            "risk_level": "medium",
            "decision_reason": f"Dispatch accepted; execution status: {es or 'unknown'}.",
            "blocked": False,
            "policy_tags": ["human_review"],
        }

    return {
        "governance_status": "review_required",
        "approval_required": False,
        "review_required": True,
        "risk_level": "unknown",
        "decision_reason": "Governance evaluation: insufficient or unknown dispatch/execution state.",
        "blocked": False,
        "policy_tags": ["human_review"],
    }


def _build_states_by_project(
    *,
    active_project: str | None,
    project_path: str | None,
    dispatch_status: str | None,
    runtime_execution_status: str | None,
    dispatch_result: dict[str, Any] | None,
    automation_status: str | None,
    automation_result: dict[str, Any] | None,
    agent_selection_summary: dict[str, Any] | None,
    dispatch_plan_summary: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    states_by_project: dict[str, dict[str, Any]] = {}
    for key, project_meta in PROJECTS.items():
        path = project_meta.get("path")
        if not path:
            continue
        loaded = load_project_state(path)
        if not isinstance(loaded, dict) or loaded.get("load_error"):
            continue
        states_by_project[key] = loaded

    if active_project:
        overlay = dict(states_by_project.get(active_project, {}))
        overlay.update(
            {
                "active_project": active_project,
                "project_path": project_path or overlay.get("project_path"),
                "dispatch_status": dispatch_status,
                "runtime_execution_status": runtime_execution_status,
                "dispatch_result": dispatch_result or {},
                "automation_status": automation_status,
                "automation_result": automation_result or {},
                "agent_selection_summary": agent_selection_summary or overlay.get("agent_selection_summary") or {},
                "dispatch_plan_summary": dispatch_plan_summary or overlay.get("dispatch_plan_summary") or {},
            }
        )
        states_by_project[active_project] = overlay

    return states_by_project


def _build_meta_engine_conflict(
    *,
    active_project: str | None = None,
    project_path: str | None = None,
    dispatch_status: str | None = None,
    runtime_execution_status: str | None = None,
    dispatch_result: dict[str, Any] | None = None,
    automation_status: str | None = None,
    automation_result: dict[str, Any] | None = None,
    agent_selection_summary: dict[str, Any] | None = None,
    dispatch_plan_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not active_project and not project_path:
        return {
            "status": "resolved",
            "conflict_type": "none",
            "involved_engines": [],
            "winning_priority": "",
            "resolution_basis": "no_project_context",
            "resolution_state": "resolved",
            "routing_outcome": "continue",
            "reason": "No active project context available for meta-engine conflict evaluation.",
            "governance_trace": {
                "priority_order": ["SENTINEL", "VERITAS", "LEVIATHAN", "TITAN", "HELIOS"],
                "engine_signals": {},
            },
        }

    from meta_engines.audit_engine import evaluate_audit_engine
    from meta_engines.compliance_engine import evaluate_compliance_engine
    from meta_engines.cost_engine import evaluate_cost_engine
    from meta_engines.policy_engine import evaluate_policy_engine
    from meta_engines.risk_engine import evaluate_risk_engine
    from meta_engines.safety_engine import evaluate_safety_engine
    from meta_engines.security_engine import evaluate_security_engine
    from elite_layers.helios import build_helios_summary_safe
    from elite_layers.leviathan import build_leviathan_summary_safe
    from elite_layers.sentinel import build_sentinel_summary_safe
    from elite_layers.titan import build_titan_summary_safe
    from elite_layers.veritas import build_veritas_summary_safe
    from NEXUS.meta_engine_governance import resolve_meta_engine_governance_safe
    from portfolio_manager import build_portfolio_summary_safe

    states_by_project = _build_states_by_project(
        active_project=active_project,
        project_path=project_path,
        dispatch_status=dispatch_status,
        runtime_execution_status=runtime_execution_status,
        dispatch_result=dispatch_result,
        automation_status=automation_status,
        automation_result=automation_result,
        agent_selection_summary=agent_selection_summary,
        dispatch_plan_summary=dispatch_plan_summary,
    )
    studio_coordination_summary = build_studio_coordination_summary_safe(states_by_project=states_by_project)
    studio_driver_summary = build_studio_driver_result_safe(
        studio_coordination_summary=studio_coordination_summary,
        states_by_project=states_by_project,
    )
    portfolio_summary = build_portfolio_summary_safe(
        states_by_project=states_by_project,
        studio_coordination_summary=studio_coordination_summary,
        studio_driver_summary=studio_driver_summary,
    )
    meta_engine_summary = {
        "safety_engine": evaluate_safety_engine(
            states_by_project=states_by_project,
            studio_coordination_summary=studio_coordination_summary,
            studio_driver_summary=studio_driver_summary,
            runtime_infrastructure_summary={},
        ),
        "security_engine": evaluate_security_engine(
            states_by_project=states_by_project,
            studio_coordination_summary=studio_coordination_summary,
            studio_driver_summary=studio_driver_summary,
            runtime_infrastructure_summary={},
        ),
        "compliance_engine": evaluate_compliance_engine(
            states_by_project=states_by_project,
            studio_coordination_summary=studio_coordination_summary,
            studio_driver_summary=studio_driver_summary,
            runtime_infrastructure_summary={},
        ),
        "risk_engine": evaluate_risk_engine(
            states_by_project=states_by_project,
            studio_coordination_summary=studio_coordination_summary,
            studio_driver_summary=studio_driver_summary,
            runtime_infrastructure_summary={},
        ),
        "policy_engine": evaluate_policy_engine(
            states_by_project=states_by_project,
            studio_coordination_summary=studio_coordination_summary,
            studio_driver_summary=studio_driver_summary,
            runtime_infrastructure_summary={},
        ),
        "cost_engine": evaluate_cost_engine(
            states_by_project=states_by_project,
            studio_coordination_summary=studio_coordination_summary,
            studio_driver_summary=studio_driver_summary,
            runtime_infrastructure_summary={},
        ),
        "audit_engine": evaluate_audit_engine(
            states_by_project=states_by_project,
            studio_coordination_summary=studio_coordination_summary,
            studio_driver_summary=studio_driver_summary,
            runtime_infrastructure_summary={},
        ),
    }
    titan_summary = build_titan_summary_safe(
        states_by_project=states_by_project,
        studio_coordination_summary=studio_coordination_summary,
        studio_driver_summary=studio_driver_summary,
    )
    leviathan_summary = build_leviathan_summary_safe(
        states_by_project=states_by_project,
        studio_coordination_summary=studio_coordination_summary,
        studio_driver_summary=studio_driver_summary,
        portfolio_summary=portfolio_summary,
    )
    veritas_summary = build_veritas_summary_safe(
        states_by_project=states_by_project,
        studio_coordination_summary=studio_coordination_summary,
        studio_driver_summary=studio_driver_summary,
        meta_engine_summary=meta_engine_summary,
    )
    sentinel_summary = build_sentinel_summary_safe(
        states_by_project=states_by_project,
        studio_coordination_summary=studio_coordination_summary,
        meta_engine_summary=meta_engine_summary,
    )
    helios_summary = build_helios_summary_safe(
        dashboard_summary={
            "veritas_summary": veritas_summary,
            "sentinel_summary": sentinel_summary,
        },
        studio_coordination_summary=studio_coordination_summary,
        studio_driver_summary=studio_driver_summary,
        project_name=(portfolio_summary.get("priority_project") or active_project or "").strip() or None,
        live_regression=False,
        helios_evaluation_mode="governance_cached",
    )
    conflict = resolve_meta_engine_governance_safe(
        titan_summary=titan_summary,
        leviathan_summary=leviathan_summary,
        helios_summary=helios_summary,
        veritas_summary=veritas_summary,
        sentinel_summary=sentinel_summary,
    )
    conflict["governance_trace"] = {
        **(conflict.get("governance_trace") or {}),
        "meta_engine_summary": meta_engine_summary,
        "titan_summary": titan_summary,
        "leviathan_summary": leviathan_summary,
        "helios_summary": helios_summary,
        "veritas_summary": veritas_summary,
        "sentinel_summary": sentinel_summary,
    }
    return conflict


def _base_resolution_from_governance(base: dict[str, Any]) -> dict[str, str]:
    governance_status = str(base.get("governance_status") or "").strip().lower()
    if governance_status == "approved":
        return {"resolution_state": "resolved", "routing_outcome": "continue", "workflow_action": "proceed"}
    if governance_status == "blocked":
        return {"resolution_state": "stop", "routing_outcome": "stop", "workflow_action": "stop_after_current_stage"}
    if governance_status == "approval_required":
        return {"resolution_state": "escalate", "routing_outcome": "escalate", "workflow_action": "await_approval"}
    return {"resolution_state": "pause", "routing_outcome": "pause", "workflow_action": "hold"}


def _severity_rank(outcome: str) -> int:
    return {"continue": 0, "pause": 1, "escalate": 2, "stop": 3}.get(str(outcome or "").strip().lower(), 1)


def _finalize_governance_result(
    *,
    base: dict[str, Any],
    conflict: dict[str, Any],
) -> dict[str, Any]:
    base_resolution = _base_resolution_from_governance(base)
    conflict_outcome = str(conflict.get("routing_outcome") or "continue").strip().lower()
    base_outcome = str(base_resolution.get("routing_outcome") or "continue").strip().lower()
    final_source = "base_governance"

    if _severity_rank(conflict_outcome) > _severity_rank(base_outcome):
        final_source = "meta_engine_conflict"
        final_resolution_state = str(conflict.get("resolution_state") or "pause")
        final_routing_outcome = conflict_outcome
        if final_routing_outcome == "stop":
            workflow_action = "stop_after_current_stage"
        elif final_routing_outcome == "escalate":
            workflow_action = "manual_review"
        elif final_routing_outcome == "pause":
            workflow_action = "hold"
        else:
            workflow_action = "proceed"
        decision_reason = str(conflict.get("reason") or base.get("decision_reason") or "")
    else:
        final_resolution_state = str(base_resolution.get("resolution_state") or "pause")
        final_routing_outcome = base_outcome
        workflow_action = str(base_resolution.get("workflow_action") or "hold")
        decision_reason = str(base.get("decision_reason") or conflict.get("reason") or "")

    governance_status = str(base.get("governance_status") or "review_required")
    approval_required = bool(base.get("approval_required"))
    review_required = bool(base.get("review_required"))
    blocked = bool(base.get("blocked"))

    if final_routing_outcome == "stop":
        governance_status = "blocked"
        approval_required = True
        review_required = True
        blocked = True
    elif final_routing_outcome == "escalate":
        governance_status = "approval_required" if approval_required else "review_required"
        approval_required = approval_required or workflow_action == "await_approval"
        review_required = True
        blocked = False
    elif final_routing_outcome == "pause":
        governance_status = "review_required"
        approval_required = False
        review_required = True
        blocked = False
    else:
        blocked = False

    policy_tags = [str(x) for x in (base.get("policy_tags") or []) if str(x).strip()]
    if conflict_outcome != "continue":
        policy_tags.append("governance_conflict")
    if final_routing_outcome != "continue":
        policy_tags.append(f"routing_{final_routing_outcome}")

    return {
        "governance_status": governance_status,
        "approval_required": bool(approval_required),
        "review_required": bool(review_required),
        "risk_level": str(base.get("risk_level") or "unknown"),
        "decision_reason": decision_reason,
        "blocked": bool(blocked),
        "policy_tags": sorted(set(policy_tags)),
        "resolution_state": final_resolution_state,
        "routing_outcome": final_routing_outcome,
        "workflow_action": workflow_action,
        "final_decision_source": final_source,
        "governance_conflict": conflict,
        "conflict_type": str(conflict.get("conflict_type") or "none"),
        "system_pause_required": bool(conflict.get("status") == "unresolved" or final_routing_outcome == "pause"),
        "reason": decision_reason,
        "governance_trace": {
            "base_governance": base,
            "conflict": conflict,
            "final_decision_source": final_source,
        },
    }


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
    base = _evaluate_dispatch_governance(
        dispatch_status=dispatch_status,
        runtime_execution_status=runtime_execution_status,
        dispatch_result=dispatch_result,
        automation_status=automation_status,
        automation_result=automation_result,
    )
    conflict = _build_meta_engine_conflict(
        active_project=active_project,
        project_path=project_path,
        dispatch_status=dispatch_status,
        runtime_execution_status=runtime_execution_status,
        dispatch_result=dispatch_result,
        automation_status=automation_status,
        automation_result=automation_result,
        agent_selection_summary=agent_selection_summary,
        dispatch_plan_summary=dispatch_plan_summary,
    )
    return _finalize_governance_result(base=base, conflict=conflict)


def evaluate_governance_outcome_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises; returns error_fallback result on exception."""
    try:
        return evaluate_governance_outcome(**kwargs)
    except Exception as e:
        return {
            "governance_status": "error_fallback",
            "approval_required": True,
            "review_required": True,
            "risk_level": "unknown",
            "decision_reason": "Governance evaluation failed; safe fallback applied.",
            "blocked": False,
            "policy_tags": ["human_review", "error_fallback"],
            "resolution_state": "pause",
            "routing_outcome": "pause",
            "workflow_action": "hold",
            "final_decision_source": "error_fallback",
            "governance_conflict": {
                "status": "unresolved",
                "conflict_type": "governance_evaluation_error",
                "involved_engines": [],
                "winning_priority": "",
                "resolution_basis": "governance_exception",
                "resolution_state": "pause",
                "routing_outcome": "pause",
                "reason": f"Governance evaluation failed: {e}",
                "governance_trace": {},
            },
            "conflict_type": "governance_evaluation_error",
            "system_pause_required": True,
            "reason": "Governance evaluation failed; safe fallback applied.",
            "governance_trace": {
                "base_governance": {},
                "conflict": {},
                "final_decision_source": "error_fallback",
            },
        }


def evaluate_self_change_governance_outcome(
    *,
    self_change_contract: dict[str, Any] | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    result = evaluate_self_change_governance_safe(self_change_contract)
    authority_trace = dict(result.get("authority_trace") or {})
    authority_trace.setdefault("actor", str(actor or authority_trace.get("actor") or "nexus"))
    authority_trace.setdefault("requested_action", "propose_self_change")
    governance_trace = dict(result.get("governance_trace") or {})
    governance_trace.setdefault("evaluation_scope", "self_evolution")
    governance_trace.setdefault("actor", authority_trace.get("actor"))
    return {
        **result,
        "authority_trace": authority_trace,
        "governance_trace": governance_trace,
    }


def evaluate_self_change_governance_outcome_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return evaluate_self_change_governance_outcome(**kwargs)
    except Exception as e:
        return {
            "self_change_status": "blocked",
            "governance_status": "blocked",
            "approval_required": True,
            "approval_requirement": "mandatory",
            "risk_level": "high_risk",
            "protected_zones": [],
            "validation_required": True,
            "rollback_required": True,
            "contract_status": "invalid",
            "decision_reason": f"Self-change governance evaluation failed: {e}",
            "authority_trace": {"actor": str(kwargs.get("actor") or "nexus"), "requested_action": "propose_self_change"},
            "governance_trace": {"evaluation_scope": "self_evolution", "error": str(e)},
            "normalized_contract": {},
        }


def evaluate_self_change_release_gate_outcome(
    *,
    self_change_contract: dict[str, Any] | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    result = evaluate_self_change_release_gate_safe(self_change_contract)
    authority_trace = dict(result.get("authority_trace") or {})
    authority_trace.setdefault("actor", str(actor or authority_trace.get("actor") or "nexus"))
    authority_trace.setdefault("requested_action", "propose_self_change")
    governance_trace = dict(result.get("governance_trace") or {})
    governance_trace.setdefault("evaluation_scope", "self_evolution_release_gate")
    governance_trace.setdefault("actor", authority_trace.get("actor"))
    return {
        **result,
        "authority_trace": authority_trace,
        "governance_trace": governance_trace,
    }


def evaluate_self_change_release_gate_outcome_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return evaluate_self_change_release_gate_outcome(**kwargs)
    except Exception as e:
        return {
            "status": "blocked",
            "change_id": "",
            "risk_level": "high_risk",
            "protected_zone_hit": False,
            "validation_outcome": "pending",
            "gate_outcome": "blocked_missing_validation",
            "release_lane": "experimental",
            "rollback_required": False,
            "reason": f"Self-change release gating failed: {e}",
            "authority_trace": {"actor": str(kwargs.get("actor") or "nexus"), "requested_action": "propose_self_change"},
            "governance_trace": {"evaluation_scope": "self_evolution_release_gate", "error": str(e)},
        }


def evaluate_self_change_sandbox_promotion_outcome(
    *,
    self_change_contract: dict[str, Any] | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    result = evaluate_self_change_sandbox_promotion_safe(self_change_contract)
    authority_trace = dict(result.get("authority_trace") or {})
    authority_trace.setdefault("actor", str(actor or authority_trace.get("actor") or "nexus"))
    authority_trace.setdefault("requested_action", "propose_self_change")
    governance_trace = dict(result.get("governance_trace") or {})
    governance_trace.setdefault("evaluation_scope", "self_evolution_sandbox_promotion")
    governance_trace.setdefault("actor", authority_trace.get("actor"))
    return {
        **result,
        "authority_trace": authority_trace,
        "governance_trace": governance_trace,
    }


def evaluate_self_change_sandbox_promotion_outcome_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return evaluate_self_change_sandbox_promotion_outcome(**kwargs)
    except Exception as e:
        return {
            "status": "promotion_blocked",
            "change_id": "",
            "risk_level": "high_risk",
            "protected_zone_hit": False,
            "protected_zones": [],
            "release_lane": "experimental",
            "sandbox_required": True,
            "sandbox_status": "sandbox_pending",
            "sandbox_result": "sandbox_pending",
            "promotion_status": "promotion_blocked",
            "promotion_reason": f"Self-change sandbox/promotion evaluation failed: {e}",
            "rollback_required": False,
            "approval_required": True,
            "approval_requirement": "mandatory",
            "approval_status": "pending",
            "validation_outcome": "pending",
            "gate_outcome": "blocked_missing_validation",
            "contract_status": "invalid",
            "tests_status": "pending",
            "build_status": "pending",
            "regression_status": "pending",
            "reason": f"Self-change sandbox/promotion evaluation failed: {e}",
            "authority_trace": {"actor": str(kwargs.get("actor") or "nexus"), "requested_action": "propose_self_change"},
            "governance_trace": {"evaluation_scope": "self_evolution_sandbox_promotion", "error": str(e)},
        }


def evaluate_self_change_comparative_scoring_outcome(
    *,
    self_change_contract: dict[str, Any] | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    result = evaluate_self_change_comparative_scoring_safe(self_change_contract)
    authority_trace = dict(result.get("authority_trace") or {})
    authority_trace.setdefault("actor", str(actor or authority_trace.get("actor") or "nexus"))
    authority_trace.setdefault("requested_action", "propose_self_change")
    governance_trace = dict(result.get("governance_trace") or {})
    governance_trace.setdefault("evaluation_scope", "self_evolution_comparative_scoring")
    governance_trace.setdefault("actor", authority_trace.get("actor"))
    return {
        **result,
        "authority_trace": authority_trace,
        "governance_trace": governance_trace,
    }


def evaluate_self_change_comparative_scoring_outcome_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return evaluate_self_change_comparative_scoring_outcome(**kwargs)
    except Exception as e:
        return {
            "status": "insufficient_evidence",
            "change_id": "",
            "baseline_reference": "",
            "candidate_reference": "",
            "comparison_dimensions": [],
            "observed_improvement": {},
            "observed_regression": {},
            "net_score": 0.0,
            "confidence_level": 0.0,
            "confidence_band": "weak",
            "promotion_confidence": "insufficient_evidence",
            "recommendation": "hold_experimental",
            "reason": f"Self-change comparative scoring failed: {e}",
            "authority_trace": {"actor": str(kwargs.get("actor") or "nexus"), "requested_action": "propose_self_change"},
            "governance_trace": {"evaluation_scope": "self_evolution_comparative_scoring", "error": str(e)},
        }


def evaluate_self_change_post_promotion_monitoring_outcome(
    *,
    self_change_contract: dict[str, Any] | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    result = evaluate_self_change_post_promotion_monitoring_safe(self_change_contract)
    authority_trace = dict(result.get("authority_trace") or {})
    authority_trace.setdefault("actor", str(actor or authority_trace.get("actor") or "nexus"))
    authority_trace.setdefault("requested_action", "propose_self_change")
    governance_trace = dict(result.get("governance_trace") or {})
    governance_trace.setdefault("evaluation_scope", "self_evolution_post_promotion_monitoring")
    governance_trace.setdefault("actor", authority_trace.get("actor"))
    return {
        **result,
        "authority_trace": authority_trace,
        "governance_trace": governance_trace,
    }


def evaluate_self_change_post_promotion_monitoring_outcome_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return evaluate_self_change_post_promotion_monitoring_outcome(**kwargs)
    except Exception as e:
        return {
            "status": "pending_monitoring",
            "change_id": "",
            "promoted_at": "",
            "monitoring_window": "observation_window",
            "monitoring_status": "pending_monitoring",
            "observation_count": 0,
            "health_signals": {},
            "regression_detected": False,
            "rollback_triggered": False,
            "rollback_trigger_outcome": "monitor_more",
            "rollback_reason": f"Self-change post-promotion monitoring failed: {e}",
            "stable_status": "provisionally_stable",
            "authority_trace": {"actor": str(kwargs.get("actor") or "nexus"), "requested_action": "propose_self_change"},
            "governance_trace": {"evaluation_scope": "self_evolution_post_promotion_monitoring", "error": str(e)},
        }


def evaluate_self_change_rollback_execution_outcome(
    *,
    self_change_contract: dict[str, Any] | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    result = evaluate_self_change_rollback_execution_safe(self_change_contract)
    authority_trace = dict(result.get("authority_trace") or {})
    authority_trace.setdefault("actor", str(actor or authority_trace.get("actor") or "nexus"))
    authority_trace.setdefault("requested_action", "execute_self_change_rollback")
    governance_trace = dict(result.get("governance_trace") or {})
    governance_trace.setdefault("evaluation_scope", "self_evolution_rollback_execution")
    governance_trace.setdefault("actor", authority_trace.get("actor"))
    return {
        **result,
        "authority_trace": authority_trace,
        "governance_trace": governance_trace,
    }


def evaluate_self_change_rollback_execution_outcome_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return evaluate_self_change_rollback_execution_outcome(**kwargs)
    except Exception as e:
        return {
            "status": "rollback_failed",
            "change_id": "",
            "rollback_id": "",
            "rollback_scope": "file_only",
            "rollback_target_files": [],
            "rollback_target_components": [],
            "blast_radius_level": "high",
            "rollback_status": "rollback_failed",
            "rollback_reason": f"Self-change rollback execution failed: {e}",
            "rollback_approval_required": True,
            "rollback_sequence": ["validate", "approve", "execute", "verify"],
            "rollback_result": f"Self-change rollback execution failed: {e}",
            "rollback_execution_eligible": False,
            "rollback_follow_up_validation_required": True,
            "rollback_validation_status": "pending",
            "authority_trace": {"actor": str(kwargs.get("actor") or "nexus"), "requested_action": "execute_self_change_rollback"},
            "governance_trace": {"evaluation_scope": "self_evolution_rollback_execution", "error": str(e)},
        }


def evaluate_self_change_mutation_budget_outcome(
    *,
    self_change_contract: dict[str, Any] | None = None,
    recent_audit_entries: list[dict[str, Any]] | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    result = evaluate_self_change_mutation_budget_safe(self_change_contract, recent_audit_entries=recent_audit_entries)
    authority_trace = dict(result.get("authority_trace") or {})
    authority_trace.setdefault("actor", str(actor or authority_trace.get("actor") or "nexus"))
    authority_trace.setdefault("requested_action", "budget_self_change_attempt")
    governance_trace = dict(result.get("governance_trace") or {})
    governance_trace.setdefault("evaluation_scope", "self_evolution_change_budgeting")
    governance_trace.setdefault("actor", authority_trace.get("actor"))
    return {
        **result,
        "authority_trace": authority_trace,
        "governance_trace": governance_trace,
    }


def evaluate_self_change_mutation_budget_outcome_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return evaluate_self_change_mutation_budget_outcome(**kwargs)
    except Exception as e:
        return {
            "status": "change_attempt_blocked",
            "change_id": "",
            "risk_level": "high_risk",
            "protected_zone_hit": False,
            "budgeting_window": {"current_window_id": "", "window_start": "", "window_end": ""},
            "attempted_changes_in_window": 0,
            "successful_changes_in_window": 0,
            "failed_changes_in_window": 0,
            "rollbacks_in_window": 0,
            "mutation_rate_status": "blocked",
            "budget_remaining": 0,
            "cool_down_required": True,
            "control_outcome": "change_attempt_blocked",
            "reason": f"Self-change mutation budgeting failed: {e}",
            "authority_trace": {"actor": str(kwargs.get("actor") or "nexus"), "requested_action": "budget_self_change_attempt"},
            "governance_trace": {"evaluation_scope": "self_evolution_change_budgeting", "error": str(e)},
        }
