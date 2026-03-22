from __future__ import annotations

import uuid
from datetime import datetime
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
    normalize_autonomy_mode,
)
from NEXUS.project_routing import build_project_routing_decision, select_next_task
from NEXUS.project_state import load_project_state, update_project_state_fields


AUTOPILOT_STATUSES = {
    "idle",
    "ready",
    "running",
    "paused",
    "escalated",
    "completed",
    "blocked",
    "error_fallback",
}
AUTOPILOT_DEFAULT_MODE = "supervised_bounded"
AUTOPILOT_DEFAULT_ITERATION_LIMIT = 1
AUTOPILOT_MAX_ITERATION_LIMIT = 25
AUTOPILOT_ACTOR = "project_autopilot"
ABACUS_ACTOR = "abacus"
NEMOCLAW_ACTOR = "nemoclaw"


def _now_iso() -> str:
    return datetime.now().isoformat()


def _clamp_iteration_limit(value: Any) -> int:
    try:
        limit = int(value)
    except Exception:
        limit = AUTOPILOT_DEFAULT_ITERATION_LIMIT
    return max(1, min(limit, AUTOPILOT_MAX_ITERATION_LIMIT))


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
    session = {
        "autopilot_status": _normalize_status(state.get("autopilot_status")),
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
    }
    if not session["autopilot_started_at"] and session["autopilot_session_id"]:
        session["autopilot_started_at"] = str(state.get("saved_at") or "")
    if not session["autopilot_updated_at"]:
        session["autopilot_updated_at"] = str(state.get("saved_at") or "")
    return session


def _session_payload(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "autopilot_status": session.get("autopilot_status"),
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
    }


def _persist_session(project_path: str, session: dict[str, Any], *, extra_fields: dict[str, Any] | None = None) -> None:
    payload = _session_payload(session)
    if extra_fields:
        payload.update(extra_fields)
    update_project_state_fields(project_path, **payload)


def _autonomy_state_fields(mode: Any, reason: str | None = None) -> dict[str, Any]:
    return build_autonomy_mode_state(mode=normalize_autonomy_mode(mode), reason=reason)


