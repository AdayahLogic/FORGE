from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from NEXUS.approval_builder import build_approval_record
from NEXUS.approval_registry import append_approval_record_safe, normalize_approval_record
from NEXUS.dispatch_planner import build_dispatch_plan_safe
from NEXUS.execution_package_builder import build_execution_package_safe
from NEXUS.execution_package_registry import (
    get_execution_package_file_path,
    read_execution_package,
    record_execution_package_decision_safe,
    record_execution_package_eligibility_safe,
    record_execution_package_evaluation_safe,
    record_execution_package_execution_safe,
    record_execution_package_handoff_safe,
    record_execution_package_local_analysis_safe,
    record_execution_package_release_safe,
    write_execution_package_safe,
)
from NEXUS.autonomy_modes import (
    DEFAULT_AUTONOMY_MODE,
    build_autonomy_mode_state,
    get_mode_stop_rail_config,
    normalize_autonomy_mode,
)
from NEXUS.executor_router import route_executor
from NEXUS.mission_system import (
    build_mission_packet,
    evaluate_mission_stop_conditions,
    normalize_mission_packet,
)
from NEXUS.project_routing import build_project_routing_decision, select_next_task
from NEXUS.project_state import load_project_state, update_project_state_fields
from NEXUS.global_control_state import evaluate_routing_enforcement
from NEXUS.mission_queue_orchestrator import (
    backpressure_status as mission_backpressure_status,
    claim_next_work_item,
    complete_work_item_failure,
    complete_work_item_success,
    enqueue_mission_work_item,
    recover_expired_leases,
    renew_work_item_lease,
)


AUTOPILOT_STATUSES = {
    "off",
    "idle",
    "ready",
    "evaluating",
    "awaiting_approval",
    "executing",
    "running",
    "paused",
    "escalated",
    "completed",
    "blocked",
    "error_fallback",
}
AUTOPILOT_LOOP_STATES = {
    "off",
    "idle",
    "evaluating",
    "awaiting_approval",
    "executing",
    "paused",
    "blocked",
}
AUTOPILOT_DEFAULT_MODE = "supervised_bounded"
AUTOPILOT_DEFAULT_ITERATION_LIMIT = 1
AUTOPILOT_MAX_ITERATION_LIMIT = 25
AUTOPILOT_DEFAULT_RETRY_LIMIT = 1
AUTOPILOT_MAX_RETRY_LIMIT = 10
AUTOPILOT_DEFAULT_RUNTIME_LIMIT_SECONDS = 900
AUTOPILOT_MAX_RUNTIME_LIMIT_SECONDS = 14400
AUTOPILOT_DEFAULT_OPERATION_LIMIT = 8
AUTOPILOT_MAX_OPERATION_LIMIT = 100
AUTOPILOT_ACTOR = "project_autopilot"
ABACUS_ACTOR = "abacus"
NEMOCLAW_ACTOR = "nemoclaw"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _elapsed_seconds(started_at: Any, current_time: datetime | None = None) -> int:
    start_dt = _parse_iso_datetime(started_at)
    if start_dt is None:
        return 0
    now_dt = current_time or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)
    elapsed = int((now_dt.astimezone(timezone.utc) - start_dt).total_seconds())
    return max(0, elapsed)


def _clamp_iteration_limit(value: Any) -> int:
    try:
        limit = int(value)
    except Exception:
        limit = AUTOPILOT_DEFAULT_ITERATION_LIMIT
    return max(1, min(limit, AUTOPILOT_MAX_ITERATION_LIMIT))


def _clamp_retry_limit(value: Any) -> int:
    try:
        limit = int(value)
    except Exception:
        limit = AUTOPILOT_DEFAULT_RETRY_LIMIT
    return max(1, min(limit, AUTOPILOT_MAX_RETRY_LIMIT))


def _clamp_runtime_limit(value: Any) -> int:
    try:
        limit = int(value)
    except Exception:
        limit = AUTOPILOT_DEFAULT_RUNTIME_LIMIT_SECONDS
    return max(1, min(limit, AUTOPILOT_MAX_RUNTIME_LIMIT_SECONDS))


def _clamp_operation_limit(value: Any) -> int:
    try:
        limit = int(value)
    except Exception:
        limit = AUTOPILOT_DEFAULT_OPERATION_LIMIT
    return max(1, min(limit, AUTOPILOT_MAX_OPERATION_LIMIT))


def _normalize_status(value: Any) -> str:
    status = str(value or "idle").strip().lower()
    return status if status in AUTOPILOT_STATUSES else "idle"


