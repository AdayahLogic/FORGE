"""
NEXUS HELIX pipeline orchestration (Phase 21).

Bounded, staged engineering pipeline. No arbitrary execution.
AEGIS and approval remain primary; HELIX outputs are advisory until routed through governance.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from NEXUS.logging_engine import log_system_event
from NEXUS.project_state import load_project_state
from NEXUS.memory import load_project_context
from NEXUS.helix_registry import (
    HELIX_STAGES,
    normalize_helix_record,
    append_helix_record_safe,
)
from NEXUS.helix_stages import (
    run_architect_stage,
    run_builder_stage,
    run_inspector_stage,
    run_critic_stage,
    run_optimizer_stage,
    run_surgeon_stage,
)

# Stop reasons
STOP_APPROVAL_BLOCKED = "approval_blocked"
STOP_SAFETY_BLOCKED = "safety_blocked"
STOP_ERROR = "error"
STOP_COMPLETED = "completed"


def _check_helix_gates(project_path: str, project_name: str) -> tuple[bool, str, bool, bool]:
    """
    Check AEGIS/approval gates before running HELIX.
    Returns: (proceed, stop_reason, approval_blocked, safety_blocked).
    """
    try:
        from NEXUS.production_guardrails import evaluate_guardrails_safe

        loaded = load_project_state(project_path)
        if loaded.get("load_error"):
            return False, STOP_SAFETY_BLOCKED, False, True

        gr = evaluate_guardrails_safe(
            autonomous_launch=False,
            project_state=loaded,
            review_queue_entry=loaded.get("review_queue_entry"),
            recovery_result=loaded.get("recovery_result"),
            reexecution_result=loaded.get("reexecution_result"),
            target_project=project_name,
            states_by_project={project_name: loaded},
            execution_attempted=False,
        )
        if not gr.get("launch_allowed"):
            return False, STOP_SAFETY_BLOCKED, False, True

        # Check approval: if enforcement says await_approval, block
        er = loaded.get("enforcement_result") or {}
        if (er.get("workflow_action") == "await_approval" or
            (er.get("enforcement_status") or "").strip().lower() == "approval_required"):
            return False, STOP_APPROVAL_BLOCKED, True, False

        return True, "", False, False
    except Exception:
        return False, STOP_SAFETY_BLOCKED, False, True


def run_helix_pipeline(
    project_path: str,
    project_name: str,
    requested_outcome: str,
) -> dict[str, Any]:
    """
    Execute HELIX pipeline: Architect -> Builder -> Inspector -> Critic -> Optimizer -> Surgeon (if needed).
    Produces structured outputs only; no code execution.
    """
    helix_id = uuid.uuid4().hex[:16]
    started_at = datetime.utcnow().isoformat() + "Z"
    stage_results: list[dict[str, Any]] = []
    current_stage = ""
    approval_blocked = False
    safety_blocked = False
    requires_surgeon = False
    stop_reason = ""
    pipeline_status = "planned"

    log_system_event(
        project=project_name,
        subsystem="helix_pipeline",
        action="run_helix_pipeline",
        status="start",
        reason=f"Starting HELIX pipeline; requested_outcome={requested_outcome[:100]}",
    )

    proceed, stop_reason, approval_blocked, safety_blocked = _check_helix_gates(project_path, project_name)
    if not proceed:
        pipeline_status = "blocked"
        finished_at = datetime.utcnow().isoformat() + "Z"
        record = normalize_helix_record({
            "helix_id": helix_id,
            "run_id": "",
            "project_name": project_name,
            "pipeline_status": pipeline_status,
            "requested_outcome": requested_outcome,
            "stages": list(HELIX_STAGES),
            "current_stage": "",
            "stage_results": [],
            "approval_blocked": approval_blocked,
            "safety_blocked": safety_blocked,
            "requires_surgeon": False,
            "stop_reason": stop_reason,
            "started_at": started_at,
            "finished_at": finished_at,
        })
        append_helix_record_safe(project_path, record)
        return record

    loaded = load_project_state(project_path)
    if loaded.get("load_error"):
        pipeline_status = "blocked"
        safety_blocked = True
        stop_reason = STOP_SAFETY_BLOCKED
        finished_at = datetime.utcnow().isoformat() + "Z"
        record = normalize_helix_record({
            "helix_id": helix_id,
            "run_id": loaded.get("run_id", ""),
            "project_name": project_name,
            "pipeline_status": pipeline_status,
            "requested_outcome": requested_outcome,
            "stages": list(HELIX_STAGES),
            "current_stage": "",
            "stage_results": [],
            "approval_blocked": False,
            "safety_blocked": True,
            "requires_surgeon": False,
            "stop_reason": stop_reason,
            "started_at": started_at,
            "finished_at": finished_at,
        })
        append_helix_record_safe(project_path, record)
        return record

    run_id = loaded.get("run_id") or ""
    context = load_project_context(project_path)

    # Forward-compatible refs (populate from existing systems when available)
    approval_id_refs: list[str] = []
    product_id_refs: list[str] = []
    try:
        from NEXUS.approval_registry import read_approval_journal_tail
        tail = read_approval_journal_tail(project_path=project_path, n=5)
        for r in tail:
            aid = r.get("approval_id")
            if aid:
                approval_id_refs.append(str(aid))
    except Exception:
        pass
    try:
        from NEXUS.product_builder import build_product_manifest_safe
        manifest = build_product_manifest_safe(project_name=project_name, project_path=project_path)
        pid = manifest.get("product_id")
        if pid:
            product_id_refs.append(str(pid))
    except Exception:
        pass

    architect_result: dict[str, Any] = {}
    builder_result: dict[str, Any] = {}
    inspector_result: dict[str, Any] = {}
    critic_result: dict[str, Any] = {}

    try:
        # 1. Architect
        current_stage = "architect"
        architect_result = run_architect_stage(
            requested_outcome=requested_outcome,
            project_name=project_name,
            loaded_context=context,
        )
        stage_results.append(architect_result)
        if architect_result.get("stage_status") == "error_fallback":
            stop_reason = STOP_ERROR
            pipeline_status = "error_fallback"
            requires_surgeon = architect_result.get("repair_recommended", False)
            raise RuntimeError(architect_result.get("output_summary", "Architect failed"))

        # 2. Builder
        current_stage = "builder"
        builder_result = run_builder_stage(
            architect_result=architect_result,
            requested_outcome=requested_outcome,
            project_name=project_name,
        )
        stage_results.append(builder_result)

        # 3. Inspector
        current_stage = "inspector"
        inspector_result = run_inspector_stage(
            builder_result=builder_result,
            project_path=project_path,
            project_name=project_name,
        )
        stage_results.append(inspector_result)
        requires_surgeon = inspector_result.get("repair_recommended", False)

        # 4. Critic
        current_stage = "critic"
        critic_result = run_critic_stage(
            inspector_result=inspector_result,
            builder_result=builder_result,
            requested_outcome=requested_outcome,
        )
        stage_results.append(critic_result)
        requires_surgeon = requires_surgeon or critic_result.get("repair_recommended", False)

        # 5. Optimizer
        current_stage = "optimizer"
        optimizer_result = run_optimizer_stage(
            critic_result=critic_result,
            builder_result=builder_result,
        )
        stage_results.append(optimizer_result)

        # 6. Surgeon (only when repair recommended)
        current_stage = "surgeon"
        surgeon_result = run_surgeon_stage(
            critic_result=critic_result,
            inspector_result=inspector_result,
            requested_outcome=requested_outcome,
        )
        stage_results.append(surgeon_result)
        requires_surgeon = surgeon_result.get("repair_recommended", False)

        pipeline_status = "completed"
        stop_reason = STOP_COMPLETED
        current_stage = ""

    except Exception as e:
        log_system_event(
            project=project_name,
            subsystem="helix_pipeline",
            action="run_helix_pipeline",
            status="error",
            reason=str(e),
        )
        if not stop_reason:
            stop_reason = STOP_ERROR
        if pipeline_status == "planned":
            pipeline_status = "error_fallback"

    finished_at = datetime.utcnow().isoformat() + "Z"

    record = normalize_helix_record({
        "helix_id": helix_id,
        "run_id": run_id,
        "project_name": project_name,
        "pipeline_status": pipeline_status,
        "requested_outcome": requested_outcome,
        "stages": list(HELIX_STAGES),
        "current_stage": current_stage,
        "stage_results": stage_results,
        "approval_blocked": approval_blocked,
        "safety_blocked": safety_blocked,
        "requires_surgeon": requires_surgeon,
        "stop_reason": stop_reason,
        "started_at": started_at,
        "finished_at": finished_at,
        "approval_id_refs": approval_id_refs,
        "product_id_refs": product_id_refs,
    })

    append_helix_record_safe(project_path, record)

    # Phase 15: record HELIX run for learning (honest, minimal)
    try:
        from NEXUS.learning_engine import build_outcome_learning_record_safe
        from NEXUS.learning_writer import append_learning_record_safe

        state_like = {"run_id": run_id, "active_project": project_name, "project_name": project_name}
        lr = build_outcome_learning_record_safe(
            state=state_like,
            workflow_stage="helix_pipeline_run",
            decision_source="helix_pipeline",
            decision_type="helix_pipeline_completed",
            decision_summary=f"pipeline_status={pipeline_status}; stop_reason={stop_reason}; requires_surgeon={requires_surgeon}",
        )
        append_learning_record_safe(project_path=project_path, record=lr)
    except Exception:
        pass

    log_system_event(
        project=project_name,
        subsystem="helix_pipeline",
        action="run_helix_pipeline",
        status="ok" if pipeline_status == "completed" else "stopped",
        reason=f"pipeline_status={pipeline_status}; stop_reason={stop_reason}; requires_surgeon={requires_surgeon}",
    )

    return record