def _routing_state_fields(
    *,
    project_name: str,
    state: dict[str, Any],
    session: dict[str, Any],
    active_package: dict[str, Any] | None = None,
) -> dict[str, Any]:
    routing = build_project_routing_decision(
        project_key=project_name,
        state=state,
        active_package=active_package,
        autonomy_mode=state.get("autonomy_mode"),
    )
    mode_state = routing.get("mode_state") if isinstance(routing.get("mode_state"), dict) else _autonomy_state_fields(state.get("autonomy_mode"))
    return {
        "autonomy_mode": mode_state.get("autonomy_mode"),
        "autonomy_mode_status": mode_state.get("autonomy_mode_status"),
        "autonomy_mode_reason": mode_state.get("autonomy_mode_reason"),
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

    package = build_execution_package_safe(
        dispatch_plan=dispatch_plan,
        aegis_result=aegis_result,
        approval_record=approval_record,
        approval_id=approval_id,
        package_reason=f"Project autopilot prepared bounded package for task: {request_summary[:160]}",
    )
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
) -> tuple[dict[str, Any] | None, str, str]:
    package_id = str(package.get("package_id") or "")
    if not package_id:
        return None, "error_fallback", "missing_package_id"

    current = package
    if str(current.get("decision_status") or "").strip().lower() == "pending":
        result = record_execution_package_decision_safe(
            project_path=project_path,
            package_id=package_id,
            decision_status="approved",
            decision_actor=AUTOPILOT_ACTOR,
            decision_notes="Autopilot approved bounded package after explicit AEGIS and package review checks.",
        )
        current = result.get("package") if isinstance(result.get("package"), dict) else None
        if not current:
            return None, "error_fallback", "decision_failed"

    if str(current.get("eligibility_status") or "").strip().lower() == "pending":
        result = record_execution_package_eligibility_safe(
            project_path=project_path,
            package_id=package_id,
            eligibility_checked_by=AUTOPILOT_ACTOR,
        )
        current = result.get("package") if isinstance(result.get("package"), dict) else None
        if not current:
            return None, "error_fallback", "eligibility_failed"

    if str(current.get("eligibility_status") or "").strip().lower() != "eligible":
        return current, "blocked", "eligibility_blocked"

    if str(current.get("release_status") or "").strip().lower() == "pending":
        result = record_execution_package_release_safe(
            project_path=project_path,
            package_id=package_id,
            release_actor=AUTOPILOT_ACTOR,
            release_notes="Autopilot released bounded package for controlled handoff.",
        )
        current = result.get("package") if isinstance(result.get("package"), dict) else None
        if not current:
            return None, "error_fallback", "release_failed"

    if str(current.get("release_status") or "").strip().lower() != "released":
        return current, "blocked", "release_blocked"

    selected_target = str(execution_bridge_summary.get("selected_runtime_target") or "").strip().lower()
    fallback_target = str(execution_bridge_summary.get("fallback_runtime_target") or "").strip().lower()
    executor_target_id = selected_target if selected_target and selected_target != "windows_review_package" else ""
    if not executor_target_id:
        executor_target_id = fallback_target if fallback_target and fallback_target != "windows_review_package" else "local"

    if str(current.get("handoff_status") or "").strip().lower() == "pending":
        result = record_execution_package_handoff_safe(
            project_path=project_path,
            package_id=package_id,
            handoff_actor=AUTOPILOT_ACTOR,
            executor_target_id=executor_target_id,
            handoff_notes="Autopilot requested controlled executor handoff for bounded package.",
        )
        current = result.get("package") if isinstance(result.get("package"), dict) else None
        if not current:
            return None, "error_fallback", "handoff_failed"

    if str(current.get("handoff_status") or "").strip().lower() != "authorized":
        handoff_aegis = current.get("handoff_aegis_result") if isinstance(current.get("handoff_aegis_result"), dict) else {}
        decision = str(handoff_aegis.get("aegis_decision") or "").strip().lower()
        if decision == "approval_required":
            return current, "escalated", "handoff_approval_required"
        return current, "blocked", "handoff_blocked"

    if str(current.get("execution_status") or "").strip().lower() == "pending":
        result = record_execution_package_execution_safe(
            project_path=project_path,
            package_id=package_id,
            execution_actor=AUTOPILOT_ACTOR,
        )
        current = result.get("package") if isinstance(result.get("package"), dict) else None
        if not current:
            return None, "error_fallback", "execution_failed"

    if str(current.get("execution_status") or "").strip().lower() == "blocked":
        return current, "escalated", "execution_blocked"

    if str(current.get("evaluation_status") or "").strip().lower() != "completed":
        result = record_execution_package_evaluation_safe(
            project_path=project_path,
            package_id=package_id,
            evaluation_actor=ABACUS_ACTOR,
        )
        current = result.get("package") if isinstance(result.get("package"), dict) else None
        if not current:
            return None, "error_fallback", "evaluation_failed"

    if str(current.get("evaluation_status") or "").strip().lower() != "completed":
        return current, "escalated", "evaluation_blocked"

    if str(current.get("local_analysis_status") or "").strip().lower() != "completed":
        result = record_execution_package_local_analysis_safe(
            project_path=project_path,
            package_id=package_id,
            analysis_actor=NEMOCLAW_ACTOR,
        )
        current = result.get("package") if isinstance(result.get("package"), dict) else None
        if not current:
            return None, "error_fallback", "local_analysis_failed"

    if str(current.get("local_analysis_status") or "").strip().lower() != "completed":
        return current, "escalated", "local_analysis_blocked"

    needs_escalation, escalation_reason = _escalation_needed(current)
    if needs_escalation:
        return current, "escalated", escalation_reason
    return current, "continue", ""


