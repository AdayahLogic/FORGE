from __future__ import annotations

from datetime import datetime
from typing import Any

from NEXUS.autonomy_modes import build_autonomy_mode_state, evaluate_mode_transition, normalize_autonomy_mode
from NEXUS.project_state import load_project_state
from NEXUS.registry import PROJECTS
from NEXUS.strategic_decision_engine import (
    build_actionable_items,
    build_mission_priorities,
    mission_priority_score,
    rank_actionable_items,
)


def _task_label(task: dict[str, Any] | None) -> str:
    row = task or {}
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    return str(row.get("task") or payload.get("description") or row.get("id") or "").strip()


def _normalize_tasks(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _now_iso() -> str:
    return datetime.now().isoformat()


def _normalize_project_id(value: Any) -> str:
    return str(value or "").strip().lower()


def _state_status(value: Any, default: str = "none") -> str:
    text = str(value or default).strip().lower()
    return text or default


def _state_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _readiness_signal(state: dict[str, Any]) -> str:
    package_id = str(state.get("execution_package_id") or state.get("autopilot_last_package_id") or "").strip()
    if package_id:
        return "active_package"
    if select_next_task(state):
        return "pending_task"
    return "idle"


def _blocked_reason(state: dict[str, Any]) -> str:
    governance_result = _state_dict(state.get("governance_result"))
    governance_outcome = _state_status(governance_result.get("routing_outcome"), "continue")
    governance_status = _state_status(state.get("governance_status") or governance_result.get("governance_status"))
    enforcement_status = _state_status(state.get("enforcement_status") or _state_dict(state.get("enforcement_result")).get("enforcement_status"))
    stop_rail_result = _state_dict(state.get("autonomy_stop_rail_result"))
    stop_rail_status = _state_status(state.get("autonomy_stop_rail_status") or stop_rail_result.get("status"), "ok")
    stop_rail_outcome = _state_status(stop_rail_result.get("routing_outcome"), "continue")
    routing_result = _state_dict(state.get("project_routing_result"))
    routing_status = _state_status(state.get("project_routing_status") or routing_result.get("routing_status"), "idle")
    autopilot_status = _state_status(state.get("autopilot_status"), "idle")
    readiness = _readiness_signal(state)

    if governance_outcome in ("pause", "escalate", "stop"):
        return f"governance_{governance_outcome}"
    if governance_status in ("blocked", "approval_required", "review_required", "rejected", "error_fallback"):
        return f"governance_{governance_status}"
    if enforcement_status in ("blocked", "approval_required", "hold", "error_fallback"):
        return f"enforcement_{enforcement_status}"
    if stop_rail_outcome in ("pause", "escalate", "stop"):
        return f"stop_rail_{stop_rail_outcome}"
    if stop_rail_status in ("paused", "escalated", "stopped"):
        return f"stop_rail_{stop_rail_status}"
    if routing_status in ("paused", "escalated", "stopped", "blocked"):
        return f"routing_{routing_status}"
    if autopilot_status in ("paused", "escalated", "blocked"):
        return f"autopilot_{autopilot_status}"
    if readiness == "idle":
        return "not_ready"
    return ""


def _candidate_priority(project_id: str, state: dict[str, Any]) -> tuple[int, int, float, int, str]:
    readiness = _readiness_signal(state)
    queue = _normalize_tasks(state.get("task_queue_snapshot") or state.get("task_queue"))
    pending = [
        item for item in queue if _state_status(item.get("status"), "pending") in ("", "pending", "queued", "ready")
    ]
    min_priority = min((int(item.get("priority") or 0) for item in pending), default=9999)
    autopilot_status = _state_status(state.get("autopilot_status"), "idle")
    active_session_rank = 0 if autopilot_status in ("running", "ready") else 1
    readiness_rank = 0 if readiness == "active_package" else 1
    mission_score = float(
        mission_priority_score(project_id=project_id, state=state).get("mission_priority_score") or 0.0
    )
    # Keep the legacy deterministic ordering while adding strategic mission score.
    return (readiness_rank, active_session_rank, -mission_score, min_priority, project_id)


def evaluate_project_selection(
    *,
    requested_project_id: str | None = None,
    candidate_project_ids: list[str] | None = None,
    user_input: str | None = None,
    states_by_project: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    requested = _normalize_project_id(requested_project_id)
    loaded_states = states_by_project or {}
    source_candidates = list(candidate_project_ids or [])
    if not source_candidates:
        source_candidates = list(PROJECTS.keys()) or list(loaded_states.keys())
    candidates = [_normalize_project_id(project_id) for project_id in source_candidates if _normalize_project_id(project_id)]
    if requested and requested not in candidates:
        candidates.append(requested)
    for project_id in loaded_states.keys():
        normalized_id = _normalize_project_id(project_id)
        if normalized_id and normalized_id not in candidates:
            candidates.append(normalized_id)
    candidates = sorted(set(candidates))

    recorded_at = _now_iso()
    if not candidates:
        return {
            "status": "blocked",
            "selected_project_id": "",
            "candidate_project_ids": [],
            "selection_reason": "No registered projects are available for governed selection.",
            "priority_basis": "requested_project > active_package > active_autopilot_session > pending_task_priority > project_id",
            "contention_detected": False,
            "blocked_projects": [],
            "eligible_projects": [],
            "routing_outcome": "stop",
            "governance_trace": {
                "requested_project_id": requested,
                "user_input": str(user_input or ""),
                "project_evaluations": {},
                "selection_policy": [
                    "requested_project_first",
                    "active_package_preferred",
                    "active_autopilot_session_preferred",
                    "lowest_pending_priority_wins",
                    "project_id_tie_break",
                ],
            },
            "recorded_at": recorded_at,
        }

    project_evaluations: dict[str, Any] = {}
    state_cache: dict[str, dict[str, Any]] = {}
    eligible: list[str] = []
    blocked: list[str] = []
    for project_id in candidates:
        state = _state_dict(loaded_states.get(project_id))
        if not state:
            path = PROJECTS.get(project_id, {}).get("path")
            state = load_project_state(path) if path else {}
        if not isinstance(state, dict) or state.get("load_error"):
            state = {}
        state_cache[project_id] = dict(state)
        blocked_reason = _blocked_reason(state)
        readiness = _readiness_signal(state)
        evaluation = {
            "project_id": project_id,
            "blocked_reason": blocked_reason,
            "eligible": blocked_reason == "",
            "readiness_signal": readiness,
            "governance_status": _state_status(state.get("governance_status")),
            "governance_routing_outcome": _state_status(_state_dict(state.get("governance_result")).get("routing_outcome"), "continue"),
            "enforcement_status": _state_status(state.get("enforcement_status")),
            "autopilot_status": _state_status(state.get("autopilot_status"), "idle"),
            "autonomy_stop_rail_status": _state_status(state.get("autonomy_stop_rail_status"), "ok"),
            "project_routing_status": _state_status(state.get("project_routing_status"), "idle"),
            "pending_task_count": len(
                [
                    item
                    for item in _normalize_tasks(state.get("task_queue_snapshot") or state.get("task_queue"))
                    if _state_status(item.get("status"), "pending") in ("", "pending", "queued", "ready")
                ]
            ),
            "execution_package_id": str(state.get("execution_package_id") or state.get("autopilot_last_package_id") or ""),
            "mission_priority_score": float(
                mission_priority_score(project_id=project_id, state=state).get("mission_priority_score") or 0.0
            ),
        }
        project_evaluations[project_id] = evaluation
        if evaluation["eligible"]:
            eligible.append(project_id)
        else:
            blocked.append(project_id)

    contention_detected = len(eligible) > 1
    if requested and requested in eligible:
        selected = requested
        selection_reason = "Requested project remained eligible under current governance and readiness checks."
        priority_basis = "requested_project > active_package > active_autopilot_session > pending_task_priority > project_id"
    elif eligible:
        def _eligible_state(project_id: str) -> dict[str, Any]:
            state = _state_dict(loaded_states.get(project_id))
            if state:
                return state
            path = PROJECTS.get(project_id, {}).get("path")
            return _state_dict(load_project_state(path)) if path else {}

        selected = sorted(eligible, key=lambda project_id: _candidate_priority(project_id, _eligible_state(project_id)))[0]
        selected_eval = project_evaluations.get(selected) or {}
        if selected_eval.get("readiness_signal") == "active_package":
            selection_reason = "Selected the eligible project with an active governed package already in flight."
        elif selected_eval.get("autopilot_status") in ("running", "ready"):
            selection_reason = "Selected the eligible project with an already active governed autopilot session."
        else:
            selection_reason = "Resolved eligible-project contention using the deterministic pending-task priority order."
        priority_basis = "active_package > active_autopilot_session > pending_task_priority > project_id"
    else:
        selected = ""
        selection_reason = "No eligible project may advance; all candidates are blocked or not ready."
        priority_basis = "requested_project > active_package > active_autopilot_session > pending_task_priority > project_id"

    status = "selected" if selected else ("blocked" if blocked else "deferred")
    routing_outcome = "continue" if selected else ("defer" if blocked else "pause")
    if not selected and candidates and blocked:
        routing_outcome = "defer"
    if not selected and not blocked:
        routing_outcome = "pause"
    mission_summary = build_mission_priorities(states_by_project=state_cache)

    return {
        "status": status,
        "selected_project_id": selected,
        "candidate_project_ids": candidates,
        "selection_reason": selection_reason,
        "priority_basis": priority_basis,
        "contention_detected": contention_detected,
        "blocked_projects": blocked,
        "eligible_projects": eligible,
        "routing_outcome": routing_outcome,
        "mission_priorities": mission_summary.get("mission_priorities") or [],
        "mission_conflict_detection": mission_summary.get("mission_conflicts") or [],
        "mission_selection_strategy": mission_summary.get("mission_selection_strategy") or "",
        "governance_trace": {
            "requested_project_id": requested,
            "user_input": str(user_input or ""),
            "project_evaluations": project_evaluations,
            "selection_policy": [
                "requested_project_first_if_eligible",
                "active_package_preferred",
                "active_autopilot_session_preferred",
                "lowest_pending_priority_wins",
                "project_id_tie_break",
            ],
        },
        "recorded_at": recorded_at,
    }


def select_project_for_workflow(
    *,
    requested_project_id: str | None = None,
    user_input: str | None = None,
    states_by_project: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    selection = evaluate_project_selection(
        requested_project_id=requested_project_id,
        candidate_project_ids=[requested_project_id] if _normalize_project_id(requested_project_id) else None,
        user_input=user_input,
        states_by_project=states_by_project,
    )
    if selection.get("selected_project_id"):
        return selection
    requested = _normalize_project_id(requested_project_id)
    if requested:
        return {
            **selection,
            "status": "blocked",
            "selected_project_id": requested,
            "selection_reason": str(selection.get("selection_reason") or "Requested project selection deferred."),
            "routing_outcome": "defer",
        }
    return selection


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
    ranked = rank_actionable_items(build_actionable_items(state=loaded), top_n=20)
    task_lookup = {
        str(item.get("id") or ""): item
        for item in pending
        if str(item.get("id") or "").strip()
    }
    for row in ranked:
        if str(row.get("action_type") or "") != "mission_task":
            continue
        task_id = str(row.get("target_ref") or "")
        if task_id in task_lookup:
            return task_lookup[task_id]
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


def _latest_runtime_target_selection(state: dict[str, Any]) -> dict[str, Any]:
    dispatch_result = state.get("dispatch_result") if isinstance(state.get("dispatch_result"), dict) else {}
    selection = dispatch_result.get("runtime_target_selection") if isinstance(dispatch_result.get("runtime_target_selection"), dict) else {}
    if selection:
        return dict(selection)
    execution_bridge = state.get("execution_bridge_summary") if isinstance(state.get("execution_bridge_summary"), dict) else {}
    return {
        "status": str(execution_bridge.get("runtime_selection_status") or "").strip().lower(),
        "selected_target_id": str(execution_bridge.get("selected_runtime_target") or "").strip().lower(),
        "selection_reason": str(execution_bridge.get("runtime_selection_reason") or "").strip(),
        "readiness_status": "",
        "availability_status": "",
        "denial_reason": "",
    }


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
    stop_rail_result = loaded.get("autonomy_stop_rail_result") if isinstance(loaded.get("autonomy_stop_rail_result"), dict) else {}
    stop_rail_status = str(loaded.get("autonomy_stop_rail_status") or stop_rail_result.get("status") or "ok").strip().lower()
    stop_rail_outcome = str(stop_rail_result.get("routing_outcome") or "").strip().lower()
    runtime_target_selection = _latest_runtime_target_selection(loaded)

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
            "autonomy_stop_rail_status": stop_rail_status,
            "selected_runtime_target_id": str(runtime_target_selection.get("selected_target_id") or ""),
            "runtime_target_selection_status": str(runtime_target_selection.get("status") or ""),
            "runtime_target_selection_reason": str(runtime_target_selection.get("selection_reason") or ""),
        },
        "mode_state": mode_state,
        "autonomy_stop_rail_result": stop_rail_result,
        "runtime_target_selection": runtime_target_selection,
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
    elif stop_rail_status in ("paused", "escalated", "stopped") and stop_rail_outcome in ("pause", "escalate", "stop"):
        routing_status = "paused" if stop_rail_outcome == "pause" else ("stopped" if stop_rail_outcome == "stop" else "escalated")
        decision.update(
            {
                "selected_action": stop_rail_outcome,
                "routing_status": routing_status,
                "routing_reason": str(stop_rail_result.get("stop_reason") or "autonomy_stop_rail_active"),
                "routing_confidence": 0.99,
                "routing_confidence_band": "high",
                "requires_operator_review": stop_rail_outcome != "stop",
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
        "autonomy_stop_rail_config": mode_state.get("autonomy_stop_rail_config") or {},
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