def _normalize_task_queue(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _task_label(task: dict[str, Any] | None) -> str:
    t = task or {}
    payload = t.get("payload") if isinstance(t.get("payload"), dict) else {}
    return str(t.get("task") or payload.get("description") or t.get("id") or "").strip()


def _select_next_task(state: dict[str, Any]) -> dict[str, Any] | None:
    return select_next_task(state)


def _mark_task_completed(state: dict[str, Any], task_id: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    def _update(queue: Any) -> list[dict[str, Any]]:
        rows = _normalize_task_queue(queue)
        updated = False
        for row in rows:
            if updated:
                continue
            if task_id and str(row.get("id") or "") == task_id:
                row["status"] = "completed"
                updated = True
            elif not task_id and str(row.get("status") or "").strip().lower() in ("", "pending", "queued", "ready"):
                row["status"] = "completed"
                updated = True
        return rows

    return _update(state.get("task_queue")), _update(state.get("task_queue_snapshot") or state.get("task_queue"))


def _normalize_session(project_name: str, state: dict[str, Any]) -> dict[str, Any]:
    progress = state.get("autopilot_progress_summary") if isinstance(state.get("autopilot_progress_summary"), dict) else {}
    stop_rail_config = state.get("autonomy_stop_rail_config") if isinstance(state.get("autonomy_stop_rail_config"), dict) else {}
    current_counts = state.get("autonomy_current_counts") if isinstance(state.get("autonomy_current_counts"), dict) else {}
    stop_rail_result = state.get("autonomy_stop_rail_result") if isinstance(state.get("autonomy_stop_rail_result"), dict) else {}
    mission_packet = normalize_mission_packet(state.get("mission_packet") if isinstance(state.get("mission_packet"), dict) else {})
    loop_state = str(state.get("autopilot_loop_state") or "").strip().lower()
    if loop_state not in AUTOPILOT_LOOP_STATES:
        loop_state = "idle"
    session = {
        "autopilot_enabled": bool(state.get("autopilot_enabled", False)),
        "autopilot_status": _normalize_status(state.get("autopilot_status")),
        "autopilot_loop_state": loop_state,
        "autopilot_last_run_at": str(state.get("autopilot_last_run_at") or ""),
        "autopilot_next_run_at": str(state.get("autopilot_next_run_at") or ""),
        "autopilot_current_focus": str(state.get("autopilot_current_focus") or mission_packet.get("mission_type") or ""),
        "autopilot_requires_operator_review": bool(state.get("autopilot_requires_operator_review")),
        "autopilot_session_id": str(state.get("autopilot_session_id") or ""),
        "autopilot_project_key": str(state.get("autopilot_project_key") or project_name or ""),
        "autopilot_mode": str(state.get("autopilot_mode") or AUTOPILOT_DEFAULT_MODE),
        "autopilot_iteration_count": max(0, int(state.get("autopilot_iteration_count") or 0)),
        "autopilot_iteration_limit": _clamp_iteration_limit(
            state.get("autopilot_iteration_limit") or AUTOPILOT_DEFAULT_ITERATION_LIMIT
        ),
        "autopilot_started_at": str(state.get("autopilot_started_at") or ""),
        "autopilot_updated_at": str(state.get("autopilot_updated_at") or ""),
        "autopilot_last_package_id": str(state.get("autopilot_last_package_id") or ""),
        "autopilot_last_result": state.get("autopilot_last_result") if isinstance(state.get("autopilot_last_result"), dict) else {},
        "autopilot_next_action": str(state.get("autopilot_next_action") or ""),
        "autopilot_stop_reason": str(state.get("autopilot_stop_reason") or ""),
        "autopilot_escalation_reason": str(state.get("autopilot_escalation_reason") or ""),
        "autopilot_progress_summary": dict(progress),
        "autopilot_retry_count": max(0, int(state.get("autopilot_retry_count") or 0)),
        "autopilot_retry_limit": _clamp_retry_limit(
            state.get("autopilot_retry_limit")
            or stop_rail_config.get("max_retries")
            or AUTOPILOT_DEFAULT_RETRY_LIMIT
        ),
        "autopilot_operation_count": max(0, int(state.get("autopilot_operation_count") or 0)),
        "autopilot_operation_limit": _clamp_operation_limit(
            state.get("autopilot_operation_limit")
            or stop_rail_config.get("max_operations")
            or AUTOPILOT_DEFAULT_OPERATION_LIMIT
        ),
        "autopilot_runtime_started_at": str(
            state.get("autopilot_runtime_started_at")
            or state.get("autopilot_started_at")
            or ""
        ),
        "autopilot_runtime_limit_seconds": _clamp_runtime_limit(
            state.get("autopilot_runtime_limit_seconds")
            or stop_rail_config.get("max_runtime_seconds")
            or AUTOPILOT_DEFAULT_RUNTIME_LIMIT_SECONDS
        ),
        "autonomy_stop_rail_config": dict(stop_rail_config),
        "autonomy_current_counts": dict(current_counts),
        "autonomy_stop_rail_status": str(state.get("autonomy_stop_rail_status") or stop_rail_result.get("status") or "ok"),
        "autonomy_stop_rail_result": dict(stop_rail_result),
        "autonomy_governance_trace": dict(state.get("autonomy_governance_trace") or {}),
        "mission_packet": mission_packet,
        "mission_status": str(state.get("mission_status") or mission_packet.get("mission_status") or "proposed"),
        "executor_route": str(state.get("executor_route") or ""),
        "executor_route_reason": str(state.get("executor_route_reason") or ""),
        "executor_route_confidence": float(state.get("executor_route_confidence") or 0.0),
        "executor_route_status": str(state.get("executor_route_status") or ""),
        "executor_task_type": str(state.get("executor_task_type") or ""),
        "executor_fallback_route": str(state.get("executor_fallback_route") or ""),
        "mission_stop_condition_hit": bool(state.get("mission_stop_condition_hit")),
        "mission_stop_condition_reason": str(state.get("mission_stop_condition_reason") or ""),
        "mission_escalation_required": bool(state.get("mission_escalation_required")),
    }
    if not session["autopilot_started_at"] and session["autopilot_session_id"]:
        session["autopilot_started_at"] = str(state.get("saved_at") or "")
    if not session["autopilot_updated_at"]:
        session["autopilot_updated_at"] = str(state.get("saved_at") or "")
    if not session["autopilot_runtime_started_at"]:
        session["autopilot_runtime_started_at"] = session["autopilot_started_at"]
    return session


def _session_payload(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "autopilot_enabled": session.get("autopilot_enabled"),
        "autopilot_status": session.get("autopilot_status"),
        "autopilot_loop_state": session.get("autopilot_loop_state"),
        "autopilot_last_run_at": session.get("autopilot_last_run_at"),
        "autopilot_next_run_at": session.get("autopilot_next_run_at"),
        "autopilot_current_focus": session.get("autopilot_current_focus"),
        "autopilot_requires_operator_review": session.get("autopilot_requires_operator_review"),
        "autopilot_session_id": session.get("autopilot_session_id"),
        "autopilot_project_key": session.get("autopilot_project_key"),
        "autopilot_mode": session.get("autopilot_mode"),
        "autopilot_iteration_count": session.get("autopilot_iteration_count"),
        "autopilot_iteration_limit": session.get("autopilot_iteration_limit"),
        "autopilot_started_at": session.get("autopilot_started_at"),
        "autopilot_updated_at": session.get("autopilot_updated_at"),
        "autopilot_last_package_id": session.get("autopilot_last_package_id"),
        "autopilot_last_result": session.get("autopilot_last_result"),
        "autopilot_next_action": session.get("autopilot_next_action"),
        "autopilot_stop_reason": session.get("autopilot_stop_reason"),
        "autopilot_escalation_reason": session.get("autopilot_escalation_reason"),
        "autopilot_progress_summary": session.get("autopilot_progress_summary"),
        "autopilot_retry_count": session.get("autopilot_retry_count"),
        "autopilot_retry_limit": session.get("autopilot_retry_limit"),
        "autopilot_operation_count": session.get("autopilot_operation_count"),
        "autopilot_operation_limit": session.get("autopilot_operation_limit"),
        "autopilot_runtime_started_at": session.get("autopilot_runtime_started_at"),
        "autopilot_runtime_limit_seconds": session.get("autopilot_runtime_limit_seconds"),
        "autonomy_stop_rail_config": session.get("autonomy_stop_rail_config"),
        "autonomy_current_counts": session.get("autonomy_current_counts"),
        "autonomy_stop_rail_status": session.get("autonomy_stop_rail_status"),
        "autonomy_stop_rail_result": session.get("autonomy_stop_rail_result"),
        "autonomy_governance_trace": session.get("autonomy_governance_trace"),
        "mission_packet": session.get("mission_packet"),
        "mission_status": session.get("mission_status"),
        "executor_route": session.get("executor_route"),
        "executor_route_reason": session.get("executor_route_reason"),
        "executor_route_confidence": session.get("executor_route_confidence"),
        "executor_route_status": session.get("executor_route_status"),
        "executor_task_type": session.get("executor_task_type"),
        "executor_fallback_route": session.get("executor_fallback_route"),
        "mission_stop_condition_hit": session.get("mission_stop_condition_hit"),
        "mission_stop_condition_reason": session.get("mission_stop_condition_reason"),
        "mission_escalation_required": session.get("mission_escalation_required"),
    }


def _persist_session(project_path: str, session: dict[str, Any], *, extra_fields: dict[str, Any] | None = None) -> None:
    payload = _session_payload(session)
    if extra_fields:
        payload.update(extra_fields)
    update_project_state_fields(project_path, **payload)


def _approval_queue_fields(*, mission: dict[str, Any], risk_class: str, reason: str) -> dict[str, Any]:
    mission_status = str(mission.get("mission_status") or "proposed")
    requires_initial = bool(mission.get("mission_requires_initial_approval", True))
    requires_final = bool(mission.get("mission_requires_final_approval", True))
    if mission_status in ("awaiting_initial_approval", "proposed"):
        item_type = "mission_initial_approval"
    elif mission_status == "awaiting_final_review":
        item_type = "mission_final_acceptance"
    elif bool(mission.get("mission_stop_condition_hit")):
        item_type = "mission_escalation_review"
    else:
        item_type = "mission_progress"
    return {
        "approval_queue_item_type": item_type,
        "approval_queue_risk_class": risk_class,
        "approval_queue_reason": reason,
        "approval_queue_batchable": mission_status in ("proposed", "awaiting_initial_approval", "awaiting_final_review"),
        "approval_queue_requires_initial_approval": requires_initial,
        "approval_queue_requires_final_approval": requires_final,
        "approval_queue_escalation_reason": str(mission.get("mission_stop_condition_reason") or ""),
    }


def _autonomy_state_fields(mode: Any, reason: str | None = None) -> dict[str, Any]:
    return build_autonomy_mode_state(mode=normalize_autonomy_mode(mode), reason=reason)


def _global_execution_gate(
    *,
    project_path: str,
    project_name: str,
    runtime_target_id: str = "local",
    allocation_status: str = "selected",
    operation_type: str = "autonomy_loop",
) -> dict[str, Any]:
    return evaluate_routing_enforcement(
        project_path=project_path,
        project_name=project_name,
        runtime_target_id=runtime_target_id,
        allocation_status=allocation_status,
        mission_key=project_name,
        strategy_key=project_name,
        operation_type=operation_type,
    )


def _ensure_stop_rail_config(session: dict[str, Any], mode: Any) -> dict[str, Any]:
    config = dict(get_mode_stop_rail_config(mode))
    config["max_loops"] = _clamp_iteration_limit(
        session.get("autopilot_iteration_limit") or config.get("max_loops") or AUTOPILOT_DEFAULT_ITERATION_LIMIT
    )
    config["max_retries"] = _clamp_retry_limit(
        session.get("autopilot_retry_limit") or config.get("max_retries") or AUTOPILOT_DEFAULT_RETRY_LIMIT
    )
    config["max_runtime_seconds"] = _clamp_runtime_limit(
        session.get("autopilot_runtime_limit_seconds")
        or config.get("max_runtime_seconds")
        or AUTOPILOT_DEFAULT_RUNTIME_LIMIT_SECONDS
    )
    config["max_operations"] = _clamp_operation_limit(
        session.get("autopilot_operation_limit") or config.get("max_operations") or AUTOPILOT_DEFAULT_OPERATION_LIMIT
    )
    config["max_budget_units"] = _clamp_operation_limit(config.get("max_budget_units") or config["max_operations"])
    config["time_window"] = {"max_runtime_seconds": config["max_runtime_seconds"]}
    session["autopilot_iteration_limit"] = config["max_loops"]
    session["autopilot_retry_limit"] = config["max_retries"]
    session["autopilot_runtime_limit_seconds"] = config["max_runtime_seconds"]
    session["autopilot_operation_limit"] = config["max_operations"]
    session["autonomy_stop_rail_config"] = config
    return config


def _current_counts(session: dict[str, Any]) -> dict[str, int]:
    counts = {
        "loops": max(0, int(session.get("autopilot_iteration_count") or 0)),
        "retries": max(0, int(session.get("autopilot_retry_count") or 0)),
        "runtime_seconds": max(0, _elapsed_seconds(session.get("autopilot_runtime_started_at"))),
        "operations": max(0, int(session.get("autopilot_operation_count") or 0)),
        "budget_units": max(0, int(session.get("autopilot_operation_count") or 0)),
    }
    session["autonomy_current_counts"] = counts
    return counts


def _stop_action_for_mode(mode: Any, config: dict[str, Any], rail_type: str) -> str:
    normalized_mode = normalize_autonomy_mode(mode)
    if rail_type in ("runtime", "loops"):
        return "stop"
    if normalized_mode == "supervised_build":
        return "pause"
    if normalized_mode == "assisted_autopilot":
        return "escalate"
    return str(config.get("default_stop_action") or "stop").strip().lower() or "stop"


def _build_stop_rail_result(
    *,
    session: dict[str, Any],
    rail_type: str,
    current_value: int,
    limit_value: int,
    routing_outcome: str,
    stop_reason: str,
) -> dict[str, Any]:
    status_map = {"continue": "ok", "pause": "paused", "escalate": "escalated", "stop": "stopped"}
    return {
        "status": status_map.get(routing_outcome, "limited"),
        "autonomy_mode": normalize_autonomy_mode(session.get("autopilot_mode")),
        "rail_type": rail_type,
        "current_value": max(0, int(current_value or 0)),
        "limit_value": max(0, int(limit_value or 0)),
        "stop_reason": stop_reason,
        "routing_outcome": routing_outcome,
        "current_counts": dict(session.get("autonomy_current_counts") or {}),
        "rail_status": "hit" if routing_outcome != "continue" else "ok",
        "governance_trace": {
            "source": "project_autopilot",
            "autopilot_session_id": str(session.get("autopilot_session_id") or ""),
            "autopilot_status": str(session.get("autopilot_status") or ""),
            "autonomy_mode": normalize_autonomy_mode(session.get("autopilot_mode")),
        },
    }


def _evaluate_stop_rails(session: dict[str, Any], rail_types: tuple[str, ...] | None = None) -> dict[str, Any]:
    config = _ensure_stop_rail_config(session, session.get("autopilot_mode"))
    counts = _current_counts(session)
    checks = (
        ("loops", counts.get("loops", 0), int(config.get("max_loops") or 0), "iteration_limit_reached"),
        ("retries", counts.get("retries", 0), int(config.get("max_retries") or 0), "autonomy_retry_limit_reached"),
        ("runtime", counts.get("runtime_seconds", 0), int(config.get("max_runtime_seconds") or 0), "autonomy_runtime_limit_reached"),
        ("operations", counts.get("operations", 0), int(config.get("max_operations") or 0), "autonomy_operation_limit_reached"),
        ("budget", counts.get("budget_units", 0), int(config.get("max_budget_units") or 0), "autonomy_budget_limit_reached"),
    )
    for rail_type, current_value, limit_value, stop_reason in checks:
        if rail_types and rail_type not in rail_types:
            continue
        if limit_value > 0 and current_value >= limit_value:
            routing_outcome = _stop_action_for_mode(session.get("autopilot_mode"), config, rail_type)
            result = _build_stop_rail_result(
                session=session,
                rail_type=rail_type,
                current_value=current_value,
                limit_value=limit_value,
                routing_outcome=routing_outcome,
                stop_reason=stop_reason,
            )
            session["autonomy_stop_rail_status"] = result["status"]
            session["autonomy_stop_rail_result"] = result
            session["autonomy_governance_trace"] = dict(result.get("governance_trace") or {})
            return result
    result = _build_stop_rail_result(
        session=session,
        rail_type="loops",
        current_value=counts.get("loops", 0),
        limit_value=int(config.get("max_loops") or 0),
        routing_outcome="continue",
        stop_reason="",
    )
    session["autonomy_stop_rail_status"] = "ok"
    session["autonomy_stop_rail_result"] = result
    session["autonomy_governance_trace"] = dict(result.get("governance_trace") or {})
    return result


def _apply_stop_rail_outcome(
    *,
    session: dict[str, Any],
    state: dict[str, Any],
    project_path: str,
    project_name: str,
    stop_rail_result: dict[str, Any],
    current_task: dict[str, Any] | None = None,
    package: dict[str, Any] | None = None,
) -> dict[str, Any]:
    routing_outcome = str(stop_rail_result.get("routing_outcome") or "stop").strip().lower()
    status_map = {
        "pause": ("paused", "operator_review", True),
        "escalate": ("escalated", "operator_review", True),
        "stop": ("completed", "stop", False),
    }
    autopilot_status, next_action, operator_review_required = status_map.get(routing_outcome, ("completed", "stop", False))
    stop_reason = str(stop_rail_result.get("stop_reason") or "autonomy_limit_reached")
    session["autopilot_status"] = autopilot_status
    session["autopilot_loop_state"] = "paused" if operator_review_required else "idle"
    session["autopilot_next_action"] = next_action
    session["autopilot_stop_reason"] = stop_reason
    session["autopilot_escalation_reason"] = stop_reason if routing_outcome in ("pause", "escalate") else ""
    session["autopilot_requires_operator_review"] = operator_review_required
    session["autopilot_last_run_at"] = _now_iso()
    session["autopilot_next_run_at"] = ""
    session["autopilot_updated_at"] = _now_iso()
    session["autopilot_last_result"] = dict(stop_rail_result)
    session["autopilot_progress_summary"] = _build_progress_summary(
        state=state,
        session=session,
        current_task=current_task,
        package=package or {},
        next_suggested_step=next_action,
        operator_review_required=operator_review_required,
    )
    _persist_session(
        project_path,
        session,
        extra_fields=_routing_state_fields(
            project_name=project_name,
            state=state,
            session=session,
            active_package=package,
        ),
    )
    return {"status": "ok", "reason": stop_reason, "session": session}


def _routing_state_fields(
    *,
    project_name: str,
    state: dict[str, Any],
    session: dict[str, Any],
    active_package: dict[str, Any] | None = None,
) -> dict[str, Any]:
    routed_state = {
        **state,
        "autonomy_stop_rail_config": session.get("autonomy_stop_rail_config") or state.get("autonomy_stop_rail_config") or {},
        "autonomy_current_counts": session.get("autonomy_current_counts") or state.get("autonomy_current_counts") or {},
        "autonomy_stop_rail_status": session.get("autonomy_stop_rail_status") or state.get("autonomy_stop_rail_status") or "ok",
        "autonomy_stop_rail_result": session.get("autonomy_stop_rail_result") or state.get("autonomy_stop_rail_result") or {},
        "autonomy_governance_trace": session.get("autonomy_governance_trace") or state.get("autonomy_governance_trace") or {},
    }
    routing = build_project_routing_decision(
        project_key=project_name,
        state=routed_state,
        active_package=active_package,
        autonomy_mode=routed_state.get("autonomy_mode"),
    )
    mode_state = routing.get("mode_state") if isinstance(routing.get("mode_state"), dict) else _autonomy_state_fields(state.get("autonomy_mode"))
    return {
        "autonomy_mode": mode_state.get("autonomy_mode"),
        "autonomy_mode_status": mode_state.get("autonomy_mode_status"),
        "autonomy_mode_reason": mode_state.get("autonomy_mode_reason"),
        "autonomy_stop_rail_config": session.get("autonomy_stop_rail_config") or mode_state.get("autonomy_stop_rail_config") or {},
        "autonomy_current_counts": session.get("autonomy_current_counts") or {},
        "autonomy_stop_rail_status": session.get("autonomy_stop_rail_status") or "ok",
        "autonomy_stop_rail_result": session.get("autonomy_stop_rail_result") or {},
        "autonomy_governance_trace": session.get("autonomy_governance_trace") or {},
        "allowed_actions": mode_state.get("allowed_actions") or [],
        "blocked_actions": mode_state.get("blocked_actions") or [],
        "escalation_threshold": mode_state.get("escalation_threshold"),
        "approval_required_actions": mode_state.get("approval_required_actions") or [],
        "project_routing_status": routing.get("routing_status"),
        "project_routing_result": routing,
    }


def _build_progress_summary(
    *,
    state: dict[str, Any],
    session: dict[str, Any],
    current_task: dict[str, Any] | None = None,
    package: dict[str, Any] | None = None,
    latest_execution_result: dict[str, Any] | None = None,
    next_suggested_step: str | None = None,
    operator_review_required: bool | None = None,
) -> dict[str, Any]:
    pkg = package or {}
    evaluation_summary = pkg.get("evaluation_summary") if isinstance(pkg.get("evaluation_summary"), dict) else {}
    local_analysis_summary = pkg.get("local_analysis_summary") if isinstance(pkg.get("local_analysis_summary"), dict) else {}
    execution_receipt = pkg.get("execution_receipt") if isinstance(pkg.get("execution_receipt"), dict) else {}
    architect_plan = state.get("architect_plan") if isinstance(state.get("architect_plan"), dict) else {}
    objective = str(architect_plan.get("objective") or "").strip()
    if operator_review_required is None:
        operator_review_required = bool(pkg.get("requires_human_approval")) or session.get("autopilot_status") in ("paused", "escalated", "blocked")
    if not next_suggested_step:
        next_suggested_step = str(local_analysis_summary.get("suggested_next_action") or session.get("autopilot_next_action") or "stop")
    return {
        "project_objective_summary": objective,
        "current_autopilot_status": session.get("autopilot_status"),
        "current_task_summary": _task_label(current_task),
        "iteration_count": session.get("autopilot_iteration_count"),
        "iteration_limit": session.get("autopilot_iteration_limit"),
        "retry_count": session.get("autopilot_retry_count"),
        "retry_limit": session.get("autopilot_retry_limit"),
        "operation_count": session.get("autopilot_operation_count"),
        "operation_limit": session.get("autopilot_operation_limit"),
        "runtime_seconds": _elapsed_seconds(session.get("autopilot_runtime_started_at")),
        "runtime_limit_seconds": session.get("autopilot_runtime_limit_seconds"),
        "stop_rail_status": session.get("autonomy_stop_rail_status") or "ok",
        "stop_rail_result": session.get("autonomy_stop_rail_result") or {},
        "latest_package_id": str(pkg.get("package_id") or session.get("autopilot_last_package_id") or ""),
        "latest_execution_result": latest_execution_result or {
            "execution_status": pkg.get("execution_status") or "",
            "execution_reason": pkg.get("execution_reason") or {"code": "", "message": ""},
            "execution_receipt": execution_receipt,
            "recovery_summary": pkg.get("recovery_summary") or {},
            "integrity_verification": pkg.get("integrity_verification") or {},
        },
        "latest_evaluation_status": str(pkg.get("evaluation_status") or ""),
        "latest_local_analysis_status": str(pkg.get("local_analysis_status") or ""),
        "latest_evaluation_risk_band": str(evaluation_summary.get("failure_risk_band") or ""),
        "latest_local_analysis_next_action": str(local_analysis_summary.get("suggested_next_action") or ""),
        "next_suggested_step": str(next_suggested_step or ""),
        "operator_review_required": bool(operator_review_required),
    }


def _escalation_needed(package: dict[str, Any]) -> tuple[bool, str]:
    p = package or {}
    recovery = p.get("recovery_summary") if isinstance(p.get("recovery_summary"), dict) else {}
    rollback_repair = p.get("rollback_repair") if isinstance(p.get("rollback_repair"), dict) else {}
    integrity = p.get("integrity_verification") if isinstance(p.get("integrity_verification"), dict) else {}
    evaluation = p.get("evaluation_summary") if isinstance(p.get("evaluation_summary"), dict) else {}
    local_analysis = p.get("local_analysis_summary") if isinstance(p.get("local_analysis_summary"), dict) else {}
    local_next = str(local_analysis.get("suggested_next_action") or "").strip().lower()
    execution_status = str(p.get("execution_status") or "").strip().lower()
    if execution_status == "blocked":
        return True, "execution_blocked"
    if execution_status in ("failed", "rolled_back"):
        return True, "execution_failed"
    if bool(recovery.get("repair_required")):
        return True, "rollback_repair_required"
    if str(rollback_repair.get("rollback_repair_status") or "").strip().lower() in ("pending", "failed"):
        return True, "rollback_repair_required"
    if str(integrity.get("integrity_status") or "").strip().lower() in ("issues_detected", "verification_failed"):
        return True, "integrity_verification_failed"
    if str(evaluation.get("failure_risk_band") or "").strip().lower() in ("high", "critical"):
        return True, "evaluation_risk_high"
    if local_next in ("investigate_failure", "initiate_rollback_repair", "review_integrity"):
        return True, f"local_analysis_{local_next}"
    return False, ""


def _load_active_package(
    *,
    project_path: str,
    session: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any] | None:
    package_ids: list[str] = []
    for candidate in (session.get("autopilot_last_package_id"), state.get("execution_package_id")):
        package_id = str(candidate or "").strip()
        if package_id and package_id not in package_ids:
            package_ids.append(package_id)
    for package_id in package_ids:
        package = read_execution_package(project_path=project_path, package_id=package_id)
        if package:
            local_status = str(package.get("local_analysis_status") or "").strip().lower()
            execution_status = str(package.get("execution_status") or "").strip().lower()
            if local_status != "completed" or execution_status in ("pending", "blocked"):
                return package
    return None


def _build_mission_id(*, project_name: str, task: dict[str, Any] | None, package: dict[str, Any] | None) -> str:
    task_id = str((task or {}).get("id") or "").strip()
    package_id = str((package or {}).get("package_id") or "").strip()
    if task_id:
        return f"{project_name}:{task_id}"
    if package_id:
        return f"{project_name}:package:{package_id}"
    return f"{project_name}:mission"


def _create_autopilot_package(
    *,
    project_path: str,
    project_name: str,
    state: dict[str, Any],
    task: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any]]:
    project_summary = {
        "project_id": project_name,
        "project_name": project_name,
        "active_project": project_name,
        "project_path": project_path,
    }
    request_summary = _task_label(task)
    router_output = state.get("agent_routing_summary") if isinstance(state.get("agent_routing_summary"), dict) else {}
    planner_output = state.get("architect_plan") if isinstance(state.get("architect_plan"), dict) else {}
    execution_bridge_packet = dict(state.get("execution_bridge_summary") or {})
    dispatch_plan = build_dispatch_plan_safe(
        project_summary=project_summary,
        request={"summary": request_summary, "task_type": router_output.get("runtime_node") or "coder"},
        planner_output=planner_output,
        router_output=router_output,
        execution_bridge_packet=execution_bridge_packet,
    )

    aegis_result: dict[str, Any] = {}
    try:
        from AEGIS.aegis_contract import normalize_aegis_result
        from AEGIS.aegis_core import evaluate_action_safe

        aegis_result = normalize_aegis_result(
            evaluate_action_safe(
                request={
                    "project_name": project_name,
                    "project_path": project_path,
                    "runtime_target_id": (dispatch_plan.get("execution") or {}).get("runtime_target_id"),
                    "requires_human_approval": bool((dispatch_plan.get("execution") or {}).get("requires_human_approval")),
                    "action": "adapter_dispatch_call",
                }
            )
        )
    except Exception:
        aegis_result = {}

    approval_record = normalize_approval_record(
        build_approval_record(
            dispatch_plan=dispatch_plan,
            aegis_result=aegis_result,
            approval_type="execution_gate",
            reason=f"Autopilot trace for bounded task: {request_summary[:160]}",
        )
    )
    append_approval_record_safe(project_path=project_path, record=approval_record)
    approval_id = str(approval_record.get("approval_id") or "")
    requires_initial_approval = bool(approval_record.get("requires_human")) or bool(
        (dispatch_plan.get("execution") or {}).get("requires_human_approval")
    )
    mission_packet = build_mission_packet(
        mission_id=f"msn_{uuid.uuid4().hex[:12]}",
        task=task,
        objective=request_summary,
        mission_type=None,
        risk_level="medium",
        requires_initial_approval=requires_initial_approval,
        requires_final_approval=True,
    )
    mission_packet["mission_status"] = (
        "awaiting_initial_approval" if requires_initial_approval else "approved_for_execution"
    )
    routing = route_executor(
        task_summary=request_summary,
        task_type_hint=str((task or {}).get("type") or ""),
        allowed_executors=mission_packet.get("mission_allowed_executors") or [],
    )
    approval_queue = _approval_queue_fields(
        mission=mission_packet,
        risk_class=str(mission_packet.get("mission_risk_level") or "medium"),
        reason="Mission envelope created for bounded autopilot task.",
    )

    package = build_execution_package_safe(
        dispatch_plan=dispatch_plan,
        aegis_result=aegis_result,
        approval_record=approval_record,
        approval_id=approval_id,
        package_reason=f"Project autopilot prepared bounded package for task: {request_summary[:160]}",
    )
    if isinstance(package, dict):
        package.update(mission_packet)
        package.update(routing)
        package.update(approval_queue)
        package["executor_task_packet"] = {
            "task_id": str((task or {}).get("id") or ""),
            "task_summary": request_summary,
            "mission_id": mission_packet.get("mission_id"),
            "mission_type": mission_packet.get("mission_type"),
            "mission_scope_boundary": mission_packet.get("mission_scope_boundary"),
            "mission_allowed_actions": mission_packet.get("mission_allowed_actions"),
        }
        package["autopilot_status"] = "evaluating"
        package["autopilot_loop_state"] = "evaluating"
        package["autopilot_requires_operator_review"] = requires_initial_approval
        package["autopilot_current_focus"] = str(mission_packet.get("mission_type") or "")
        package["autopilot_enabled"] = True
        package["autopilot_stop_reason"] = ""
        package["mission_stop_condition_hit"] = False
        package["mission_stop_condition_reason"] = ""
        package["mission_escalation_required"] = False
        metadata = dict(package.get("metadata") or {})
        metadata["mission_packet"] = dict(mission_packet)
        metadata["executor_router"] = dict(routing)
        metadata["approval_queue"] = dict(approval_queue)
        package["metadata"] = metadata
    package_path = write_execution_package_safe(project_path=project_path, package=package)
    package_id = str((package or {}).get("package_id") or "")
    if not package_path or not package_id:
        return None, dispatch_plan, approval_record
    return read_execution_package(project_path=project_path, package_id=package_id), dispatch_plan, approval_record


def _advance_package_pipeline(
    *,
    project_path: str,
    package: dict[str, Any],
    execution_bridge_summary: dict[str, Any],
) -> tuple[dict[str, Any] | None, str, str, int]:
    package_id = str(package.get("package_id") or "")
    if not package_id:
        return None, "error_fallback", "missing_package_id", 0

    current = package
    operations_used = 0

    def _annotate_current(mission_status: str, autopilot_status: str, loop_state: str, stop_reason: str = "") -> None:
        nonlocal current
        if not isinstance(current, dict):
            return
        current["mission_status"] = mission_status
        current["autopilot_status"] = autopilot_status
        current["autopilot_loop_state"] = loop_state
        current["autopilot_stop_reason"] = stop_reason
        write_execution_package_safe(project_path=project_path, package=current)
    if str(current.get("decision_status") or "").strip().lower() == "pending":
        operations_used += 1
        result = record_execution_package_decision_safe(
            project_path=project_path,
            package_id=package_id,
            decision_status="approved",
            decision_actor=AUTOPILOT_ACTOR,
            decision_notes="Autopilot approved bounded package after explicit AEGIS and package review checks.",
        )
        current = result.get("package") if isinstance(result.get("package"), dict) else None
        if not current:
            return None, "error_fallback", "decision_failed", operations_used

    if str(current.get("eligibility_status") or "").strip().lower() == "pending":
        operations_used += 1
        result = record_execution_package_eligibility_safe(
            project_path=project_path,
            package_id=package_id,
            eligibility_checked_by=AUTOPILOT_ACTOR,
        )
        current = result.get("package") if isinstance(result.get("package"), dict) else None
        if not current:
            return None, "error_fallback", "eligibility_failed", operations_used

    if str(current.get("eligibility_status") or "").strip().lower() != "eligible":
        _annotate_current("paused", "blocked", "blocked", "eligibility_blocked")
        return current, "blocked", "eligibility_blocked", operations_used

    if str(current.get("release_status") or "").strip().lower() == "pending":
        operations_used += 1
        result = record_execution_package_release_safe(
            project_path=project_path,
            package_id=package_id,
            release_actor=AUTOPILOT_ACTOR,
            release_notes="Autopilot released bounded package for controlled handoff.",
        )
        current = result.get("package") if isinstance(result.get("package"), dict) else None
        if not current:
            return None, "error_fallback", "release_failed", operations_used

    if str(current.get("release_status") or "").strip().lower() != "released":
        _annotate_current("paused", "blocked", "blocked", "release_blocked")
        return current, "blocked", "release_blocked", operations_used

    selected_target = str(execution_bridge_summary.get("selected_runtime_target") or "").strip().lower()
    fallback_target = str(execution_bridge_summary.get("fallback_runtime_target") or "").strip().lower()
    executor_target_id = selected_target if selected_target and selected_target != "windows_review_package" else ""
    if not executor_target_id:
        executor_target_id = fallback_target if fallback_target and fallback_target != "windows_review_package" else "local"

    if str(current.get("handoff_status") or "").strip().lower() == "pending":
        operations_used += 1
        result = record_execution_package_handoff_safe(
            project_path=project_path,
            package_id=package_id,
            handoff_actor=AUTOPILOT_ACTOR,
            executor_target_id=executor_target_id,
            handoff_notes="Autopilot requested controlled executor handoff for bounded package.",
        )
        current = result.get("package") if isinstance(result.get("package"), dict) else None
        if not current:
            return None, "error_fallback", "handoff_failed", operations_used

    if str(current.get("handoff_status") or "").strip().lower() != "authorized":
        handoff_aegis = current.get("handoff_aegis_result") if isinstance(current.get("handoff_aegis_result"), dict) else {}
        decision = str(handoff_aegis.get("aegis_decision") or "").strip().lower()
        if decision == "approval_required":
            _annotate_current("awaiting_initial_approval", "awaiting_approval", "awaiting_approval", "handoff_approval_required")
            return current, "escalated", "handoff_approval_required", operations_used
        _annotate_current("paused", "blocked", "blocked", "handoff_blocked")
        return current, "blocked", "handoff_blocked", operations_used

    if str(current.get("execution_status") or "").strip().lower() == "pending":
        operations_used += 1
        result = record_execution_package_execution_safe(
            project_path=project_path,
            package_id=package_id,
            execution_actor=AUTOPILOT_ACTOR,
        )
        current = result.get("package") if isinstance(result.get("package"), dict) else None
        if not current:
            return None, "error_fallback", "execution_failed", operations_used

    if str(current.get("execution_status") or "").strip().lower() == "blocked":
        _annotate_current("paused", "blocked", "blocked", "execution_blocked")
        return current, "escalated", "execution_blocked", operations_used

    if str(current.get("evaluation_status") or "").strip().lower() != "completed":
        operations_used += 1
        result = record_execution_package_evaluation_safe(
            project_path=project_path,
            package_id=package_id,
            evaluation_actor=ABACUS_ACTOR,
        )
        current = result.get("package") if isinstance(result.get("package"), dict) else None
        if not current:
            return None, "error_fallback", "evaluation_failed", operations_used

    if str(current.get("evaluation_status") or "").strip().lower() != "completed":
        _annotate_current("paused", "escalated", "paused", "evaluation_blocked")
        return current, "escalated", "evaluation_blocked", operations_used

    if str(current.get("local_analysis_status") or "").strip().lower() != "completed":
        operations_used += 1
        result = record_execution_package_local_analysis_safe(
            project_path=project_path,
            package_id=package_id,
            analysis_actor=NEMOCLAW_ACTOR,
        )
        current = result.get("package") if isinstance(result.get("package"), dict) else None
        if not current:
            return None, "error_fallback", "local_analysis_failed", operations_used

    if str(current.get("local_analysis_status") or "").strip().lower() != "completed":
        _annotate_current("paused", "escalated", "paused", "local_analysis_blocked")
        return current, "escalated", "local_analysis_blocked", operations_used

    needs_escalation, escalation_reason = _escalation_needed(current)
    if needs_escalation:
        _annotate_current("paused", "escalated", "paused", escalation_reason)
        return current, "escalated", escalation_reason, operations_used
    _annotate_current("executing", "executing", "executing")
    return current, "continue", "", operations_used


def get_project_autopilot_status(*, project_path: str, project_name: str) -> dict[str, Any]:
    state = load_project_state(project_path)
    if not isinstance(state, dict) or state.get("load_error"):
        return {
            "status": "error",
            "reason": str((state or {}).get("load_error") or "Failed to load project state."),
            "session": _normalize_session(project_name, {}),
        }
    session = _normalize_session(project_name, state)
    _ensure_stop_rail_config(session, state.get("autonomy_mode") or session.get("autopilot_mode"))
    _current_counts(session)
    _evaluate_stop_rails(session)
    active_package = None
    package_id = str(session.get("autopilot_last_package_id") or state.get("execution_package_id") or "")
    if package_id:
        active_package = read_execution_package(project_path=project_path, package_id=package_id)
    current_task = _select_next_task(state)
    session["autopilot_progress_summary"] = _build_progress_summary(
        state=state,
        session=session,
        current_task=current_task,
        package=active_package or {},
        next_suggested_step=str(session.get("autopilot_next_action") or ""),
    )
    return {"status": "ok", "reason": "Autopilot status loaded.", "session": session}


def pause_project_autopilot(*, project_path: str, project_name: str) -> dict[str, Any]:
    status = get_project_autopilot_status(project_path=project_path, project_name=project_name)
    if status.get("status") != "ok":
        return status
    session = status["session"]
    if session["autopilot_status"] in ("completed", "escalated", "blocked", "error_fallback"):
        return {
            "status": "error",
            "reason": f"Cannot pause autopilot from status={session['autopilot_status']}.",
            "session": session,
        }
    session["autopilot_status"] = "paused"
    session["autopilot_enabled"] = True
    session["autopilot_loop_state"] = "paused"
    session["autopilot_next_action"] = "operator_review"
    session["autopilot_stop_reason"] = "operator_requested_pause"
    session["autopilot_escalation_reason"] = "operator_requested_pause"
    session["autopilot_requires_operator_review"] = True
    session["autopilot_last_run_at"] = _now_iso()
    session["autopilot_next_run_at"] = ""
    session["autopilot_updated_at"] = _now_iso()
    _ensure_stop_rail_config(session, load_project_state(project_path).get("autonomy_mode") or session.get("autopilot_mode"))
    _current_counts(session)
    session["autonomy_stop_rail_result"] = _build_stop_rail_result(
        session=session,
        rail_type="operations",
        current_value=int((session.get("autonomy_current_counts") or {}).get("operations") or 0),
        limit_value=int((session.get("autonomy_stop_rail_config") or {}).get("max_operations") or 0),
        routing_outcome="pause",
        stop_reason="operator_requested_pause",
    )
    session["autonomy_stop_rail_status"] = "paused"
    session["autonomy_governance_trace"] = dict((session.get("autonomy_stop_rail_result") or {}).get("governance_trace") or {})
    session["autopilot_progress_summary"] = _build_progress_summary(
        state=load_project_state(project_path),
        session=session,
        next_suggested_step="operator_review",
        operator_review_required=True,
    )
    _persist_session(
        project_path,
        session,
        extra_fields=_routing_state_fields(
            project_name=project_name,
            state=load_project_state(project_path),
            session=session,
        ),
    )
    return {"status": "ok", "reason": "Autopilot paused.", "session": session}


def stop_project_autopilot(*, project_path: str, project_name: str) -> dict[str, Any]:
    status = get_project_autopilot_status(project_path=project_path, project_name=project_name)
    if status.get("status") != "ok":
        return status
    session = status["session"]
    session["autopilot_status"] = "completed"
    session["autopilot_enabled"] = False
    session["autopilot_loop_state"] = "off"
    session["autopilot_next_action"] = "stop"
    session["autopilot_stop_reason"] = "operator_requested_stop"
    session["autopilot_escalation_reason"] = ""
    session["autopilot_requires_operator_review"] = False
    session["autopilot_last_run_at"] = _now_iso()
    session["autopilot_next_run_at"] = ""
    session["autopilot_updated_at"] = _now_iso()
    _ensure_stop_rail_config(session, load_project_state(project_path).get("autonomy_mode") or session.get("autopilot_mode"))
    _current_counts(session)
    session["autonomy_stop_rail_result"] = _build_stop_rail_result(
        session=session,
        rail_type="operations",
        current_value=int((session.get("autonomy_current_counts") or {}).get("operations") or 0),
        limit_value=int((session.get("autonomy_stop_rail_config") or {}).get("max_operations") or 0),
        routing_outcome="stop",
        stop_reason="operator_requested_stop",
    )
    session["autonomy_stop_rail_status"] = "stopped"
    session["autonomy_governance_trace"] = dict((session.get("autonomy_stop_rail_result") or {}).get("governance_trace") or {})
    session["autopilot_progress_summary"] = _build_progress_summary(
        state=load_project_state(project_path),
        session=session,
        next_suggested_step="stop",
        operator_review_required=False,
    )
    _persist_session(
        project_path,
        session,
        extra_fields=_routing_state_fields(
            project_name=project_name,
            state=load_project_state(project_path),
            session=session,
        ),
    )
    return {"status": "ok", "reason": "Autopilot stopped.", "session": session}


def start_project_autopilot(
    *,
    project_path: str,
    project_name: str,
    iteration_limit: int | None = None,
    autopilot_mode: str | None = None,
) -> dict[str, Any]:
    enforcement = _global_execution_gate(
        project_path=project_path,
        project_name=project_name,
        runtime_target_id="local",
        allocation_status="selected",
        operation_type="autonomy_loop",
    )
    if enforcement.get("routing_enforcement_status") == "denied":
        deny_reason = "; ".join(
            str(item.get("reason") or item.get("code") or "routing_denied")
            for item in list(enforcement.get("denies") or [])[:5]
        ) or "Global control routing enforcement denied autopilot start."
        return {
            "status": "error",
            "reason": deny_reason,
            "session": _normalize_session(project_name, {}),
        }
    state = load_project_state(project_path)
    if not isinstance(state, dict) or state.get("load_error"):
        return {
            "status": "error",
            "reason": str((state or {}).get("load_error") or "Failed to load project state."),
            "session": _normalize_session(project_name, {}),
        }
    autonomy_mode = normalize_autonomy_mode(
        autopilot_mode if autopilot_mode in (DEFAULT_AUTONOMY_MODE, "assisted_autopilot", "low_risk_autonomous_development") else state.get("autonomy_mode")
    )
    stop_rail_config = get_mode_stop_rail_config(autonomy_mode)
    session = {
        "autopilot_enabled": True,
        "autopilot_status": "ready",
        "autopilot_loop_state": "idle",
        "autopilot_last_run_at": "",
        "autopilot_next_run_at": _now_iso(),
        "autopilot_current_focus": "",
        "autopilot_requires_operator_review": False,
        "autopilot_session_id": uuid.uuid4().hex[:16],
        "autopilot_project_key": project_name,
        "autopilot_mode": autonomy_mode,
        "autopilot_iteration_count": 0,
        "autopilot_iteration_limit": _clamp_iteration_limit(iteration_limit or stop_rail_config.get("max_loops") or AUTOPILOT_DEFAULT_ITERATION_LIMIT),
        "autopilot_started_at": _now_iso(),
        "autopilot_updated_at": _now_iso(),
        "autopilot_last_package_id": "",
        "autopilot_last_result": {},
        "autopilot_next_action": "run",
        "autopilot_stop_reason": "",
        "autopilot_escalation_reason": "",
        "autopilot_progress_summary": {},
        "autopilot_retry_count": 0,
        "autopilot_retry_limit": _clamp_retry_limit(stop_rail_config.get("max_retries")),
        "autopilot_operation_count": 0,
        "autopilot_operation_limit": _clamp_operation_limit(stop_rail_config.get("max_operations")),
        "autopilot_runtime_started_at": _now_iso(),
        "autopilot_runtime_limit_seconds": _clamp_runtime_limit(stop_rail_config.get("max_runtime_seconds")),
        "autonomy_stop_rail_config": {},
        "autonomy_current_counts": {},
        "autonomy_stop_rail_status": "ok",
        "autonomy_stop_rail_result": {},
        "autonomy_governance_trace": {},
        "mission_packet": normalize_mission_packet({}),
        "mission_status": "proposed",
        "executor_route": "",
        "executor_route_reason": "",
        "executor_route_confidence": 0.0,
        "executor_route_status": "",
        "executor_task_type": "",
        "executor_fallback_route": "",
        "mission_stop_condition_hit": False,
        "mission_stop_condition_reason": "",
        "mission_escalation_required": False,
    }
    _ensure_stop_rail_config(session, autonomy_mode)
    _current_counts(session)
    _evaluate_stop_rails(session)
    session["autopilot_progress_summary"] = _build_progress_summary(
        state=state,
        session=session,
        current_task=_select_next_task(state),
        next_suggested_step="run",
        operator_review_required=False,
    )
    _persist_session(
        project_path,
        session,
        extra_fields=_routing_state_fields(
            project_name=project_name,
            state={**state, "autonomy_mode": autonomy_mode},
            session=session,
        ),
    )
    return _run_project_autopilot_loop(project_path=project_path, project_name=project_name, session=session)


def resume_project_autopilot(*, project_path: str, project_name: str) -> dict[str, Any]:
    enforcement = _global_execution_gate(
        project_path=project_path,
        project_name=project_name,
        runtime_target_id="local",
        allocation_status="selected",
        operation_type="autonomy_loop",
    )
    if enforcement.get("routing_enforcement_status") == "denied":
        deny_reason = "; ".join(
            str(item.get("reason") or item.get("code") or "routing_denied")
            for item in list(enforcement.get("denies") or [])[:5]
        ) or "Global control routing enforcement denied autopilot resume."
        return {
            "status": "error",
            "reason": deny_reason,
            "session": _normalize_session(project_name, {}),
        }
    state = load_project_state(project_path)
    if not isinstance(state, dict) or state.get("load_error"):
        return {
            "status": "error",
            "reason": str((state or {}).get("load_error") or "Failed to load project state."),
            "session": _normalize_session(project_name, {}),
        }
    session = _normalize_session(project_name, state)
    if session["autopilot_status"] not in ("paused", "ready"):
        return {
            "status": "error",
            "reason": f"Resume not allowed from status={session['autopilot_status']}.",
            "session": session,
        }
    session["autopilot_status"] = "ready"
    session["autopilot_enabled"] = True
    session["autopilot_loop_state"] = "idle"
    session["autopilot_next_action"] = "resume"
    session["autopilot_stop_reason"] = ""
    session["autopilot_escalation_reason"] = ""
    session["autopilot_requires_operator_review"] = False
    session["autopilot_next_run_at"] = _now_iso()
    session["autopilot_updated_at"] = _now_iso()
    _ensure_stop_rail_config(session, state.get("autonomy_mode") or session.get("autopilot_mode"))
    _current_counts(session)
    stop_rail_result = _evaluate_stop_rails(session)
    if stop_rail_result.get("status") in ("paused", "escalated", "stopped"):
        return _apply_stop_rail_outcome(
            session=session,
            state=state,
            project_path=project_path,
            project_name=project_name,
            stop_rail_result=stop_rail_result,
            current_task=_select_next_task(state),
            package=_load_active_package(project_path=project_path, session=session, state=state) or {},
        )
    _persist_session(
        project_path,
        session,
        extra_fields=_routing_state_fields(
            project_name=project_name,
            state=state,
            session=session,
        ),
    )
    return _run_project_autopilot_loop(project_path=project_path, project_name=project_name, session=session)


def _run_project_autopilot_loop(
    *,
    project_path: str,
    project_name: str,
    session: dict[str, Any],
) -> dict[str, Any]:
    worker_id = f"project_autopilot:{str(session.get('autopilot_session_id') or uuid.uuid4().hex[:8])}"
    while True:
        loop_enforcement = _global_execution_gate(
            project_path=project_path,
            project_name=project_name,
            runtime_target_id="local",
            allocation_status="selected",
            operation_type="autonomy_loop",
        )
        if loop_enforcement.get("routing_enforcement_status") == "denied":
            reason = "; ".join(
                str(item.get("reason") or item.get("code") or "routing_denied")
                for item in list(loop_enforcement.get("denies") or [])[:5]
            ) or "Global control routing enforcement denied autonomous loop."
            session["autopilot_status"] = "blocked"
            session["autopilot_next_action"] = "operator_review"
            session["autopilot_stop_reason"] = "global_control_denied"
            session["autopilot_escalation_reason"] = "global_control_denied"
            session["autopilot_updated_at"] = _now_iso()
            session["autopilot_last_result"] = {
                "status": "blocked",
                "reason": reason,
                "routing_enforcement": loop_enforcement,
            }
            _persist_session(
                project_path,
                session,
                extra_fields=_routing_state_fields(project_name=project_name, state={}, session=session),
            )
            return {"status": "error", "reason": reason, "session": session}
        state = load_project_state(project_path)
        if not isinstance(state, dict) or state.get("load_error"):
            session["autopilot_enabled"] = False
            session["autopilot_status"] = "error_fallback"
            session["autopilot_loop_state"] = "blocked"
            session["autopilot_next_action"] = "stop"
            session["autopilot_stop_reason"] = "project_state_load_failed"
            session["autopilot_requires_operator_review"] = True
            session["autopilot_last_run_at"] = _now_iso()
            session["autopilot_next_run_at"] = ""
            session["autopilot_updated_at"] = _now_iso()
            session["autopilot_last_result"] = {"status": "error", "reason": "project_state_load_failed"}
            _persist_session(
                project_path,
                session,
                extra_fields=_routing_state_fields(project_name=project_name, state={}, session=session),
            )
            return {"status": "error", "reason": "Failed to load project state during autopilot run.", "session": session}

        recover_expired_leases()

        _ensure_stop_rail_config(session, state.get("autonomy_mode") or session.get("autopilot_mode"))
        session["autopilot_last_run_at"] = _now_iso()
        _current_counts(session)
        precheck_stop_rail = _evaluate_stop_rails(session)
        if precheck_stop_rail.get("status") in ("paused", "escalated", "stopped"):
            return _apply_stop_rail_outcome(
                session=session,
                state=state,
                project_path=project_path,
                project_name=project_name,
                stop_rail_result=precheck_stop_rail,
                current_task=_select_next_task(state),
                package=_load_active_package(project_path=project_path, session=session, state=state) or {},
            )

        session["autopilot_status"] = "evaluating"
        session["autopilot_loop_state"] = "evaluating"
        session["autopilot_updated_at"] = _now_iso()

        task = _select_next_task(state)
        active_package = _load_active_package(project_path=project_path, session=session, state=state)
        if not active_package and not task:
            session["autopilot_enabled"] = False
            session["autopilot_status"] = "completed"
            session["autopilot_loop_state"] = "off"
            session["autopilot_next_action"] = "stop"
            session["autopilot_stop_reason"] = "no_next_bounded_task"
            session["autopilot_escalation_reason"] = ""
            session["autopilot_requires_operator_review"] = False
            session["autopilot_last_result"] = {"status": "completed", "reason": "no_next_bounded_task"}
            session["autopilot_next_run_at"] = ""
            session["autopilot_updated_at"] = _now_iso()
            session["autopilot_progress_summary"] = _build_progress_summary(
                state=state,
                session=session,
                current_task=None,
                next_suggested_step="stop",
                operator_review_required=False,
            )
            _persist_session(
                project_path,
                session,
                extra_fields=_routing_state_fields(project_name=project_name, state=state, session=session),
            )
            return {"status": "ok", "reason": "No next bounded task available.", "session": session}

        if not active_package and task:
            package, dispatch_plan, approval_record = _create_autopilot_package(
                project_path=project_path,
                project_name=project_name,
                state=state,
                task=task,
            )
            if not package:
                session["autopilot_status"] = "error_fallback"
                session["autopilot_next_action"] = "stop"
                session["autopilot_stop_reason"] = "package_creation_failed"
                session["autopilot_last_result"] = {"status": "error", "reason": "package_creation_failed"}
                session["autopilot_updated_at"] = _now_iso()
                session["autopilot_progress_summary"] = _build_progress_summary(
                    state=state,
                    session=session,
                    current_task=task,
                    next_suggested_step="stop",
                    operator_review_required=True,
                )
                _persist_session(
                    project_path,
                    session,
                    extra_fields=_routing_state_fields(project_name=project_name, state=state, session=session),
                )
                return {"status": "error", "reason": "Autopilot package creation failed.", "session": session}

            session["autopilot_last_package_id"] = str(package.get("package_id") or "")
            session["autopilot_iteration_count"] += 1
            session["autopilot_operation_count"] += 1
            session["autopilot_retry_count"] = 0
            session["mission_packet"] = normalize_mission_packet(package)
            session["mission_status"] = str(package.get("mission_status") or "proposed")
            session["executor_route"] = str(package.get("executor_route") or "")
            session["executor_route_reason"] = str(package.get("executor_route_reason") or "")
            session["executor_route_confidence"] = float(package.get("executor_route_confidence") or 0.0)
            session["executor_route_status"] = str(package.get("executor_route_status") or "")
            session["executor_task_type"] = str(package.get("executor_task_type") or "")
            session["executor_fallback_route"] = str(package.get("executor_fallback_route") or "")
            session["autopilot_current_focus"] = str(
                (session.get("mission_packet") or {}).get("mission_type") or ""
            )
            _current_counts(session)
            session["autopilot_last_result"] = {
                "status": "package_prepared",
                "task_id": str(task.get("id") or ""),
                "task_summary": _task_label(task),
                "dispatch_plan_summary": package.get("dispatch_plan_summary") or dispatch_plan.get("dispatch_plan_summary") or {},
                "approval_id": approval_record.get("approval_id"),
                "package_id": package.get("package_id"),
            }
            extra_fields = {
                "execution_package_id": package.get("package_id"),
                "execution_package_path": get_execution_package_file_path(project_path, package.get("package_id")),
            }
            requires_human = bool(package.get("requires_human_approval")) or bool(approval_record.get("requires_human"))
            aegis_decision = str(package.get("aegis_decision") or "").strip().lower()
            if requires_human or aegis_decision == "approval_required":
                session["autopilot_status"] = "escalated"
                session["autopilot_loop_state"] = "awaiting_approval"
                session["mission_status"] = "awaiting_initial_approval"
                session["autopilot_next_action"] = "operator_review"
                session["autopilot_stop_reason"] = "approval_required_unresolved"
                session["autopilot_escalation_reason"] = "approval_required_unresolved"
                session["autopilot_requires_operator_review"] = True
                session["autopilot_next_run_at"] = ""
                session["autopilot_updated_at"] = _now_iso()
                session["autopilot_progress_summary"] = _build_progress_summary(
                    state=state,
                    session=session,
                    current_task=task,
                    package=package,
                    next_suggested_step="operator_review",
                    operator_review_required=True,
                )
                _persist_session(project_path, session, extra_fields=extra_fields)
                return {"status": "ok", "reason": "Autopilot escalated for approval resolution.", "session": session}
            active_package = package
        elif active_package:
            session["autopilot_iteration_count"] += 1
            session["autopilot_retry_count"] += 1
            session["autopilot_loop_state"] = "executing"
            session["autopilot_status"] = "executing"
            _current_counts(session)
            retry_stop_rail = _evaluate_stop_rails(session, rail_types=("retries", "runtime", "operations", "budget"))
            if retry_stop_rail.get("status") in ("paused", "escalated", "stopped"):
                return _apply_stop_rail_outcome(
                    session=session,
                    state=state,
                    project_path=project_path,
                    project_name=project_name,
                    stop_rail_result=retry_stop_rail,
                    current_task=task,
                    package=active_package,
                )

        routed_state = {**state, "execution_package_id": (active_package or {}).get("package_id")}
        routing_fields = _routing_state_fields(
            project_name=project_name,
            state=routed_state,
            session=session,
            active_package=active_package or {},
        )
        routing_result = routing_fields.get("project_routing_result") if isinstance(routing_fields.get("project_routing_result"), dict) else {}
        selected_action = str(routing_result.get("selected_action") or "").strip().lower()
        if selected_action in ("pause", "escalate", "stop"):
            session["autopilot_status"] = "paused" if selected_action == "pause" else ("completed" if selected_action == "stop" else "escalated")
            session["autopilot_next_action"] = "stop" if selected_action == "stop" else "operator_review"
            session["autopilot_stop_reason"] = str(routing_result.get("routing_reason") or f"routing_{selected_action}")
            session["autopilot_escalation_reason"] = (
                ""
                if selected_action == "stop"
                else str(routing_result.get("routing_reason") or f"routing_{selected_action}")
            )
            session["autopilot_updated_at"] = _now_iso()
            session["autopilot_last_result"] = {
                "status": "routing_controlled",
                "reason": routing_result.get("routing_reason"),
                "selected_action": selected_action,
                "package_id": (active_package or {}).get("package_id") if isinstance(active_package, dict) else "",
            }
            session["autopilot_progress_summary"] = _build_progress_summary(
                state=state,
                session=session,
                current_task=task,
                package=active_package or {},
                next_suggested_step=session["autopilot_next_action"],
                operator_review_required=selected_action != "stop",
            )
            _persist_session(
                project_path,
                session,
                extra_fields={
                    **routing_fields,
                    "execution_package_id": (active_package or {}).get("package_id"),
                    "execution_package_path": get_execution_package_file_path(project_path, (active_package or {}).get("package_id")),
                },
            )
            return {
                "status": "ok",
                "reason": session["autopilot_stop_reason"],
                "session": session,
            }

        _persist_session(
            project_path,
            session,
            extra_fields={
                **routing_fields,
                "execution_package_id": (active_package or {}).get("package_id"),
                "execution_package_path": get_execution_package_file_path(project_path, (active_package or {}).get("package_id")),
            },
        )

        queue_item_id = ""
        if active_package and str(active_package.get("package_id") or "").strip():
            mission_id = _build_mission_id(project_name=project_name, task=task, package=active_package)
            task_type = str((task or {}).get("type") or "autopilot_task")
            priority_value = int((task or {}).get("priority") or 100)
            enqueue_result = enqueue_mission_work_item(
                mission_id=mission_id,
                project_id=project_name,
                package_id=str(active_package.get("package_id") or ""),
                task_type=task_type,
                priority=priority_value,
                idempotency_key=f"{project_name}:{mission_id}:{active_package.get('package_id')}",
            )
            queued = enqueue_result.get("queue_item") if isinstance(enqueue_result.get("queue_item"), dict) else {}
            queue_item_id = str(queued.get("queue_item_id") or "")
            queue_pressure = mission_backpressure_status()
            claim_result = claim_next_work_item(
                worker_id=worker_id,
                kill_switch_active=bool((active_package.get("budget_control") or {}).get("kill_switch_active")),
                project_id_filter=project_name,
            )
            if claim_result.get("status") != "ok":
                session["autopilot_status"] = "paused"
                session["autopilot_next_action"] = "operator_review"
                session["autopilot_stop_reason"] = str(claim_result.get("reason") or "mission_queue_claim_blocked")
                session["autopilot_escalation_reason"] = session["autopilot_stop_reason"]
                session["autopilot_updated_at"] = _now_iso()
                session["autopilot_last_result"] = {
                    "status": "mission_queue_wait",
                    "reason": session["autopilot_stop_reason"],
                    "queue_item_id": queue_item_id,
                    "backpressure": queue_pressure,
                }
                session["autopilot_progress_summary"] = _build_progress_summary(
                    state=state,
                    session=session,
                    current_task=task,
                    package=active_package or {},
                    next_suggested_step="operator_review",
                    operator_review_required=True,
                )
                _persist_session(
                    project_path,
                    session,
                    extra_fields={
                        **routing_fields,
                        "execution_package_id": (active_package or {}).get("package_id"),
                        "execution_package_path": get_execution_package_file_path(project_path, (active_package or {}).get("package_id")),
                    },
                )
                return {"status": "ok", "reason": session["autopilot_stop_reason"], "session": session}
            claimed_item = claim_result.get("queue_item") if isinstance(claim_result.get("queue_item"), dict) else {}
            queue_item_id = str(claimed_item.get("queue_item_id") or queue_item_id)
            if queue_item_id:
                renew_work_item_lease(queue_item_id=queue_item_id, worker_id=worker_id)

        advanced_package, outcome, outcome_reason, operations_used = _advance_package_pipeline(
            project_path=project_path,
            package=active_package or {},
            execution_bridge_summary=state.get("execution_bridge_summary") if isinstance(state.get("execution_bridge_summary"), dict) else {},
        )
        if queue_item_id:
            current_package_for_queue = advanced_package or active_package or {}
            if outcome == "continue":
                receipt_ref = str(((current_package_for_queue.get("execution_receipt") or {}).get("log_ref") or ""))
                verification_ref = str(((current_package_for_queue.get("integrity_verification") or {}).get("integrity_status") or ""))
                complete_work_item_success(
                    queue_item_id=queue_item_id,
                    worker_id=worker_id,
                    execution_receipt_ref=receipt_ref,
                    verification_ref=verification_ref,
                )
            else:
                complete_work_item_failure(
                    queue_item_id=queue_item_id,
                    worker_id=worker_id,
                    error_reason=outcome_reason or outcome or "pipeline_error",
                    retryable=outcome not in ("blocked", "escalated"),
                    operator_escalation_ref=outcome_reason if outcome in ("blocked", "escalated") else "",
                )
        session["autopilot_operation_count"] += max(0, int(operations_used or 0))
        _current_counts(session)
        post_operation_stop_rail = _evaluate_stop_rails(session, rail_types=("runtime", "operations", "budget"))
        current_package = advanced_package or active_package or {}
        mission_stop = evaluate_mission_stop_conditions(
            {
                "scope_expansion_required": bool((current_package.get("metadata") or {}).get("scope_expansion_required")),
                "governance_hard_block": str(current_package.get("execution_status") or "").strip().lower() == "blocked",
                "credentials_required_unexpectedly": bool((current_package.get("metadata") or {}).get("credentials_required_unexpectedly")),
                "executor_critical_failure": str(current_package.get("execution_status") or "").strip().lower() in ("failed", "rolled_back"),
                "risky_external_action_out_of_scope": bool(
                    (current_package.get("metadata") or {}).get("risky_external_action_out_of_scope")
                ),
                "repo_safety_cannot_be_maintained": bool((current_package.get("metadata") or {}).get("repo_safety_cannot_be_maintained")),
            }
        )
        session["mission_stop_condition_hit"] = bool(mission_stop.get("mission_stop_condition_hit"))
        session["mission_stop_condition_reason"] = str(mission_stop.get("mission_stop_condition_reason") or "")
        session["mission_escalation_required"] = bool(mission_stop.get("mission_escalation_required"))
        if isinstance(current_package, dict) and str(current_package.get("package_id") or "").strip():
            current_package["mission_stop_condition_hit"] = session["mission_stop_condition_hit"]
            current_package["mission_stop_condition_reason"] = session["mission_stop_condition_reason"]
            current_package["mission_escalation_required"] = session["mission_escalation_required"]
            current_package["autopilot_status"] = session.get("autopilot_status") or "evaluating"
            current_package["autopilot_loop_state"] = session.get("autopilot_loop_state") or "evaluating"
            current_package["mission_status"] = session.get("mission_status") or current_package.get("mission_status") or "executing"
            write_execution_package_safe(project_path=project_path, package=current_package)
        if session["mission_stop_condition_hit"]:
            outcome = "escalated"
            outcome_reason = session["mission_stop_condition_reason"] or "mission_stop_condition_hit"
        next_action = "continue"
        status_value = "running"
        stop_reason = ""
        escalation_reason = ""
        operator_review_required = False
        if post_operation_stop_rail.get("status") in ("paused", "escalated", "stopped"):
            return _apply_stop_rail_outcome(
                session=session,
                state=state,
                project_path=project_path,
                project_name=project_name,
                stop_rail_result=post_operation_stop_rail,
                current_task=task,
                package=current_package,
            )
        if outcome == "continue":
            session["autopilot_status"] = "executing"
            session["autopilot_loop_state"] = "executing"
            next_action = "continue"
            session["autopilot_retry_count"] = 0
        elif outcome == "blocked":
            next_action = "operator_review"
            status_value = "blocked"
            session["autopilot_loop_state"] = "blocked"
            stop_reason = outcome_reason
            escalation_reason = outcome_reason
            operator_review_required = True
        elif outcome == "escalated":
            next_action = "operator_review"
            status_value = "escalated"
            session["autopilot_loop_state"] = "paused"
            stop_reason = outcome_reason
            escalation_reason = outcome_reason
            operator_review_required = True
        else:
            next_action = "stop"
            status_value = "error_fallback"
            session["autopilot_loop_state"] = "blocked"
            stop_reason = outcome_reason or "pipeline_error"
            escalation_reason = stop_reason
            operator_review_required = True

        if outcome == "continue":
            local_analysis_summary = current_package.get("local_analysis_summary") if isinstance(current_package.get("local_analysis_summary"), dict) else {}
            if str(local_analysis_summary.get("suggested_next_action") or "").strip().lower() == "no_action_required":
                task_id = str(task.get("id") or "") if task else ""
                task_queue, task_queue_snapshot = _mark_task_completed(state, task_id)
                next_task = _select_next_task({"task_queue": task_queue, "task_queue_snapshot": task_queue_snapshot})
                if not next_task:
                    status_value = "completed"
                    next_action = "stop"
                    stop_reason = "project_objective_completed"
                    session["autopilot_enabled"] = False
                    session["autopilot_loop_state"] = "off"
                elif int(session.get("autopilot_iteration_count") or 0) >= int(session.get("autopilot_iteration_limit") or 1):
                    status_value = "completed"
                    next_action = "stop"
                    stop_reason = "iteration_limit_reached"
                session["autopilot_progress_summary"] = _build_progress_summary(
                    state=state,
                    session={**session, "autopilot_status": status_value, "autopilot_next_action": next_action},
                    current_task=next_task,
                    package=current_package,
                    next_suggested_step=next_action if next_task else "stop",
                    operator_review_required=False,
                )
                session["autopilot_status"] = status_value
                session["mission_status"] = "completed" if status_value == "completed" else "approved_for_execution"
                session["autopilot_next_action"] = next_action if next_task else "stop"
                session["autopilot_stop_reason"] = stop_reason
                session["autopilot_escalation_reason"] = ""
                session["autopilot_requires_operator_review"] = False
                session["autopilot_next_run_at"] = "" if status_value == "completed" else _now_iso()
                session["autopilot_updated_at"] = _now_iso()
                _current_counts(session)
                _evaluate_stop_rails(session)
                _persist_session(
                    project_path,
                    session,
                    extra_fields={
                        **_routing_state_fields(
                            project_name=project_name,
                            state={**state, "task_queue": task_queue, "task_queue_snapshot": task_queue_snapshot},
                            session=session,
                            active_package=current_package,
                        ),
                        "task_queue": task_queue,
                        "task_queue_snapshot": task_queue_snapshot,
                        "execution_package_id": current_package.get("package_id"),
                        "execution_package_path": get_execution_package_file_path(project_path, current_package.get("package_id")),
                    },
                )
                if status_value == "completed":
                    return {"status": "ok", "reason": "Autopilot completed the current project objective slice.", "session": session}
                continue
            status_value = "escalated"
            next_action = "operator_review"
            stop_reason = "no_valid_next_task_confidence"
            escalation_reason = "no_valid_next_task_confidence"
            operator_review_required = True

        session["autopilot_status"] = status_value
        if status_value == "completed":
            session["autopilot_enabled"] = False
            session["autopilot_loop_state"] = "off"
            session["mission_status"] = "completed"
        elif status_value in ("escalated", "blocked"):
            session["mission_status"] = "paused"
        else:
            session["mission_status"] = "executing"
        session["autopilot_next_action"] = next_action
        session["autopilot_stop_reason"] = stop_reason
        session["autopilot_escalation_reason"] = escalation_reason
        session["autopilot_requires_operator_review"] = operator_review_required
        session["autopilot_next_run_at"] = "" if status_value in ("completed", "blocked", "escalated", "error_fallback") else _now_iso()
        session["autopilot_updated_at"] = _now_iso()
        session["autopilot_last_result"] = {
            "status": outcome,
            "reason": outcome_reason,
            "package_id": current_package.get("package_id") if isinstance(current_package, dict) else "",
            "execution_status": current_package.get("execution_status") if isinstance(current_package, dict) else "",
            "evaluation_status": current_package.get("evaluation_status") if isinstance(current_package, dict) else "",
            "local_analysis_status": current_package.get("local_analysis_status") if isinstance(current_package, dict) else "",
        }
        if current_package and str(current_package.get("package_id") or "").strip():
            session["autopilot_last_package_id"] = str(current_package.get("package_id") or "")
        _current_counts(session)
        _evaluate_stop_rails(session)
        session["autopilot_progress_summary"] = _build_progress_summary(
            state=state,
            session=session,
            current_task=task,
            package=current_package,
            next_suggested_step=next_action,
            operator_review_required=operator_review_required,
        )
        _persist_session(
            project_path,
            session,
            extra_fields={
                **_routing_state_fields(
                    project_name=project_name,
                    state=state,
                    session=session,
                    active_package=current_package,
                ),
                "execution_package_id": current_package.get("package_id"),
                "execution_package_path": get_execution_package_file_path(project_path, current_package.get("package_id")),
            },
        )
        if status_value != "running":
            return {
                "status": "ok" if status_value in ("completed", "escalated", "blocked") else "error",
                "reason": stop_reason or escalation_reason or "autopilot_stopped",
                "session": session,
            }
