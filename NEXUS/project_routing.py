from __future__ import annotations

from typing import Any

from NEXUS.autonomy_modes import build_autonomy_mode_state, evaluate_mode_transition, normalize_autonomy_mode


def _task_label(task: dict[str, Any] | None) -> str:
    row = task or {}
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    return str(row.get("task") or payload.get("description") or row.get("id") or "").strip()


def _normalize_tasks(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def select_next_task(state: dict[str, Any] | None = None) -> dict[str, Any] | None:
    loaded = state or {}
    queue = _normalize_tasks(loaded.get("task_queue_snapshot") or loaded.get("task_queue"))
    pending = [
        item
        for item in queue
        if str(item.get("status") or "").strip().lower() in ("", "pending", "queued", "ready")
    ]
    if not pending:
        return None
    pending.sort(key=lambda item: (int(item.get("priority") or 0), str(item.get("id") or ""), _task_label(item)))
    return pending[0]


def _determine_backend_path(
    *,
    state: dict[str, Any],
    package: dict[str, Any] | None,
) -> str:
    pkg = package or {}
    execution_bridge = state.get("execution_bridge_summary") if isinstance(state.get("execution_bridge_summary"), dict) else {}
    dispatch = state.get("dispatch_plan_summary") if isinstance(state.get("dispatch_plan_summary"), dict) else {}
    executor_target = str(
        pkg.get("handoff_executor_target_id")
        or pkg.get("execution_executor_target_id")
        or execution_bridge.get("selected_runtime_target")
        or execution_bridge.get("fallback_runtime_target")
        or dispatch.get("runtime_target_id")
        or "local"
    ).strip()
    runtime_node = str(
        (pkg.get("routing_summary") or {}).get("runtime_node")
        or execution_bridge.get("runtime_node")
        or dispatch.get("runtime_node")
        or "coder"
    ).strip()
    return f"execution_package_pipeline:{runtime_node}:{executor_target}"


def build_project_routing_decision(
    *,
    project_key: str,
    state: dict[str, Any] | None = None,
    active_package: dict[str, Any] | None = None,
    autonomy_mode: str | None = None,
) -> dict[str, Any]:
    loaded = state or {}
    pkg = active_package or {}
    mode = normalize_autonomy_mode(autonomy_mode or loaded.get("autonomy_mode"))
    mode_state = build_autonomy_mode_state(mode=mode)
    next_task = select_next_task(loaded)
    governance_status = str(
        loaded.get("governance_status")
        or (loaded.get("governance_result") or {}).get("governance_status")
        or "none"
    ).strip().lower()
    governance_result = loaded.get("governance_result") if isinstance(loaded.get("governance_result"), dict) else {}
    governance_resolution_state = str(governance_result.get("resolution_state") or "").strip().lower()
    governance_routing_outcome = str(governance_result.get("routing_outcome") or "").strip().lower()
    enforcement_status = str(
        loaded.get("enforcement_status")
        or (loaded.get("enforcement_result") or {}).get("enforcement_status")
        or "none"
    ).strip().lower()
    guardrail_status = str(
        loaded.get("guardrail_status")
        or (loaded.get("guardrail_result") or {}).get("guardrail_status")
        or "none"
    ).strip().lower()
    repair_required = bool(((pkg.get("recovery_summary") or {}).get("repair_required")))
    integrity_status = str(((pkg.get("integrity_verification") or {}).get("integrity_status") or "")).strip().lower()
    risk_band = str(((pkg.get("evaluation_summary") or {}).get("failure_risk_band") or "")).strip().lower()
    local_next = str(((pkg.get("local_analysis_summary") or {}).get("suggested_next_action") or "")).strip().lower()
    package_requires_human = bool(pkg.get("requires_human_approval"))
    aegis_decision = str(pkg.get("aegis_decision") or "").strip().lower()

    decision: dict[str, Any] = {
        "selected_project_key": project_key,
        "selected_next_task": _task_label(next_task),
        "selected_action": "pause",
        "selected_backend_path": _determine_backend_path(state=loaded, package=pkg),
        "routing_reason": "Routing awaiting project context.",
        "routing_confidence": 0.5,
        "routing_confidence_band": "guarded",
        "autonomy_mode": mode,
        "routing_status": "ready",
        "requires_operator_review": False,
        "bounded": True,
        "routing_inputs": {
            "governance_status": governance_status,
            "enforcement_status": enforcement_status,
            "guardrail_status": guardrail_status,
            "package_requires_human_approval": package_requires_human,
            "aegis_decision": aegis_decision,
            "integrity_status": integrity_status,
            "failure_risk_band": risk_band,
            "local_analysis_next_action": local_next,
            "autopilot_status": str(loaded.get("autopilot_status") or "").strip().lower(),
        },
        "mode_state": mode_state,
    }

    if governance_routing_outcome in ("pause", "escalate", "stop") and governance_resolution_state != "resolved":
        routing_status = "paused"
        if governance_routing_outcome == "escalate":
            routing_status = "escalated"
        elif governance_routing_outcome == "stop":
            routing_status = "stopped"
        decision.update(
            {
                "selected_action": governance_routing_outcome,
                "routing_status": routing_status,
                "routing_reason": str(governance_result.get("reason") or governance_result.get("decision_reason") or "Governance conflict paused routing."),
                "routing_confidence": 0.99,
                "routing_confidence_band": "high",
                "requires_operator_review": governance_routing_outcome != "stop",
            }
        )
    elif enforcement_status in ("approval_required", "blocked"):
        decision.update(
            {
                "selected_action": "escalate",
                "routing_status": "escalated",
                "routing_reason": "Enforcement requires operator action before routing may continue.",
                "routing_confidence": 0.98,
                "routing_confidence_band": "high",
                "requires_operator_review": True,
            }
        )
    elif governance_status in ("approval_required", "blocked", "rejected"):
        decision.update(
            {
                "selected_action": "escalate",
                "routing_status": "escalated",
                "routing_reason": "Governance gate blocks progress.",
                "routing_confidence": 0.98,
                "routing_confidence_band": "high",
                "requires_operator_review": True,
            }
        )
    elif guardrail_status in ("blocked", "error_fallback") or repair_required:
        decision.update(
            {
                "selected_action": "stop" if repair_required else "escalate",
                "routing_status": "escalated",
                "routing_reason": "Repair or guardrail issue requires operator review.",
                "routing_confidence": 0.97,
                "routing_confidence_band": "high",
                "requires_operator_review": True,
            }
        )
    elif package_requires_human or aegis_decision == "approval_required":
        decision.update(
            {
                "selected_action": "escalate",
                "routing_status": "escalated",
                "routing_reason": "Approval is required and routing must not bypass it.",
                "routing_confidence": 0.99,
                "routing_confidence_band": "high",
                "requires_operator_review": True,
            }
        )
    elif integrity_status in ("issues_detected", "verification_failed"):
        decision.update(
            {
                "selected_action": "escalate",
                "routing_status": "escalated",
                "routing_reason": "Integrity issues detected; escalate instead of continuing.",
                "routing_confidence": 0.99,
                "routing_confidence_band": "high",
                "requires_operator_review": True,
            }
        )
    elif risk_band in ("high", "critical"):
        decision.update(
            {
                "selected_action": "escalate",
                "routing_status": "escalated",
                "routing_reason": "Abacus evaluation risk is beyond the safe threshold.",
                "routing_confidence": 0.95,
                "routing_confidence_band": "high",
                "requires_operator_review": True,
            }
        )
    elif local_next in ("investigate_failure", "initiate_rollback_repair", "review_integrity"):
        decision.update(
            {
                "selected_action": "escalate",
                "routing_status": "escalated",
                "routing_reason": "NemoClaw recommends a high-risk follow-up action.",
                "routing_confidence": 0.95,
                "routing_confidence_band": "high",
                "requires_operator_review": True,
            }
        )
    elif pkg:
        package_stage = "continue"
        if str(pkg.get("decision_status") or "").strip().lower() == "pending":
            package_stage = "decision"
        elif str(pkg.get("eligibility_status") or "").strip().lower() == "pending":
            package_stage = "eligibility"
        elif str(pkg.get("release_status") or "").strip().lower() == "pending":
            package_stage = "release"
        elif str(pkg.get("handoff_status") or "").strip().lower() == "pending":
            package_stage = "handoff"
        elif str(pkg.get("execution_status") or "").strip().lower() == "pending":
            package_stage = "execute"
        elif str(pkg.get("evaluation_status") or "").strip().lower() != "completed":
            package_stage = "evaluate"
        elif str(pkg.get("local_analysis_status") or "").strip().lower() != "completed":
            package_stage = "local_analysis"
        decision.update(
            {
                "selected_action": package_stage,
                "routing_status": "ready",
                "routing_reason": "Continuing bounded execution package pipeline via existing governed stages.",
                "routing_confidence": 0.88,
                "routing_confidence_band": "high",
            }
        )
    elif next_task:
        decision.update(
            {
                "selected_action": "prepare_package",
                "routing_status": "ready",
                "routing_reason": "Next bounded task is ready to be packaged for existing governance flow.",
                "routing_confidence": 0.84,
                "routing_confidence_band": "high",
            }
        )
    else:
        decision.update(
            {
                "selected_action": "stop",
                "routing_status": "stopped",
                "routing_reason": "No valid next bounded task exists.",
                "routing_confidence": 0.92,
                "routing_confidence_band": "high",
            }
        )

    mode_gate = evaluate_mode_transition(
        mode=mode,
        proposed_action=str(decision.get("selected_action") or "pause"),
        package=pkg,
        routing_result=decision,
    )
    decision["mode_state"] = {
        "autonomy_mode": mode_gate.get("autonomy_mode"),
        "autonomy_mode_status": mode_gate.get("autonomy_mode_status"),
        "autonomy_mode_reason": mode_gate.get("autonomy_mode_reason"),
        "allowed_actions": mode_gate.get("allowed_actions") or [],
        "blocked_actions": mode_gate.get("blocked_actions") or [],
        "escalation_threshold": mode_gate.get("escalation_threshold"),
        "approval_required_actions": mode_gate.get("approval_required_actions") or [],
    }
    decision["mode_gate"] = {
        "action_allowed": bool(mode_gate.get("action_allowed")),
        "requires_operator_approval": bool(mode_gate.get("requires_operator_approval")),
        "must_pause": bool(mode_gate.get("must_pause")),
        "must_escalate": bool(mode_gate.get("must_escalate")),
        "effective_action": mode_gate.get("effective_action") or decision.get("selected_action"),
        "mode_gate_reason": mode_gate.get("mode_gate_reason") or "",
    }
    if not decision["mode_gate"]["action_allowed"]:
        effective = str(decision["mode_gate"].get("effective_action") or "operator_review")
        decision["selected_action"] = "pause" if effective == "pause" else "escalate"
        decision["routing_status"] = "paused" if effective == "pause" else "escalated"
        reason = str(decision["mode_gate"].get("mode_gate_reason") or "mode_policy_blocked_action")
        decision["routing_reason"] = reason
        decision["requires_operator_review"] = True
        decision["routing_confidence"] = max(float(decision.get("routing_confidence") or 0.0), 0.9)
        decision["routing_confidence_band"] = "high"

    return decision