def get_project_autopilot_status(*, project_path: str, project_name: str) -> dict[str, Any]:
    state = load_project_state(project_path)
    if not isinstance(state, dict) or state.get("load_error"):
        return {
            "status": "error",
            "reason": str((state or {}).get("load_error") or "Failed to load project state."),
            "session": _normalize_session(project_name, {}),
        }
    session = _normalize_session(project_name, state)
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
    session["autopilot_next_action"] = "operator_review"
    session["autopilot_stop_reason"] = ""
    session["autopilot_escalation_reason"] = ""
    session["autopilot_updated_at"] = _now_iso()
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
    session["autopilot_next_action"] = "stop"
    session["autopilot_stop_reason"] = "operator_requested_stop"
    session["autopilot_escalation_reason"] = ""
    session["autopilot_updated_at"] = _now_iso()
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
    state = load_project_state(project_path)
    if not isinstance(state, dict) or state.get("load_error"):
        return {
            "status": "error",
            "reason": str((state or {}).get("load_error") or "Failed to load project state."),
            "session": _normalize_session(project_name, {}),
        }
    session = {
        "autopilot_status": "ready",
        "autopilot_session_id": uuid.uuid4().hex[:16],
        "autopilot_project_key": project_name,
        "autopilot_mode": str(autopilot_mode or AUTOPILOT_DEFAULT_MODE),
        "autopilot_iteration_count": 0,
        "autopilot_iteration_limit": _clamp_iteration_limit(iteration_limit or AUTOPILOT_DEFAULT_ITERATION_LIMIT),
        "autopilot_started_at": _now_iso(),
        "autopilot_updated_at": _now_iso(),
        "autopilot_last_package_id": "",
        "autopilot_last_result": {},
        "autopilot_next_action": "run",
        "autopilot_stop_reason": "",
        "autopilot_escalation_reason": "",
        "autopilot_progress_summary": {},
    }
    autonomy_mode = normalize_autonomy_mode(autopilot_mode if autopilot_mode in (DEFAULT_AUTONOMY_MODE, "assisted_autopilot", "low_risk_autonomous_development") else state.get("autonomy_mode"))
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
    session["autopilot_next_action"] = "resume"
    session["autopilot_stop_reason"] = ""
    session["autopilot_escalation_reason"] = ""
    session["autopilot_updated_at"] = _now_iso()
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
    while True:
        state = load_project_state(project_path)
        if not isinstance(state, dict) or state.get("load_error"):
            session["autopilot_status"] = "error_fallback"
            session["autopilot_next_action"] = "stop"
            session["autopilot_stop_reason"] = "project_state_load_failed"
            session["autopilot_updated_at"] = _now_iso()
            session["autopilot_last_result"] = {"status": "error", "reason": "project_state_load_failed"}
            _persist_session(
                project_path,
                session,
                extra_fields=_routing_state_fields(project_name=project_name, state={}, session=session),
            )
            return {"status": "error", "reason": "Failed to load project state during autopilot run.", "session": session}

        if session["autopilot_iteration_count"] >= session["autopilot_iteration_limit"]:
            session["autopilot_status"] = "completed"
            session["autopilot_next_action"] = "stop"
            session["autopilot_stop_reason"] = "iteration_limit_reached"
            session["autopilot_escalation_reason"] = ""
            session["autopilot_updated_at"] = _now_iso()
            session["autopilot_progress_summary"] = _build_progress_summary(
                state=state,
                session=session,
                next_suggested_step="stop",
                operator_review_required=False,
            )
            _persist_session(
                project_path,
                session,
                extra_fields=_routing_state_fields(project_name=project_name, state=state, session=session),
            )
            return {"status": "ok", "reason": "Autopilot iteration limit reached.", "session": session}

        session["autopilot_status"] = "running"
        session["autopilot_updated_at"] = _now_iso()

        task = _select_next_task(state)
        active_package = _load_active_package(project_path=project_path, session=session, state=state)
        if not active_package and not task:
            session["autopilot_status"] = "completed"
            session["autopilot_next_action"] = "stop"
            session["autopilot_stop_reason"] = "no_next_bounded_task"
            session["autopilot_escalation_reason"] = ""
            session["autopilot_last_result"] = {"status": "completed", "reason": "no_next_bounded_task"}
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
                session["autopilot_next_action"] = "operator_review"
                session["autopilot_stop_reason"] = "approval_required_unresolved"
                session["autopilot_escalation_reason"] = "approval_required_unresolved"
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

        advanced_package, outcome, outcome_reason = _advance_package_pipeline(
            project_path=project_path,
            package=active_package or {},
            execution_bridge_summary=state.get("execution_bridge_summary") if isinstance(state.get("execution_bridge_summary"), dict) else {},
        )
        current_package = advanced_package or active_package or {}
        next_action = "continue"
        status_value = "running"
        stop_reason = ""
        escalation_reason = ""
        operator_review_required = False
        if outcome == "continue":
            next_action = "continue"
        elif outcome == "blocked":
            next_action = "operator_review"
            status_value = "blocked"
            stop_reason = outcome_reason
            escalation_reason = outcome_reason
            operator_review_required = True
        elif outcome == "escalated":
            next_action = "operator_review"
            status_value = "escalated"
            stop_reason = outcome_reason
            escalation_reason = outcome_reason
            operator_review_required = True
        else:
            next_action = "stop"
            status_value = "error_fallback"
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
                session["autopilot_progress_summary"] = _build_progress_summary(
                    state=state,
                    session={**session, "autopilot_status": status_value, "autopilot_next_action": next_action},
                    current_task=next_task,
                    package=current_package,
                    next_suggested_step=next_action if next_task else "stop",
                    operator_review_required=False,
                )
                session["autopilot_status"] = status_value
                session["autopilot_next_action"] = next_action if next_task else "stop"
                session["autopilot_stop_reason"] = stop_reason
                session["autopilot_escalation_reason"] = ""
                session["autopilot_updated_at"] = _now_iso()
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
        session["autopilot_next_action"] = next_action
        session["autopilot_stop_reason"] = stop_reason
        session["autopilot_escalation_reason"] = escalation_reason
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
