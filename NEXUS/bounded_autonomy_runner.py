"""
NEXUS bounded autonomy runner (Phase 20).

Multi-step orchestration: runs up to N safe steps, stopping when gates are hit.
Uses existing run_project_autonomy, guardrails, reexecution, recovery, scheduler.
No bypass of AEGIS, approval, or enforcement.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from NEXUS.logging_engine import log_system_event
from NEXUS.project_state import load_project_state
from NEXUS.production_guardrails import evaluate_guardrails_safe
from NEXUS.reexecution_engine import evaluate_reexecution_outcome
from NEXUS.cycle_scheduler import evaluate_cycle_scheduler
from NEXUS.continuous_autonomy import run_project_autonomy
from NEXUS.autonomy_registry import (
    normalize_autonomy_record,
    append_autonomy_record_safe,
)


# Stop reasons (explicit, no silent continuation)
STOP_APPROVAL_REQUIRED = "approval_required"
STOP_ENFORCEMENT_BLOCKED = "enforcement_blocked"
STOP_REVIEW_HOLD = "review_hold"
STOP_RECOVERY_BLOCKED = "recovery_blocked"
STOP_REEXECUTION_NOT_PERMITTED = "reexecution_not_permitted"
STOP_GUARDRAILS_BLOCKED = "guardrails_blocked"
STOP_SCHEDULER_NO_NEXT_CYCLE = "scheduler_no_next_cycle"
STOP_MAX_STEPS_REACHED = "max_steps_reached"
STOP_INVALID_STATE = "invalid_state"
STOP_ERROR = "error"


def _check_pre_step_gates(loaded: dict[str, Any], project_name: str) -> tuple[bool, str, bool, bool]:
    """
    Check gates before attempting next step.
    Returns: (proceed, stop_reason, approval_blocked, safety_blocked).
    """
    rec = loaded.get("recovery_result") or {}
    rex = loaded.get("reexecution_result") or {}
    gr = loaded.get("guardrail_result") or {}
    er = loaded.get("enforcement_result") or {}
    qe = loaded.get("review_queue_entry") or {}
    sr = loaded.get("scheduler_result") or {}

    rec_status = (rec.get("recovery_status") or loaded.get("recovery_status") or "").strip().lower()
    enforcement_status = (er.get("enforcement_status") or loaded.get("enforcement_status") or "").strip().lower()
    workflow_action = (er.get("workflow_action") or "").strip().lower()
    workflow_route = (loaded.get("workflow_route") or "").strip().lower()
    queue_status = (qe.get("queue_status") or "").strip().lower()

    # Recovery blocked
    if rec_status == "blocked":
        return False, STOP_RECOVERY_BLOCKED, False, True

    # Enforcement: approval required
    if workflow_action == "await_approval" or enforcement_status == "approval_required":
        return False, STOP_APPROVAL_REQUIRED, True, False

    # Enforcement: manual review hold
    if workflow_action == "await_review" or "manual_review" in workflow_route:
        return False, STOP_REVIEW_HOLD, True, False

    # Enforcement: blocked / hold
    if workflow_action in ("stop_after_current_stage", "hold") or enforcement_status in ("blocked", "hold"):
        return False, STOP_ENFORCEMENT_BLOCKED, False, True

    # Recompute guardrails with fresh state
    gr_fresh = evaluate_guardrails_safe(
        autonomous_launch=False,
        project_state=loaded,
        review_queue_entry=qe,
        recovery_result=rec,
        reexecution_result=rex,
        target_project=project_name,
        states_by_project={project_name: loaded},
        execution_attempted=True,
    )
    if not gr_fresh.get("launch_allowed"):
        return False, STOP_GUARDRAILS_BLOCKED, False, True

    # Reexecution: run_permitted
    rex_fresh = evaluate_reexecution_outcome(
        active_project=project_name,
        run_id=loaded.get("run_id"),
        scheduler_status=loaded.get("scheduler_status"),
        scheduler_result=sr,
        recovery_status=rec_status,
        recovery_result=rec,
        resume_status=loaded.get("resume_status"),
        resume_result=loaded.get("resume_result"),
        review_queue_entry=qe,
        autonomous_cycle_summary=loaded.get("autonomous_cycle_summary"),
        project_lifecycle_status=loaded.get("project_lifecycle_status"),
        project_lifecycle_result=loaded.get("project_lifecycle_result"),
    )
    if not rex_fresh.get("run_permitted"):
        return False, STOP_REEXECUTION_NOT_PERMITTED, queue_status == "queued", False

    # Scheduler: next cycle permitted
    sched_fresh = evaluate_cycle_scheduler(
        active_project=project_name,
        run_id=loaded.get("run_id"),
        heartbeat_status=loaded.get("heartbeat_status"),
        heartbeat_result=loaded.get("heartbeat_result"),
        resume_status=loaded.get("resume_status"),
        resume_result=loaded.get("resume_result"),
        review_queue_entry=qe,
        project_lifecycle_status=loaded.get("project_lifecycle_status"),
        project_lifecycle_result=loaded.get("project_lifecycle_result"),
        governance_status=loaded.get("governance_status"),
        governance_result=loaded.get("governance_result"),
        autonomous_cycle_summary=loaded.get("autonomous_cycle_summary"),
    )
    if not sched_fresh.get("next_cycle_permitted"):
        return False, STOP_SCHEDULER_NO_NEXT_CYCLE, False, False

    return True, "", False, False


def run_bounded_autonomy(
    project_path: str,
    project_name: str,
    max_steps: int = 3,
) -> dict[str, Any]:
    """
    Execute up to max_steps safe autonomy runs, stopping when any gate hits.
    Each step = one run_project_autonomy invocation.
    """
    autonomy_id = uuid.uuid4().hex[:16]
    started_at = datetime.utcnow().isoformat() + "Z"
    step_results: list[dict[str, Any]] = []
    steps_attempted = 0
    steps_completed = 0
    stop_reason = ""
    approval_blocked = False
    safety_blocked = False
    reached_limit = False
    autonomy_status = "idle"

    if max_steps < 1:
        max_steps = 1
    if max_steps > 10:
        max_steps = 10

    log_system_event(
        project=project_name,
        subsystem="bounded_autonomy_runner",
        action="run_bounded_autonomy",
        status="start",
        reason=f"Starting bounded autonomy run; max_steps={max_steps}.",
    )

    loaded = load_project_state(project_path)
    if loaded.get("load_error"):
        stop_reason = STOP_INVALID_STATE
        autonomy_status = "blocked"
        finished_at = datetime.utcnow().isoformat() + "Z"
        record = normalize_autonomy_record({
            "autonomy_id": autonomy_id,
            "run_id": loaded.get("run_id", ""),
            "project_name": project_name,
            "autonomy_status": autonomy_status,
            "autonomy_mode": "bounded_multi_step",
            "max_steps": max_steps,
            "steps_attempted": 0,
            "steps_completed": 0,
            "stop_reason": stop_reason,
            "approval_blocked": False,
            "safety_blocked": True,
            "reached_limit": False,
            "step_results": [],
            "started_at": started_at,
            "finished_at": finished_at,
        })
        append_autonomy_record_safe(project_path, record)
        return record

    for step_num in range(1, max_steps + 1):
        loaded = load_project_state(project_path)
        if loaded.get("load_error"):
            stop_reason = STOP_INVALID_STATE
            autonomy_status = "blocked"
            break

        proceed, stop_reason, approval_blocked, safety_blocked = _check_pre_step_gates(loaded, project_name)
        if not proceed:
            autonomy_status = "blocked" if safety_blocked else "stopped"
            break

        steps_attempted += 1
        try:
            single_result = run_project_autonomy(
                project_path=project_path,
                project_name=project_name,
                project_state=loaded,
            )
        except Exception as e:
            log_system_event(
                project=project_name,
                subsystem="bounded_autonomy_runner",
                action="run_project_autonomy",
                status="error",
                reason=str(e),
            )
            step_results.append({
                "step": step_num,
                "status": "error",
                "reason": str(e),
                "autonomy_status": "error_fallback",
            })
            stop_reason = STOP_ERROR
            autonomy_status = "stopped"
            break

        ran = bool(single_result.get("autonomous_run_started"))
        if ran:
            steps_completed += 1
        step_results.append({
            "step": step_num,
            "status": "ran" if ran else "idle",
            "autonomy_status": single_result.get("autonomy_status", "idle"),
            "autonomy_reason": single_result.get("autonomy_reason", ""),
        })

        if step_num >= max_steps:
            reached_limit = True
            stop_reason = STOP_MAX_STEPS_REACHED
            autonomy_status = "completed"
            break

        loaded = load_project_state(project_path)
        proceed, stop_reason, approval_blocked, safety_blocked = _check_pre_step_gates(loaded, project_name)
        if not proceed:
            autonomy_status = "blocked" if safety_blocked else "stopped"
            break

    finished_at = datetime.utcnow().isoformat() + "Z"
    if not stop_reason and autonomy_status == "idle":
        stop_reason = "no_steps_attempted" if steps_attempted == 0 else "completed"

    approval_id_refs: list[str] = []
    product_id_refs: list[str] = []
    try:
        from NEXUS.approval_registry import read_approval_journal_tail
        for r in read_approval_journal_tail(project_path=project_path, n=5):
            aid = r.get("approval_id")
            if aid:
                approval_id_refs.append(str(aid))
    except Exception:
        pass
    try:
        from NEXUS.product_builder import build_product_manifest_safe
        m = build_product_manifest_safe(project_name=project_name, project_path=project_path)
        pid = m.get("product_id")
        if pid:
            product_id_refs.append(str(pid))
    except Exception:
        pass

    record = normalize_autonomy_record({
        "autonomy_id": autonomy_id,
        "run_id": loaded.get("run_id", ""),
        "project_name": project_name,
        "autonomy_status": autonomy_status,
        "autonomy_mode": "bounded_multi_step",
        "max_steps": max_steps,
        "steps_attempted": steps_attempted,
        "steps_completed": steps_completed,
        "stop_reason": stop_reason,
        "approval_blocked": approval_blocked,
        "safety_blocked": safety_blocked,
        "reached_limit": reached_limit,
        "step_results": step_results,
        "started_at": started_at,
        "finished_at": finished_at,
        "approval_id_refs": approval_id_refs,
        "product_id_refs": product_id_refs,
    })

    append_autonomy_record_safe(project_path, record)

    # Phase 15: record bounded autonomy run for learning (honest, minimal).
    try:
        from NEXUS.learning_engine import build_outcome_learning_record_safe
        from NEXUS.learning_writer import append_learning_record_safe

        state_like = {
            "run_id": record.get("run_id"),
            "active_project": project_name,
            "project_name": project_name,
        }
        lr = build_outcome_learning_record_safe(
            state=state_like,
            workflow_stage="bounded_autonomy_run",
            decision_source="bounded_autonomy_runner",
            decision_type="autonomy_run_completed",
            decision_summary=f"steps={steps_completed}/{steps_attempted}; stop_reason={stop_reason}",
        )
        lr["autonomy_id_refs"] = [autonomy_id]
        lr["approval_id_refs"] = approval_id_refs[:5]
        lr["product_id_refs"] = product_id_refs[:5]
        append_learning_record_safe(project_path=project_path, record=lr)
    except Exception:
        pass

    log_system_event(
        project=project_name,
        subsystem="bounded_autonomy_runner",
        action="run_bounded_autonomy",
        status="ok" if autonomy_status in ("completed", "ran") else "stopped",
        reason=f"steps_attempted={steps_attempted}; steps_completed={steps_completed}; stop_reason={stop_reason}",
    )

    return record
