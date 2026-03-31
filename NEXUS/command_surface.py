"""
NEXUS studio command surface.

Small read-focused command layer for routine operations: health, latest_session,
ledger_tail, project_summary, registry_status. Returns normalized result dicts.
No async, no CLI framework; minimal safe changes.
"""

from __future__ import annotations

from typing import Any

from NEXUS.registry import PROJECTS
from NEXUS.project_state import load_project_state, update_project_state_fields
from NEXUS.execution_ledger import get_ledger_path, read_ledger_tail
from NEXUS.system_health import evaluate_system_health
from NEXUS.agent_registry import get_runtime_routable_agents
from NEXUS.tool_registry import list_active_tools, list_planned_tools
from NEXUS.engine_registry import list_active_engines, list_planned_engines
from NEXUS.capability_registry import list_active_capabilities, list_planned_capabilities
from NEXUS.registry_dashboard import build_registry_dashboard_summary
from NEXUS.runtime_target_registry import get_runtime_target_summary
from NEXUS.runtime_target_selector import select_runtime_target
from NEXUS.execution_environment_summary import build_per_project_environment_summary
from NEXUS.memory_layer import build_memory_layer_summary_safe, read_governed_memory_safe

from NEXUS.logging_engine import log_system_event

SUPPORTED_COMMANDS = frozenset({
    "health",
    "latest_session",
    "ledger_tail",
    "project_summary",
    "project_autopilot_start",
    "project_autopilot_status",
    "project_autopilot_pause",
    "project_autopilot_resume",
    "project_autopilot_stop",
    "project_autonomy_mode_set",
    "project_autonomy_mode_status",
    "project_routing_status",
    "registry_status",
    "dashboard_summary",
    "runtime_targets",
    "runtime_select",
    "dispatch_plan",
    "dispatch_status",
    "execution_package_queue",
    "execution_package_details",
    "execution_package_decide",
    "execution_package_decision_status",
    "execution_package_eligibility_check",
    "execution_package_eligibility_status",
    "execution_package_release_request",
    "execution_package_release_status",
    "execution_package_handoff_request",
    "execution_package_handoff_status",
    "execution_package_execute_request",
    "execution_package_execute_status",
    "execution_package_evaluate",
    "execution_package_evaluation_status",
    "execution_package_local_analysis",
    "execution_package_local_analysis_status",
    "automation_status",
    "agent_status",
    "governance_status",
    "project_lifecycle",
    "enforcement_status",
    "review_queue",
    "resume_status",
    "heartbeat_status",
    "scheduler_status",
    "studio_coordination",
    "complete_review",
    "complete_approval",
    "recovery_status",
    "reexecution_status",
    "studio_driver",
    "launch_next_cycle",
    "launch_studio_cycle",
    "launch_status",
    "autonomous_cycle",
    "autonomous_studio_cycle",
    "autonomy_status",
    "autonomy_run",
    "autonomy_trace",
    "portfolio_autonomy_status",
    "portfolio_autonomy_trace",
    "portfolio_autonomy_revenue_priority",
    "persistent_kill_switch_status",
    "helix_status",
    "helix_run",
    "helix_trace",
    "guardrail_status",
    "runtime_route",
    "model_route",
    "deployment_preflight",
    "operator_snapshot",
    "forge_os_snapshot",
    "portfolio_status",
    "runtime_infrastructure",
    "execution_environment",
    "memory_status",
    "meta_engine_status",
    "titan_status",
    "leviathan_status",
    "helios_status",
    "helios_proposal",
    "veritas_status",
    "sentinel_status",
    "elite_systems_snapshot",
    # GENESIS (Phase 10): idea generation/ranking evaluation-only.
    "genesis_generate",
    "genesis_refine",
    "genesis_rank",
    # Controlled studio loop (Phase 12): bounded selection only.
    "studio_loop_tick",
    "prism_evaluate",
    "prism_status",
    "project_onboard",
    "self_improvement_backlog",
    "improve_system",
    "change_gate",
    "regression_check",
    # AEGIS Phase 13
    "aegis_status",
    "forgeshell_status",
    "forgeshell_test",
    "tool_gateway_status",
    # Phase 18: approval system
    "pending_approvals",
    "approval_details",
    # Phase 19: productization
    "product_manifest",
    "product_summary",
    # Phase 21: HELIX pipeline
    "helix_status",
    "helix_run",
    "helix_trace",
    # Hardening: integrity checker
    "integrity_check",
    # Phase 23: patch proposals
    "patch_proposals",
    "patch_proposal_details",
    # Phase 24: approval resolution
    "approve_patch_proposal",
    "reject_patch_proposal",
    "apply_patch_proposal",
    # Phase 25: approval maturity
    "retry_patch_proposal",
    "approval_trace",
    # Phase 39: approval lifecycle
    "approval_lifecycle_status",
    "reapproval_status",
    "retry_after_expiry_status",
    # Phase 26: operator release readiness
    "release_readiness",
    "operator_release_summary",
    # Phase 40: runtime isolation
    "runtime_isolation_status",
    "sandbox_posture",
    # Phase 27: cross-artifact trace
    "artifact_trace",
    # Phase 37: candidate review workflow
    "candidate_review_status",
    "review_candidate",
    "candidate_review_details",
})


def _resolve_project_path(project_path: str | None = None, project_name: str | None = None) -> tuple[str | None, str | None]:
    """Return (project_path, project_name). Prefer project_path if given."""
    if project_path:
        return project_path, project_name
    if project_name:
        key = str(project_name).strip().lower()
        if key in PROJECTS:
            return PROJECTS[key]["path"], PROJECTS[key].get("name") or key
        return None, key
    return None, None


def _result(
    command: str,
    status: str,
    project_name: str | None = None,
    summary: str = "",
    payload: dict | list | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "command": command,
        "status": status,
        "project_name": project_name,
        "summary": summary,
        "payload": payload if payload is not None else {},
    }
    return out


def _execution_package_error_result(
    *,
    command: str,
    reason: str,
    project_name: str | None,
    project_path: str | None,
    package_id: str | None = None,
) -> dict[str, Any]:
    return _result(
        command=command,
        status="error",
        project_name=project_name,
        summary=reason,
        payload={
            "status": "error",
            "reason": reason,
            "project_path": project_path,
            "package_id": package_id,
        },
    )


def _build_execution_package_review_header(package: dict[str, Any] | None) -> dict[str, Any]:
    p = package or {}
    cursor_bridge = dict(p.get("cursor_bridge_summary") or {})
    return {
        "package_id": p.get("package_id"),
        "package_kind": p.get("package_kind"),
        "package_status": p.get("package_status"),
        "review_status": p.get("review_status"),
        "sealed": p.get("sealed"),
        "seal_reason": p.get("seal_reason"),
        "runtime_target_id": p.get("runtime_target_id"),
        "requires_human_approval": p.get("requires_human_approval"),
        "approval_id_refs": p.get("approval_id_refs") or [],
        "aegis_decision": p.get("aegis_decision"),
        "aegis_scope": p.get("aegis_scope"),
        "reason": p.get("reason"),
        "decision_status": p.get("decision_status"),
        "decision_timestamp": p.get("decision_timestamp"),
        "decision_actor": p.get("decision_actor"),
        "decision_id": p.get("decision_id"),
        "eligibility_status": p.get("eligibility_status"),
        "eligibility_timestamp": p.get("eligibility_timestamp"),
        "eligibility_reason": p.get("eligibility_reason") or {"code": "", "message": ""},
        "eligibility_check_id": p.get("eligibility_check_id"),
        "release_status": p.get("release_status"),
        "release_timestamp": p.get("release_timestamp"),
        "release_reason": p.get("release_reason") or {"code": "", "message": ""},
        "release_id": p.get("release_id"),
        "handoff_status": p.get("handoff_status"),
        "handoff_timestamp": p.get("handoff_timestamp"),
        "handoff_reason": p.get("handoff_reason") or {"code": "", "message": ""},
        "handoff_id": p.get("handoff_id"),
        "handoff_executor_target_id": p.get("handoff_executor_target_id"),
        "handoff_executor_target_name": p.get("handoff_executor_target_name"),
        "execution_status": p.get("execution_status"),
        "execution_timestamp": p.get("execution_timestamp"),
        "execution_reason": p.get("execution_reason") or {"code": "", "message": ""},
        "execution_id": p.get("execution_id"),
        "execution_executor_target_id": p.get("execution_executor_target_id"),
        "execution_executor_target_name": p.get("execution_executor_target_name"),
        "execution_executor_backend_id": p.get("execution_executor_backend_id"),
        "idempotency_status": ((p.get("idempotency") or {}).get("idempotency_status") or "active"),
        "retry_policy_status": ((p.get("retry_policy") or {}).get("policy_status") or "default_no_retry"),
        "failure_class": ((p.get("failure_summary") or {}).get("failure_class") or ""),
        "failure_stage": ((p.get("failure_summary") or {}).get("failure_stage") or ""),
        "recovery_status": ((p.get("recovery_summary") or {}).get("recovery_status") or "not_needed"),
        "rollback_repair_status": ((p.get("rollback_repair") or {}).get("rollback_repair_status") or "not_needed"),
        "integrity_status": ((p.get("integrity_verification") or {}).get("integrity_status") or "not_verified"),
        "evaluation_status": p.get("evaluation_status"),
        "evaluation_timestamp": p.get("evaluation_timestamp"),
        "evaluation_actor": p.get("evaluation_actor"),
        "evaluation_id": p.get("evaluation_id"),
        "evaluation_reason": p.get("evaluation_reason") or {"code": "", "message": ""},
        "local_analysis_status": p.get("local_analysis_status"),
        "local_analysis_timestamp": p.get("local_analysis_timestamp"),
        "local_analysis_actor": p.get("local_analysis_actor"),
        "local_analysis_id": p.get("local_analysis_id"),
        "local_analysis_reason": p.get("local_analysis_reason") or {"code": "", "message": ""},
        "bridge_task_id": cursor_bridge.get("bridge_task_id"),
        "cursor_bridge_status": cursor_bridge.get("bridge_status"),
        "cursor_bridge_artifact_count": cursor_bridge.get("artifact_count"),
        "cursor_bridge_latest_artifact_type": cursor_bridge.get("latest_artifact_type"),
        "cursor_bridge_latest_validation_status": cursor_bridge.get("latest_validation_status"),
        "pipeline_stage": p.get("pipeline_stage") or "intake",
        "highest_value_next_action": p.get("highest_value_next_action") or "",
        "highest_value_next_action_score": p.get("highest_value_next_action_score") or 0.0,
        "highest_value_next_action_reason": p.get("highest_value_next_action_reason") or "",
        "revenue_activation_status": p.get("revenue_activation_status") or "needs_revision",
        "revenue_workflow_ready": bool(p.get("revenue_workflow_ready")),
        "revenue_workflow_block_reason": p.get("revenue_workflow_block_reason") or "",
        "opportunity_classification": p.get("opportunity_classification") or "cold",
        "opportunity_classification_reason": p.get("opportunity_classification_reason") or "",
    }


def _build_execution_package_sections(package: dict[str, Any] | None) -> dict[str, Any]:
    p = package or {}
    cursor_bridge = dict(p.get("cursor_bridge_summary") or {})
    sections = {
        "command_request": dict(p.get("command_request") or {}),
        "scope": {
            "candidate_paths": list(p.get("candidate_paths") or []),
            "expected_outputs": list(p.get("expected_outputs") or []),
            "dispatch_plan_summary": dict(p.get("dispatch_plan_summary") or {}),
            "routing_summary": dict(p.get("routing_summary") or {}),
            "execution_summary": dict(p.get("execution_summary") or {}),
        },
        "approval": {
            "requires_human_approval": bool(p.get("requires_human_approval")),
            "approval_id_refs": list(p.get("approval_id_refs") or []),
            "aegis_decision": p.get("aegis_decision") or "",
            "aegis_scope": p.get("aegis_scope") or "",
        },
        "safety": {
            "sealed": bool(p.get("sealed")),
            "seal_reason": p.get("seal_reason") or "",
            "review_checklist": list(p.get("review_checklist") or []),
            "runtime_artifacts": list(p.get("runtime_artifacts") or []),
        },
        "rollback": {
            "rollback_notes": list(p.get("rollback_notes") or []),
        },
        "decision": {
            "decision_status": p.get("decision_status") or "pending",
            "decision_timestamp": p.get("decision_timestamp") or "",
            "decision_actor": p.get("decision_actor") or "",
            "decision_notes": p.get("decision_notes") or "",
            "decision_id": p.get("decision_id") or "",
        },
        "eligibility": {
            "eligibility_status": p.get("eligibility_status") or "pending",
            "eligibility_timestamp": p.get("eligibility_timestamp") or "",
            "eligibility_reason": p.get("eligibility_reason") or {"code": "", "message": ""},
            "eligibility_checked_by": p.get("eligibility_checked_by") or "",
            "eligibility_check_id": p.get("eligibility_check_id") or "",
        },
        "release": {
            "release_status": p.get("release_status") or "pending",
            "release_timestamp": p.get("release_timestamp") or "",
            "release_actor": p.get("release_actor") or "",
            "release_notes": p.get("release_notes") or "",
            "release_id": p.get("release_id") or "",
            "release_reason": p.get("release_reason") or {"code": "", "message": ""},
            "release_version": p.get("release_version") or "v1",
        },
        "handoff": {
            "handoff_status": p.get("handoff_status") or "pending",
            "handoff_timestamp": p.get("handoff_timestamp") or "",
            "handoff_actor": p.get("handoff_actor") or "",
            "handoff_notes": p.get("handoff_notes") or "",
            "handoff_id": p.get("handoff_id") or "",
            "handoff_reason": p.get("handoff_reason") or {"code": "", "message": ""},
            "handoff_version": p.get("handoff_version") or "v1",
            "handoff_executor_target_id": p.get("handoff_executor_target_id") or "",
            "handoff_executor_target_name": p.get("handoff_executor_target_name") or "",
            "handoff_aegis_result": dict(p.get("handoff_aegis_result") or {}),
        },
        "execution": {
            "execution_status": p.get("execution_status") or "pending",
            "execution_timestamp": p.get("execution_timestamp") or "",
            "execution_actor": p.get("execution_actor") or "",
            "execution_id": p.get("execution_id") or "",
            "execution_reason": p.get("execution_reason") or {"code": "", "message": ""},
            "execution_receipt": dict(p.get("execution_receipt") or {}),
            "execution_version": p.get("execution_version") or "v1",
            "execution_executor_target_id": p.get("execution_executor_target_id") or "",
            "execution_executor_target_name": p.get("execution_executor_target_name") or "",
            "execution_executor_backend_id": p.get("execution_executor_backend_id") or "",
            "execution_aegis_result": dict(p.get("execution_aegis_result") or {}),
            "execution_started_at": p.get("execution_started_at") or "",
            "execution_finished_at": p.get("execution_finished_at") or "",
            "rollback_status": p.get("rollback_status") or "not_needed",
            "rollback_timestamp": p.get("rollback_timestamp") or "",
            "rollback_reason": p.get("rollback_reason") or {"code": "", "message": ""},
            "retry_policy": dict(p.get("retry_policy") or {}),
            "idempotency": dict(p.get("idempotency") or {}),
            "failure_summary": dict(p.get("failure_summary") or {}),
            "recovery_summary": dict(p.get("recovery_summary") or {}),
            "rollback_repair": dict(p.get("rollback_repair") or {}),
            "integrity_verification": dict(p.get("integrity_verification") or {}),
        },
        "metadata": dict(p.get("metadata") or {}),
    }
    cursor_bridge_artifacts = list(p.get("cursor_bridge_artifacts") or [])
    if cursor_bridge or cursor_bridge_artifacts:
        sections["cursor_bridge"] = {
            "summary": cursor_bridge,
            "artifacts": cursor_bridge_artifacts,
        }
    return sections


def _build_execution_package_queue_row(package: dict[str, Any] | None) -> dict[str, Any]:
    p = package or {}
    cursor_bridge = dict(p.get("cursor_bridge_summary") or {})
    return {
        "package_id": p.get("package_id"),
        "created_at": p.get("created_at"),
        "package_status": p.get("package_status"),
        "review_status": p.get("review_status"),
        "runtime_target_id": p.get("runtime_target_id"),
        "decision_status": p.get("decision_status"),
        "eligibility_status": p.get("eligibility_status"),
        "release_status": p.get("release_status"),
        "handoff_status": p.get("handoff_status"),
        "execution_status": p.get("execution_status"),
        "evaluation_status": p.get("evaluation_status"),
        "failure_class": ((p.get("failure_summary") or {}).get("failure_class") or ""),
        "recovery_status": ((p.get("recovery_summary") or {}).get("recovery_status") or "not_needed"),
        "retry_policy_status": ((p.get("retry_policy") or {}).get("policy_status") or "default_no_retry"),
        "retry_authorized": bool((p.get("retry_policy") or {}).get("retry_authorized", False)),
        "idempotency_status": ((p.get("idempotency") or {}).get("idempotency_status") or "active"),
        "duplicate_success_blocked": bool((p.get("idempotency") or {}).get("duplicate_success_blocked", False)),
        "rollback_repair_status": ((p.get("rollback_repair") or {}).get("rollback_repair_status") or "not_needed"),
        "integrity_status": ((p.get("integrity_verification") or {}).get("integrity_status") or "not_verified"),
        "failure_risk_band": ((p.get("evaluation_summary") or {}).get("failure_risk_band") or ""),
        "local_analysis_status": p.get("local_analysis_status"),
        "suggested_next_action": ((p.get("local_analysis_summary") or {}).get("suggested_next_action") or ""),
        "bridge_task_id": cursor_bridge.get("bridge_task_id"),
        "cursor_bridge_status": cursor_bridge.get("bridge_status"),
        "cursor_bridge_artifact_count": cursor_bridge.get("artifact_count"),
        "cursor_bridge_latest_validation_status": cursor_bridge.get("latest_validation_status"),
        "pipeline_stage": p.get("pipeline_stage") or "intake",
        "highest_value_next_action": p.get("highest_value_next_action") or "",
        "highest_value_next_action_score": p.get("highest_value_next_action_score") or 0.0,
        "revenue_activation_status": p.get("revenue_activation_status") or "needs_revision",
        "revenue_workflow_priority": p.get("revenue_workflow_priority") or "medium",
        "revenue_workflow_block_reason": p.get("revenue_workflow_block_reason") or "",
        "opportunity_classification": p.get("opportunity_classification") or "cold",
    }


def _build_execution_package_evaluation(package: dict[str, Any] | None) -> dict[str, Any]:
    p = package or {}
    return {
        "evaluation_status": p.get("evaluation_status") or "pending",
        "evaluation_timestamp": p.get("evaluation_timestamp") or "",
        "evaluation_actor": p.get("evaluation_actor") or "",
        "evaluation_id": p.get("evaluation_id") or "",
        "evaluation_version": p.get("evaluation_version") or "v1",
        "evaluation_reason": p.get("evaluation_reason") or {"code": "", "message": ""},
        "evaluation_basis": p.get("evaluation_basis") or {},
        "evaluation_summary": p.get("evaluation_summary") or {},
    }


def _build_execution_package_local_analysis(package: dict[str, Any] | None) -> dict[str, Any]:
    p = package or {}
    return {
        "local_analysis_status": p.get("local_analysis_status") or "pending",
        "local_analysis_timestamp": p.get("local_analysis_timestamp") or "",
        "local_analysis_actor": p.get("local_analysis_actor") or "nemoclaw",
        "local_analysis_id": p.get("local_analysis_id") or "",
        "local_analysis_version": p.get("local_analysis_version") or "v1",
        "local_analysis_reason": p.get("local_analysis_reason") or {"code": "", "message": ""},
        "local_analysis_basis": p.get("local_analysis_basis") or {},
        "local_analysis_summary": p.get("local_analysis_summary") or {},
    }


def run_command(
    command: str,
    project_path: str | None = None,
    project_name: str | None = None,
    n: int = 20,
    agent_name: str | None = None,
    tool_name: str | None = None,
    action_type: str | None = None,
    task_type: str | None = None,
    sensitivity: str | None = None,
    review_context: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Execute a single studio command and return a normalized result dict.

    Supported commands: health, latest_session, ledger_tail, project_summary, registry_status, dashboard_summary, runtime_targets, runtime_select, dispatch_plan, dispatch_status, automation_status, agent_status, governance_status, project_lifecycle, enforcement_status.
    Result shape: command, status, project_name, summary, payload.
    For runtime_select, optional agent_name, tool_name, action_type, task_type, sensitivity, review_context are passed to the selector.
    """
    cmd = (command or "").strip().lower()
    if cmd not in SUPPORTED_COMMANDS:
        return _result(
            command=cmd or "(empty)",
            status="error",
            summary=f"Unknown command. Supported: {sorted(SUPPORTED_COMMANDS)}",
            payload={"supported_commands": sorted(SUPPORTED_COMMANDS)},
        )

    path, proj_name = _resolve_project_path(project_path=project_path, project_name=project_name)

    # High-value log: command invoked (once per invocation).
    log_system_event(
        project=proj_name,
        subsystem="command_surface",
        action=f"command:{cmd}",
        status="received",
        reason="Command invoked.",
    )

    if cmd == "registry_status":
        try:
            projects_list = list(PROJECTS.keys())
            agents_list = get_runtime_routable_agents()
            tools_active = list_active_tools()
            tools_planned = list_planned_tools()
            engines_active = list_active_engines()
            engines_planned = list_planned_engines()
            caps_active = list_active_capabilities()
            caps_planned = list_planned_capabilities()
            payload = {
                "projects": projects_list,
                "project_count": len(projects_list),
                "agents_routable": agents_list,
                "agent_count": len(agents_list),
                "tools_active": tools_active,
                "tools_planned": tools_planned,
                "tool_active_count": len(tools_active),
                "tool_planned_count": len(tools_planned),
                "engines_active": engines_active,
                "engines_planned": engines_planned,
                "engine_active_count": len(engines_active),
                "engine_planned_count": len(engines_planned),
                "capabilities_active": caps_active,
                "capabilities_planned": caps_planned,
                "capability_active_count": len(caps_active),
                "capability_planned_count": len(caps_planned),
            }
            return _result(
                command=cmd,
                status="ok",
                summary="Registry counts and names.",
                payload=payload,
            )
        except Exception as e:
            return _result(command=cmd, status="error", summary=str(e), payload={"error": str(e)})

    if cmd == "dashboard_summary":
        try:
            snapshot = build_registry_dashboard_summary()
            return _result(
                command=cmd,
                status="ok",
                summary=f"Unified registry snapshot for {snapshot.get('studio_name', 'NEXUS')}.",
                payload=snapshot,
            )
        except Exception as e:
            return _result(command=cmd, status="error", summary=str(e), payload={"error": str(e)})

    if cmd == "runtime_targets":
        try:
            summary = get_runtime_target_summary()
            return _result(
                command=cmd,
                status="ok",
                summary=f"Active: {summary.get('active_count', 0)}, planned: {summary.get('planned_count', 0)}.",
                payload=summary,
            )
        except Exception as e:
            return _result(command=cmd, status="error", summary=str(e), payload={"error": str(e)})

    if cmd == "runtime_select":
        try:
            decision = select_runtime_target(
                agent_name=agent_name,
                tool_name=tool_name,
                action_type=action_type,
                task_type=task_type,
                sensitivity=sensitivity,
                review_context=review_context,
            )
            return _result(
                command=cmd,
                status="ok",
                summary=f"Selected: {decision.get('selected_target', '')}; {decision.get('selection_status', '')}.",
                payload=decision,
            )
        except Exception as e:
            return _result(command=cmd, status="error", summary=str(e), payload={"error": str(e)})

    if cmd == "dispatch_plan":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(
                    command=cmd,
                    status="error",
                    project_name=proj_name,
                    summary=loaded.get("load_error", "Failed to load state."),
                    payload=loaded,
                )
            summary_data = loaded.get("dispatch_plan_summary") or {}
            status_str = summary_data.get("dispatch_planning_status", "unknown")
            ready = summary_data.get("ready_for_dispatch", False)
            summary_line = f"status={status_str}; ready_for_dispatch={ready}"
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=summary_line,
                payload=summary_data,
            )
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "dispatch_status":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(
                    command=cmd,
                    status="error",
                    project_name=proj_name,
                    summary=loaded.get("load_error", "Failed to load state."),
                    payload=loaded,
                )
            dispatch_status_val = loaded.get("dispatch_status")
            dispatch_result_val = loaded.get("dispatch_result") or {}
            dr_status = dispatch_result_val.get("status")
            dr_exec_status = dispatch_result_val.get("execution_status")
            execution_package_id = loaded.get("execution_package_id") or dispatch_result_val.get("execution_package_id")
            execution_package_path = loaded.get("execution_package_path") or dispatch_result_val.get("execution_package_path")
            summary_line = f"dispatch_status={dispatch_status_val}; result_status={dr_status}; execution_status={dr_exec_status}"
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=summary_line,
                payload={
                    "dispatch_status": dispatch_status_val,
                    "runtime_target": (dispatch_result_val.get("runtime_target") or dispatch_result_val.get("runtime")),
                    "execution_package_id": execution_package_id,
                    "execution_package_path": execution_package_path,
                    "dispatch_result": {
                        "status": dr_status,
                        "execution_status": dr_exec_status,
                        "message": dispatch_result_val.get("message"),
                    },
                },
            )
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "execution_package_queue":
        if not path:
            return _execution_package_error_result(
                command=cmd,
                reason="Project path or project_name required.",
                project_name=proj_name,
                project_path=path,
            )
        try:
            from NEXUS.execution_package_registry import list_execution_package_journal_entries

            limit = max(1, min(int(n or 20), 50))
            packages = list_execution_package_journal_entries(project_path=path, n=limit)
            queue_rows = [_build_execution_package_queue_row(pkg) for pkg in packages]
            pending_count = sum(
                1
                for pkg in queue_rows
                if str(pkg.get("review_status") or "") in ("pending", "review_pending")
                or str(pkg.get("package_status") or "") in ("pending", "review_pending")
            )
            ranked_revenue = sorted(
                [
                    row
                    for row in queue_rows
                    if str(row.get("revenue_activation_status") or "") == "ready_for_revenue_action"
                ],
                key=lambda row: float(row.get("highest_value_next_action_score") or 0.0),
                reverse=True,
            )
            blocked_revenue = [
                {
                    "package_id": row.get("package_id"),
                    "revenue_activation_status": row.get("revenue_activation_status"),
                    "revenue_workflow_block_reason": row.get("revenue_workflow_block_reason") or "Blocked by governance/enforcement posture.",
                    "pipeline_stage": row.get("pipeline_stage"),
                    "highest_value_next_action": row.get("highest_value_next_action"),
                }
                for row in queue_rows
                if str(row.get("revenue_activation_status") or "") == "blocked_for_revenue_action"
            ]
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=f"packages={len(packages)}; pending={pending_count}",
                payload={
                    "status": "ok",
                    "reason": "Execution package queue loaded.",
                    "project_path": path,
                    "count": len(packages),
                    "pending_count": pending_count,
                    "packages": queue_rows,
                    "top_revenue_candidates": [
                        {
                            "package_id": row.get("package_id"),
                            "highest_value_next_action": row.get("highest_value_next_action"),
                            "highest_value_next_action_score": row.get("highest_value_next_action_score"),
                            "pipeline_stage": row.get("pipeline_stage"),
                            "opportunity_classification": row.get("opportunity_classification"),
                        }
                        for row in ranked_revenue[:5]
                    ],
                    "blocked_revenue_candidates": blocked_revenue[:5],
                },
            )
        except Exception as e:
            return _execution_package_error_result(
                command=cmd,
                reason=str(e),
                project_name=proj_name,
                project_path=path,
            )

    if cmd == "execution_package_details":
        package_id = str(kwargs.get("execution_package_id") or "").strip() or None
        if not path:
            return _execution_package_error_result(
                command=cmd,
                reason="Project path or project_name required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if not package_id:
            return _execution_package_error_result(
                command=cmd,
                reason="execution_package_id required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        try:
            from NEXUS.execution_package_registry import get_execution_package_file_path, read_execution_package

            package = read_execution_package(project_path=path, package_id=package_id)
            if not package:
                return _execution_package_error_result(
                    command=cmd,
                    reason="Execution package not found.",
                    project_name=proj_name,
                    project_path=path,
                    package_id=package_id,
                )
            review_header = _build_execution_package_review_header(package)
            sections = _build_execution_package_sections(package)
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=f"package_id={package_id}; review_status={package.get('review_status')}; sealed={package.get('sealed')}",
                payload={
                    "status": "ok",
                    "reason": "Execution package loaded.",
                    "project_path": path,
                    "package_id": package_id,
                    "package_path": get_execution_package_file_path(path, package_id),
                    "review_header": review_header,
                    "package": package,
                    "sections": sections,
                },
            )
        except Exception as e:
            return _execution_package_error_result(
                command=cmd,
                reason=str(e),
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )

    if cmd == "execution_package_decide":
        package_id = str(kwargs.get("execution_package_id") or "").strip() or None
        decision_status = str(kwargs.get("decision_status") or "").strip().lower()
        decision_actor = str(kwargs.get("decision_actor") or "").strip()
        decision_notes = str(kwargs.get("decision_notes") or "")
        if not path:
            return _execution_package_error_result(
                command=cmd,
                reason="Project path or project_name required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if not package_id:
            return _execution_package_error_result(
                command=cmd,
                reason="execution_package_id required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if decision_status not in ("approved", "rejected"):
            return _execution_package_error_result(
                command=cmd,
                reason="decision_status must be approved or rejected.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if not decision_actor:
            return _execution_package_error_result(
                command=cmd,
                reason="decision_actor required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        try:
            from NEXUS.execution_package_registry import record_execution_package_decision_safe

            result = record_execution_package_decision_safe(
                project_path=path,
                package_id=package_id,
                decision_status=decision_status,
                decision_actor=decision_actor,
                decision_notes=decision_notes,
            )
            if result.get("status") != "ok":
                return _execution_package_error_result(
                    command=cmd,
                    reason=str(result.get("reason") or "Failed to record execution package decision."),
                    project_name=proj_name,
                    project_path=path,
                    package_id=package_id,
                )
            package = result.get("package") or {}
            decision = {
                "decision_status": package.get("decision_status"),
                "decision_timestamp": package.get("decision_timestamp"),
                "decision_actor": package.get("decision_actor"),
                "decision_notes": package.get("decision_notes"),
                "decision_id": package.get("decision_id"),
            }
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=f"package_id={package_id}; decision_status={decision.get('decision_status')}",
                payload={
                    "status": "ok",
                    "reason": "Execution package decision recorded.",
                    "project_path": path,
                    "package_id": package_id,
                    "decision": decision,
                },
            )
        except Exception as e:
            return _execution_package_error_result(
                command=cmd,
                reason=str(e),
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )

    if cmd == "execution_package_decision_status":
        package_id = str(kwargs.get("execution_package_id") or "").strip() or None
        if not path:
            return _execution_package_error_result(
                command=cmd,
                reason="Project path or project_name required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if not package_id:
            return _execution_package_error_result(
                command=cmd,
                reason="execution_package_id required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        try:
            from NEXUS.execution_package_registry import read_execution_package

            package = read_execution_package(project_path=path, package_id=package_id)
            if not package:
                return _execution_package_error_result(
                    command=cmd,
                    reason="Execution package not found.",
                    project_name=proj_name,
                    project_path=path,
                    package_id=package_id,
                )
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=f"package_id={package_id}; decision_status={package.get('decision_status')}",
                payload={
                    "status": "ok",
                    "reason": "Execution package decision status loaded.",
                    "project_path": path,
                    "package_id": package_id,
                    "decision": {
                        "decision_status": package.get("decision_status"),
                        "decision_timestamp": package.get("decision_timestamp"),
                        "decision_actor": package.get("decision_actor"),
                        "decision_notes": package.get("decision_notes"),
                        "decision_id": package.get("decision_id"),
                    },
                },
            )
        except Exception as e:
            return _execution_package_error_result(
                command=cmd,
                reason=str(e),
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )

    if cmd == "execution_package_eligibility_check":
        package_id = str(kwargs.get("execution_package_id") or "").strip() or None
        eligibility_checked_by = str(kwargs.get("eligibility_checked_by") or "").strip()
        if not path:
            return _execution_package_error_result(
                command=cmd,
                reason="Project path or project_name required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if not package_id:
            return _execution_package_error_result(
                command=cmd,
                reason="execution_package_id required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if not eligibility_checked_by:
            return _execution_package_error_result(
                command=cmd,
                reason="eligibility_checked_by required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        try:
            from NEXUS.execution_package_registry import record_execution_package_eligibility_safe

            result = record_execution_package_eligibility_safe(
                project_path=path,
                package_id=package_id,
                eligibility_checked_by=eligibility_checked_by,
            )
            if result.get("status") != "ok":
                return _execution_package_error_result(
                    command=cmd,
                    reason=str(result.get("reason") or "Failed to record execution package eligibility."),
                    project_name=proj_name,
                    project_path=path,
                    package_id=package_id,
                )
            package = result.get("package") or {}
            eligibility = {
                "eligibility_status": package.get("eligibility_status"),
                "eligibility_timestamp": package.get("eligibility_timestamp"),
                "eligibility_reason": package.get("eligibility_reason") or {"code": "", "message": ""},
                "eligibility_checked_by": package.get("eligibility_checked_by"),
                "eligibility_check_id": package.get("eligibility_check_id"),
            }
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=f"package_id={package_id}; eligibility_status={eligibility.get('eligibility_status')}",
                payload={
                    "status": "ok",
                    "reason": "Execution package eligibility recorded.",
                    "project_path": path,
                    "package_id": package_id,
                    "eligibility": eligibility,
                },
            )
        except Exception as e:
            return _execution_package_error_result(
                command=cmd,
                reason=str(e),
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )

    if cmd == "execution_package_eligibility_status":
        package_id = str(kwargs.get("execution_package_id") or "").strip() or None
        if not path:
            return _execution_package_error_result(
                command=cmd,
                reason="Project path or project_name required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if not package_id:
            return _execution_package_error_result(
                command=cmd,
                reason="execution_package_id required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        try:
            from NEXUS.execution_package_registry import read_execution_package

            package = read_execution_package(project_path=path, package_id=package_id)
            if not package:
                return _execution_package_error_result(
                    command=cmd,
                    reason="Execution package not found.",
                    project_name=proj_name,
                    project_path=path,
                    package_id=package_id,
                )
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=f"package_id={package_id}; eligibility_status={package.get('eligibility_status')}",
                payload={
                    "status": "ok",
                    "reason": "Execution package eligibility status loaded.",
                    "project_path": path,
                    "package_id": package_id,
                    "eligibility": {
                        "eligibility_status": package.get("eligibility_status"),
                        "eligibility_timestamp": package.get("eligibility_timestamp"),
                        "eligibility_reason": package.get("eligibility_reason") or {"code": "", "message": ""},
                        "eligibility_checked_by": package.get("eligibility_checked_by"),
                        "eligibility_check_id": package.get("eligibility_check_id"),
                    },
                },
            )
        except Exception as e:
            return _execution_package_error_result(
                command=cmd,
                reason=str(e),
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )

    if cmd == "execution_package_release_request":
        package_id = str(kwargs.get("execution_package_id") or "").strip() or None
        release_actor = str(kwargs.get("release_actor") or "").strip()
        release_notes = str(kwargs.get("release_notes") or "")
        if not path:
            return _execution_package_error_result(
                command=cmd,
                reason="Project path or project_name required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if not package_id:
            return _execution_package_error_result(
                command=cmd,
                reason="execution_package_id required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if not release_actor:
            return _execution_package_error_result(
                command=cmd,
                reason="release_actor required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        try:
            from NEXUS.execution_package_registry import record_execution_package_release_safe

            result = record_execution_package_release_safe(
                project_path=path,
                package_id=package_id,
                release_actor=release_actor,
                release_notes=release_notes,
            )
            if result.get("status") != "ok":
                return _execution_package_error_result(
                    command=cmd,
                    reason=str(result.get("reason") or "Failed to record execution package release."),
                    project_name=proj_name,
                    project_path=path,
                    package_id=package_id,
                )
            package = result.get("package") or {}
            release = {
                "release_status": package.get("release_status"),
                "release_timestamp": package.get("release_timestamp"),
                "release_actor": package.get("release_actor"),
                "release_notes": package.get("release_notes"),
                "release_id": package.get("release_id"),
                "release_reason": package.get("release_reason") or {"code": "", "message": ""},
                "release_version": package.get("release_version"),
            }
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=f"package_id={package_id}; release_status={release.get('release_status')}",
                payload={
                    "status": "ok",
                    "reason": "Execution package release recorded.",
                    "project_path": path,
                    "package_id": package_id,
                    "release": release,
                },
            )
        except Exception as e:
            return _execution_package_error_result(
                command=cmd,
                reason=str(e),
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )

    if cmd == "execution_package_release_status":
        package_id = str(kwargs.get("execution_package_id") or "").strip() or None
        if not path:
            return _execution_package_error_result(
                command=cmd,
                reason="Project path or project_name required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if not package_id:
            return _execution_package_error_result(
                command=cmd,
                reason="execution_package_id required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        try:
            from NEXUS.execution_package_registry import read_execution_package

            package = read_execution_package(project_path=path, package_id=package_id)
            if not package:
                return _execution_package_error_result(
                    command=cmd,
                    reason="Execution package not found.",
                    project_name=proj_name,
                    project_path=path,
                    package_id=package_id,
                )
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=f"package_id={package_id}; release_status={package.get('release_status')}",
                payload={
                    "status": "ok",
                    "reason": "Execution package release status loaded.",
                    "project_path": path,
                    "package_id": package_id,
                    "release": {
                        "release_status": package.get("release_status"),
                        "release_timestamp": package.get("release_timestamp"),
                        "release_actor": package.get("release_actor"),
                        "release_notes": package.get("release_notes"),
                        "release_id": package.get("release_id"),
                        "release_reason": package.get("release_reason") or {"code": "", "message": ""},
                        "release_version": package.get("release_version"),
                    },
                },
            )
        except Exception as e:
            return _execution_package_error_result(
                command=cmd,
                reason=str(e),
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )

    if cmd == "execution_package_handoff_request":
        package_id = str(kwargs.get("execution_package_id") or "").strip() or None
        handoff_actor = str(kwargs.get("handoff_actor") or "").strip()
        executor_target_id = str(kwargs.get("executor_target_id") or "").strip()
        handoff_notes = str(kwargs.get("handoff_notes") or "")
        if not path:
            return _execution_package_error_result(
                command=cmd,
                reason="Project path or project_name required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if not package_id:
            return _execution_package_error_result(
                command=cmd,
                reason="execution_package_id required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if not executor_target_id:
            return _execution_package_error_result(
                command=cmd,
                reason="executor_target_id required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if not handoff_actor:
            return _execution_package_error_result(
                command=cmd,
                reason="handoff_actor required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        try:
            from NEXUS.execution_package_registry import record_execution_package_handoff_safe

            result = record_execution_package_handoff_safe(
                project_path=path,
                package_id=package_id,
                handoff_actor=handoff_actor,
                executor_target_id=executor_target_id,
                handoff_notes=handoff_notes,
            )
            if result.get("status") != "ok":
                return _execution_package_error_result(
                    command=cmd,
                    reason=str(result.get("reason") or "Failed to record execution package handoff."),
                    project_name=proj_name,
                    project_path=path,
                    package_id=package_id,
                )
            package = result.get("package") or {}
            handoff = {
                "handoff_status": package.get("handoff_status"),
                "handoff_timestamp": package.get("handoff_timestamp"),
                "handoff_actor": package.get("handoff_actor"),
                "handoff_notes": package.get("handoff_notes"),
                "handoff_id": package.get("handoff_id"),
                "handoff_reason": package.get("handoff_reason") or {"code": "", "message": ""},
                "handoff_version": package.get("handoff_version"),
                "handoff_executor_target_id": package.get("handoff_executor_target_id"),
                "handoff_executor_target_name": package.get("handoff_executor_target_name"),
                "handoff_aegis_result": package.get("handoff_aegis_result") or {},
            }
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=f"package_id={package_id}; handoff_status={handoff.get('handoff_status')}",
                payload={
                    "status": "ok",
                    "reason": "Execution package handoff recorded.",
                    "project_path": path,
                    "package_id": package_id,
                    "handoff": handoff,
                },
            )
        except Exception as e:
            return _execution_package_error_result(
                command=cmd,
                reason=str(e),
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )

    if cmd == "execution_package_handoff_status":
        package_id = str(kwargs.get("execution_package_id") or "").strip() or None
        if not path:
            return _execution_package_error_result(
                command=cmd,
                reason="Project path or project_name required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if not package_id:
            return _execution_package_error_result(
                command=cmd,
                reason="execution_package_id required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        try:
            from NEXUS.execution_package_registry import read_execution_package

            package = read_execution_package(project_path=path, package_id=package_id)
            if not package:
                return _execution_package_error_result(
                    command=cmd,
                    reason="Execution package not found.",
                    project_name=proj_name,
                    project_path=path,
                    package_id=package_id,
                )
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=f"package_id={package_id}; handoff_status={package.get('handoff_status')}",
                payload={
                    "status": "ok",
                    "reason": "Execution package handoff status loaded.",
                    "project_path": path,
                    "package_id": package_id,
                    "handoff": {
                        "handoff_status": package.get("handoff_status"),
                        "handoff_timestamp": package.get("handoff_timestamp"),
                        "handoff_actor": package.get("handoff_actor"),
                        "handoff_notes": package.get("handoff_notes"),
                        "handoff_id": package.get("handoff_id"),
                        "handoff_reason": package.get("handoff_reason") or {"code": "", "message": ""},
                        "handoff_version": package.get("handoff_version"),
                        "handoff_executor_target_id": package.get("handoff_executor_target_id"),
                        "handoff_executor_target_name": package.get("handoff_executor_target_name"),
                        "handoff_aegis_result": package.get("handoff_aegis_result") or {},
                    },
                },
            )
        except Exception as e:
            return _execution_package_error_result(
                command=cmd,
                reason=str(e),
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )

    if cmd == "execution_package_execute_request":
        package_id = str(kwargs.get("execution_package_id") or "").strip() or None
        execution_actor = str(kwargs.get("execution_actor") or "").strip()
        if not path:
            return _execution_package_error_result(
                command=cmd,
                reason="Project path or project_name required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if not package_id:
            return _execution_package_error_result(
                command=cmd,
                reason="execution_package_id required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if not execution_actor:
            return _execution_package_error_result(
                command=cmd,
                reason="execution_actor required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        try:
            from NEXUS.execution_package_registry import record_execution_package_execution_safe

            result = record_execution_package_execution_safe(
                project_path=path,
                package_id=package_id,
                execution_actor=execution_actor,
            )
            if result.get("status") == "denied":
                package = result.get("package") or {}
                execution = {
                    "execution_status": package.get("execution_status"),
                    "execution_timestamp": package.get("execution_timestamp"),
                    "execution_actor": package.get("execution_actor"),
                    "execution_id": package.get("execution_id"),
                    "execution_reason": package.get("execution_reason") or {"code": "", "message": ""},
                    "execution_receipt": package.get("execution_receipt") or {},
                    "execution_version": package.get("execution_version"),
                    "execution_executor_target_id": package.get("execution_executor_target_id"),
                    "execution_executor_target_name": package.get("execution_executor_target_name"),
                    "execution_executor_backend_id": package.get("execution_executor_backend_id"),
                    "execution_aegis_result": package.get("execution_aegis_result") or {},
                    "execution_started_at": package.get("execution_started_at"),
                    "execution_finished_at": package.get("execution_finished_at"),
                    "rollback_status": package.get("rollback_status"),
                    "rollback_timestamp": package.get("rollback_timestamp"),
                    "rollback_reason": package.get("rollback_reason") or {"code": "", "message": ""},
                    "retry_policy": package.get("retry_policy") or {},
                    "idempotency": package.get("idempotency") or {},
                    "failure_summary": package.get("failure_summary") or {},
                    "recovery_summary": package.get("recovery_summary") or {},
                    "rollback_repair": package.get("rollback_repair") or {},
                    "integrity_verification": package.get("integrity_verification") or {},
                }
                return _result(
                    command=cmd,
                    status="blocked",
                    project_name=proj_name,
                    summary=f"package_id={package_id}; execution_status={execution.get('execution_status')}; authority=denied",
                    payload={
                        "status": "blocked",
                        "reason": str(result.get("reason") or "Execution authority denied."),
                        "project_path": path,
                        "package_id": package_id,
                        "execution": execution,
                        "authority_denial": ((package.get("metadata") or {}).get("authority_denials") or {}).get("execution") or {},
                    },
                )
            if result.get("status") != "ok":
                return _execution_package_error_result(
                    command=cmd,
                    reason=str(result.get("reason") or "Failed to record execution package execution."),
                    project_name=proj_name,
                    project_path=path,
                    package_id=package_id,
                )
            package = result.get("package") or {}
            execution = {
                "execution_status": package.get("execution_status"),
                "execution_timestamp": package.get("execution_timestamp"),
                "execution_actor": package.get("execution_actor"),
                "execution_id": package.get("execution_id"),
                "execution_reason": package.get("execution_reason") or {"code": "", "message": ""},
                "execution_receipt": package.get("execution_receipt") or {},
                "execution_version": package.get("execution_version"),
                "execution_executor_target_id": package.get("execution_executor_target_id"),
                "execution_executor_target_name": package.get("execution_executor_target_name"),
                "execution_executor_backend_id": package.get("execution_executor_backend_id"),
                "execution_aegis_result": package.get("execution_aegis_result") or {},
                "execution_started_at": package.get("execution_started_at"),
                "execution_finished_at": package.get("execution_finished_at"),
                "rollback_status": package.get("rollback_status"),
                "rollback_timestamp": package.get("rollback_timestamp"),
                "rollback_reason": package.get("rollback_reason") or {"code": "", "message": ""},
                "retry_policy": package.get("retry_policy") or {},
                "idempotency": package.get("idempotency") or {},
                "failure_summary": package.get("failure_summary") or {},
                "recovery_summary": package.get("recovery_summary") or {},
                "rollback_repair": package.get("rollback_repair") or {},
                "integrity_verification": package.get("integrity_verification") or {},
            }
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=f"package_id={package_id}; execution_status={execution.get('execution_status')}",
                payload={
                    "status": "ok",
                    "reason": "Execution package execution recorded.",
                    "project_path": path,
                    "package_id": package_id,
                    "execution": execution,
                },
            )
        except Exception as e:
            return _execution_package_error_result(
                command=cmd,
                reason=str(e),
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )

    if cmd == "execution_package_execute_status":
        package_id = str(kwargs.get("execution_package_id") or "").strip() or None
        if not path:
            return _execution_package_error_result(
                command=cmd,
                reason="Project path or project_name required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if not package_id:
            return _execution_package_error_result(
                command=cmd,
                reason="execution_package_id required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        try:
            from NEXUS.execution_package_registry import read_execution_package

            package = read_execution_package(project_path=path, package_id=package_id)
            if not package:
                return _execution_package_error_result(
                    command=cmd,
                    reason="Execution package not found.",
                    project_name=proj_name,
                    project_path=path,
                    package_id=package_id,
                )
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=f"package_id={package_id}; execution_status={package.get('execution_status')}",
                payload={
                    "status": "ok",
                    "reason": "Execution package execution status loaded.",
                    "project_path": path,
                    "package_id": package_id,
                    "execution": {
                        "execution_status": package.get("execution_status"),
                        "execution_timestamp": package.get("execution_timestamp"),
                        "execution_actor": package.get("execution_actor"),
                        "execution_id": package.get("execution_id"),
                        "execution_reason": package.get("execution_reason") or {"code": "", "message": ""},
                        "execution_receipt": package.get("execution_receipt") or {},
                        "execution_version": package.get("execution_version"),
                        "execution_executor_target_id": package.get("execution_executor_target_id"),
                        "execution_executor_target_name": package.get("execution_executor_target_name"),
                        "execution_aegis_result": package.get("execution_aegis_result") or {},
                        "execution_started_at": package.get("execution_started_at"),
                        "execution_finished_at": package.get("execution_finished_at"),
                        "rollback_status": package.get("rollback_status"),
                        "rollback_timestamp": package.get("rollback_timestamp"),
                        "rollback_reason": package.get("rollback_reason") or {"code": "", "message": ""},
                        "retry_policy": package.get("retry_policy") or {},
                        "idempotency": package.get("idempotency") or {},
                        "failure_summary": package.get("failure_summary") or {},
                        "recovery_summary": package.get("recovery_summary") or {},
                        "rollback_repair": package.get("rollback_repair") or {},
                        "integrity_verification": package.get("integrity_verification") or {},
                    },
                },
            )
        except Exception as e:
            return _execution_package_error_result(
                command=cmd,
                reason=str(e),
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )

    if cmd == "execution_package_evaluate":
        package_id = str(kwargs.get("execution_package_id") or "").strip() or None
        evaluation_actor = str(kwargs.get("evaluation_actor") or "").strip()
        if not path:
            return _execution_package_error_result(
                command=cmd,
                reason="Project path or project_name required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if not package_id:
            return _execution_package_error_result(
                command=cmd,
                reason="execution_package_id required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if not evaluation_actor:
            return _execution_package_error_result(
                command=cmd,
                reason="evaluation_actor required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        try:
            from NEXUS.execution_package_registry import record_execution_package_evaluation_safe

            result = record_execution_package_evaluation_safe(
                project_path=path,
                package_id=package_id,
                evaluation_actor=evaluation_actor,
            )
            if result.get("status") == "denied":
                package = result.get("package") or {}
                evaluation = _build_execution_package_evaluation(package)
                return _result(
                    command=cmd,
                    status="blocked",
                    project_name=proj_name,
                    summary=f"package_id={package_id}; evaluation_status={evaluation.get('evaluation_status')}; authority=denied",
                    payload={
                        "status": "blocked",
                        "reason": str(result.get("reason") or "Evaluation authority denied."),
                        "project_path": path,
                        "package_id": package_id,
                        "evaluation": evaluation,
                        "authority_denial": ((package.get("metadata") or {}).get("authority_denials") or {}).get("evaluation") or {},
                    },
                )
            if result.get("status") != "ok":
                return _execution_package_error_result(
                    command=cmd,
                    reason=str(result.get("reason") or "Failed to record execution package evaluation."),
                    project_name=proj_name,
                    project_path=path,
                    package_id=package_id,
                )
            package = result.get("package") or {}
            evaluation = _build_execution_package_evaluation(package)
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=f"package_id={package_id}; evaluation_status={evaluation.get('evaluation_status')}",
                payload={
                    "status": "ok",
                    "reason": "Execution package evaluation recorded.",
                    "project_path": path,
                    "package_id": package_id,
                    "evaluation": evaluation,
                },
            )
        except Exception as e:
            return _execution_package_error_result(
                command=cmd,
                reason=str(e),
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )

    if cmd == "execution_package_evaluation_status":
        package_id = str(kwargs.get("execution_package_id") or "").strip() or None
        if not path:
            return _execution_package_error_result(
                command=cmd,
                reason="Project path or project_name required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if not package_id:
            return _execution_package_error_result(
                command=cmd,
                reason="execution_package_id required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        try:
            from NEXUS.execution_package_registry import read_execution_package

            package = read_execution_package(project_path=path, package_id=package_id)
            if not package:
                return _execution_package_error_result(
                    command=cmd,
                    reason="Execution package not found.",
                    project_name=proj_name,
                    project_path=path,
                    package_id=package_id,
                )
            evaluation = _build_execution_package_evaluation(package)
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=f"package_id={package_id}; evaluation_status={evaluation.get('evaluation_status')}",
                payload={
                    "status": "ok",
                    "reason": "Execution package evaluation status loaded.",
                    "project_path": path,
                    "package_id": package_id,
                    "evaluation": evaluation,
                },
            )
        except Exception as e:
            return _execution_package_error_result(
                command=cmd,
                reason=str(e),
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )

    if cmd == "execution_package_local_analysis":
        package_id = str(kwargs.get("execution_package_id") or "").strip() or None
        analysis_actor = str(kwargs.get("analysis_actor") or "").strip() or "nemoclaw"
        if not path:
            return _execution_package_error_result(
                command=cmd,
                reason="Project path or project_name required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if not package_id:
            return _execution_package_error_result(
                command=cmd,
                reason="execution_package_id required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        try:
            from NEXUS.execution_package_registry import record_execution_package_local_analysis_safe

            result = record_execution_package_local_analysis_safe(
                project_path=path,
                package_id=package_id,
                analysis_actor=analysis_actor,
            )
            if result.get("status") == "denied":
                package = result.get("package") or {}
                local_analysis = _build_execution_package_local_analysis(package)
                return _result(
                    command=cmd,
                    status="blocked",
                    project_name=proj_name,
                    summary=f"package_id={package_id}; local_analysis_status={local_analysis.get('local_analysis_status')}; authority=denied",
                    payload={
                        "status": "blocked",
                        "reason": str(result.get("reason") or "Local analysis authority denied."),
                        "project_path": path,
                        "package_id": package_id,
                        "local_analysis": local_analysis,
                        "authority_denial": ((package.get("metadata") or {}).get("authority_denials") or {}).get("local_analysis") or {},
                    },
                )
            if result.get("status") != "ok":
                return _execution_package_error_result(
                    command=cmd,
                    reason=str(result.get("reason") or "Failed to record execution package local analysis."),
                    project_name=proj_name,
                    project_path=path,
                    package_id=package_id,
                )
            package = result.get("package") or {}
            local_analysis = _build_execution_package_local_analysis(package)
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=f"package_id={package_id}; local_analysis_status={local_analysis.get('local_analysis_status')}",
                payload={
                    "status": "ok",
                    "reason": "Execution package local analysis recorded.",
                    "project_path": path,
                    "package_id": package_id,
                    "local_analysis": local_analysis,
                },
            )
        except Exception as e:
            return _execution_package_error_result(
                command=cmd,
                reason=str(e),
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )

    if cmd == "execution_package_local_analysis_status":
        package_id = str(kwargs.get("execution_package_id") or "").strip() or None
        if not path:
            return _execution_package_error_result(
                command=cmd,
                reason="Project path or project_name required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        if not package_id:
            return _execution_package_error_result(
                command=cmd,
                reason="execution_package_id required.",
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )
        try:
            from NEXUS.execution_package_registry import read_execution_package

            package = read_execution_package(project_path=path, package_id=package_id)
            if not package:
                return _execution_package_error_result(
                    command=cmd,
                    reason="Execution package not found.",
                    project_name=proj_name,
                    project_path=path,
                    package_id=package_id,
                )
            local_analysis = _build_execution_package_local_analysis(package)
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=f"package_id={package_id}; local_analysis_status={local_analysis.get('local_analysis_status')}",
                payload={
                    "status": "ok",
                    "reason": "Execution package local analysis status loaded.",
                    "project_path": path,
                    "package_id": package_id,
                    "local_analysis": local_analysis,
                },
            )
        except Exception as e:
            return _execution_package_error_result(
                command=cmd,
                reason=str(e),
                project_name=proj_name,
                project_path=path,
                package_id=package_id,
            )

    if cmd == "automation_status":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(
                    command=cmd,
                    status="error",
                    project_name=proj_name,
                    summary=loaded.get("load_error", "Failed to load state."),
                    payload=loaded,
                )
            status_val = loaded.get("automation_status")
            ar = loaded.get("automation_result") or {}
            payload = {
                "automation_status": status_val,
                "recommended_action": ar.get("recommended_action"),
                "human_review_required": ar.get("human_review_required"),
                "reason": ar.get("reason"),
            }
            summary_line = f"automation_status={status_val}; action={payload.get('recommended_action')}"
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=summary_line,
                payload=payload,
            )
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "agent_status":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(
                    command=cmd,
                    status="error",
                    project_name=proj_name,
                    summary=loaded.get("load_error", "Failed to load state."),
                    payload=loaded,
                )
            sel = loaded.get("agent_selection_summary") or {}
            payload = {
                "selected_agent": sel.get("selected_agent"),
                "agent_role": sel.get("agent_role"),
                "selection_reason": sel.get("selection_reason"),
                "confidence": sel.get("confidence"),
                "specialties": sel.get("specialties") or [],
            }
            summary_line = f"agent={payload.get('selected_agent')}; role={payload.get('agent_role')}"
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=summary_line,
                payload=payload,
            )
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "governance_status":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(
                    command=cmd,
                    status="error",
                    project_name=proj_name,
                    summary=loaded.get("load_error", "Failed to load state."),
                    payload=loaded,
                )
            gr = loaded.get("governance_result") or {}
            payload = {
                "governance_status": loaded.get("governance_status") or gr.get("governance_status"),
                "risk_level": gr.get("risk_level"),
                "approval_required": gr.get("approval_required"),
                "review_required": gr.get("review_required"),
                "blocked": gr.get("blocked"),
                "decision_reason": gr.get("decision_reason"),
            }
            summary_line = f"governance={payload.get('governance_status')}; risk={payload.get('risk_level')}"
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=summary_line,
                payload=payload,
            )
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "project_lifecycle":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(
                    command=cmd,
                    status="error",
                    project_name=proj_name,
                    summary=loaded.get("load_error", "Failed to load state."),
                    payload=loaded,
                )
            plr = loaded.get("project_lifecycle_result") or {}
            payload = {
                "lifecycle_status": loaded.get("project_lifecycle_status") or plr.get("lifecycle_status"),
                "lifecycle_stage": plr.get("lifecycle_stage"),
                "recommended_lifecycle_action": plr.get("recommended_lifecycle_action"),
                "is_active": plr.get("is_active"),
                "is_blocked": plr.get("is_blocked"),
                "is_archived": plr.get("is_archived"),
                "reason": plr.get("reason"),
            }
            summary_line = f"lifecycle={payload.get('lifecycle_status')}; stage={payload.get('lifecycle_stage')}"
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=summary_line,
                payload=payload,
            )
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "enforcement_status":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(
                    command=cmd,
                    status="error",
                    project_name=proj_name,
                    summary=loaded.get("load_error", "Failed to load state."),
                    payload=loaded,
                )
            er = loaded.get("enforcement_result") or {}
            payload = {
                "enforcement_status": loaded.get("enforcement_status") or er.get("enforcement_status"),
                "workflow_action": er.get("workflow_action"),
                "approval_gate": er.get("approval_gate"),
                "manual_review_gate": er.get("manual_review_gate"),
                "downstream_blocked": er.get("downstream_blocked"),
                "reason": er.get("reason"),
                "enforcement_tags": er.get("enforcement_tags") or [],
            }
            summary_line = f"enforcement={payload.get('enforcement_status')}; workflow_action={payload.get('workflow_action')}"
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=summary_line,
                payload=payload,
            )
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "review_queue":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(
                    command=cmd,
                    status="error",
                    project_name=proj_name,
                    summary=loaded.get("load_error", "Failed to load state."),
                    payload=loaded,
                )
            qe = loaded.get("review_queue_entry") or {}
            payload = {
                "queue_status": qe.get("queue_status"),
                "queue_type": qe.get("queue_type"),
                "queue_reason": qe.get("queue_reason"),
                "resume_action": qe.get("resume_action"),
                "resume_condition": qe.get("resume_condition"),
                "requires_human_action": qe.get("requires_human_action"),
            }
            summary_line = f"queue_status={payload.get('queue_status')}; queue_type={payload.get('queue_type')}"
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=summary_line,
                payload=payload,
            )
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "resume_status":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(
                    command=cmd,
                    status="error",
                    project_name=proj_name,
                    summary=loaded.get("load_error", "Failed to load state."),
                    payload=loaded,
                )
            rr = loaded.get("resume_result") or {}
            payload = {
                "resume_status": loaded.get("resume_status") or rr.get("resume_status"),
                "resume_type": rr.get("resume_type"),
                "resume_reason": rr.get("resume_reason"),
                "resume_action": rr.get("resume_action"),
                "requires_human_action": rr.get("requires_human_action"),
            }
            summary_line = f"resume_status={payload.get('resume_status')}; resume_type={payload.get('resume_type')}"
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=summary_line,
                payload=payload,
            )
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "heartbeat_status":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(
                    command=cmd,
                    status="error",
                    project_name=proj_name,
                    summary=loaded.get("load_error", "Failed to load state."),
                    payload=loaded,
                )
            hr = loaded.get("heartbeat_result") or {}
            payload = {
                "heartbeat_status": loaded.get("heartbeat_status") or hr.get("heartbeat_status"),
                "heartbeat_action": hr.get("heartbeat_action"),
                "heartbeat_reason": hr.get("heartbeat_reason"),
                "next_cycle_allowed": hr.get("next_cycle_allowed"),
                "queue_detected": hr.get("queue_detected"),
                "resume_detected": hr.get("resume_detected"),
            }
            summary_line = f"heartbeat_status={payload.get('heartbeat_status')}; next_cycle_allowed={payload.get('next_cycle_allowed')}"
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=summary_line,
                payload=payload,
            )
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "scheduler_status":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(
                    command=cmd,
                    status="error",
                    project_name=proj_name,
                    summary=loaded.get("load_error", "Failed to load state."),
                    payload=loaded,
                )
            sr = loaded.get("scheduler_result") or {}
            payload = {
                "scheduler_status": loaded.get("scheduler_status") or sr.get("scheduler_status"),
                "scheduler_action": sr.get("scheduler_action"),
                "scheduler_reason": sr.get("scheduler_reason"),
                "next_cycle_permitted": sr.get("next_cycle_permitted"),
                "cycle_limit_reached": sr.get("cycle_limit_reached"),
            }
            summary_line = f"scheduler_status={payload.get('scheduler_status')}; next_cycle_permitted={payload.get('next_cycle_permitted')}"
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=summary_line,
                payload=payload,
            )
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "studio_coordination":
        try:
            from NEXUS.studio_coordinator import build_studio_coordination_summary_safe
            states_by_project: dict[str, dict] = {}
            for key in PROJECTS:
                p = PROJECTS[key].get("path")
                if p:
                    states_by_project[key] = load_project_state(p)
            summary = build_studio_coordination_summary_safe(states_by_project)
            summary_line = f"coordination={summary.get('coordination_status')}; priority={summary.get('priority_project')}"
            return _result(
                command=cmd,
                status="ok",
                project_name=None,
                summary=summary_line,
                payload=summary,
            )
        except Exception as e:
            return _result(command=cmd, status="error", summary=str(e), payload={"error": str(e)})

    if cmd == "complete_review":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            from NEXUS.review_completion import build_completion_result_safe
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(
                    command=cmd,
                    status="error",
                    project_name=proj_name,
                    summary=loaded.get("load_error", "Failed to load state."),
                    payload=loaded,
                )
            completion_type = (kwargs.get("completion_type") or "manual_review").strip().lower()
            result = build_completion_result_safe(
                active_project=loaded.get("active_project"),
                run_id=loaded.get("run_id"),
                review_queue_entry=loaded.get("review_queue_entry"),
                completion_type=completion_type,
                completion_requested=True,
                enforcement_result=loaded.get("enforcement_result"),
                resume_result=loaded.get("resume_result"),
            )
            if result.get("completion_recorded"):
                cleared_entry = {
                    "queue_status": "cleared",
                    "queue_type": None,
                    "queue_reason": "Cleared after completion.",
                    "resume_action": None,
                    "resume_condition": None,
                    "active_project": loaded.get("active_project") or "",
                    "run_id": loaded.get("run_id") or "",
                    "requires_human_action": False,
                }
                update_project_state_fields(path, completion_result=result, review_queue_entry=cleared_entry)
            payload = {
                "completion_status": result.get("completion_status"),
                "completion_type": result.get("completion_type"),
                "queue_cleared": result.get("queue_cleared"),
                "resume_unlocked": result.get("resume_unlocked"),
                "completion_recorded": result.get("completion_recorded"),
            }
            summary_line = f"completion_status={result.get('completion_status')}; queue_cleared={result.get('queue_cleared')}"
            log_system_event(
                project=proj_name,
                subsystem="command_surface",
                action="complete_review",
                status="ok",
                reason=summary_line,
            )
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=payload)
        except Exception as e:
            log_system_event(
                project=proj_name,
                subsystem="command_surface",
                action="complete_review",
                status="error",
                reason=str(e),
            )
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "complete_approval":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            from NEXUS.review_completion import build_completion_result_safe
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(
                    command=cmd,
                    status="error",
                    project_name=proj_name,
                    summary=loaded.get("load_error", "Failed to load state."),
                    payload=loaded,
                )
            result = build_completion_result_safe(
                active_project=loaded.get("active_project"),
                run_id=loaded.get("run_id"),
                review_queue_entry=loaded.get("review_queue_entry"),
                completion_type="approval",
                completion_requested=True,
                enforcement_result=loaded.get("enforcement_result"),
                resume_result=loaded.get("resume_result"),
            )
            if result.get("completion_recorded"):
                cleared_entry = {
                    "queue_status": "cleared",
                    "queue_type": None,
                    "queue_reason": "Cleared after approval.",
                    "resume_action": None,
                    "resume_condition": None,
                    "active_project": loaded.get("active_project") or "",
                    "run_id": loaded.get("run_id") or "",
                    "requires_human_action": False,
                }
                update_project_state_fields(path, completion_result=result, review_queue_entry=cleared_entry)
            payload = {
                "completion_status": result.get("completion_status"),
                "completion_type": result.get("completion_type"),
                "queue_cleared": result.get("queue_cleared"),
                "resume_unlocked": result.get("resume_unlocked"),
                "completion_recorded": result.get("completion_recorded"),
            }
            summary_line = f"completion_status={result.get('completion_status')}; queue_cleared={result.get('queue_cleared')}"
            log_system_event(
                project=proj_name,
                subsystem="command_surface",
                action="complete_approval",
                status="ok",
                reason=summary_line,
            )
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=payload)
        except Exception as e:
            log_system_event(
                project=proj_name,
                subsystem="command_surface",
                action="complete_approval",
                status="error",
                reason=str(e),
            )
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "recovery_status":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(
                    command=cmd,
                    status="error",
                    project_name=proj_name,
                    summary=loaded.get("load_error", "Failed to load state."),
                    payload=loaded,
                )
            rec = loaded.get("recovery_result") or {}
            payload = {
                "recovery_status": loaded.get("recovery_status") or rec.get("recovery_status"),
                "recovery_action": rec.get("recovery_action"),
                "recovery_reason": rec.get("recovery_reason"),
                "retry_permitted": rec.get("retry_permitted"),
                "repair_required": rec.get("repair_required"),
                "retry_count_exceeded": rec.get("retry_count_exceeded"),
            }
            summary_line = f"recovery_status={payload.get('recovery_status')}; retry_permitted={payload.get('retry_permitted')}"
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=summary_line,
                payload=payload,
            )
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "reexecution_status":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(
                    command=cmd,
                    status="error",
                    project_name=proj_name,
                    summary=loaded.get("load_error", "Failed to load state."),
                    payload=loaded,
                )
            rex = loaded.get("reexecution_result") or {}
            payload = {
                "reexecution_status": loaded.get("reexecution_status") or rex.get("reexecution_status"),
                "reexecution_action": rex.get("reexecution_action"),
                "reexecution_reason": rex.get("reexecution_reason"),
                "target_project": rex.get("target_project"),
                "run_permitted": rex.get("run_permitted"),
                "bounded_execution": rex.get("bounded_execution"),
            }
            summary_line = f"reexecution_status={payload.get('reexecution_status')}; run_permitted={payload.get('run_permitted')}"
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=summary_line,
                payload=payload,
            )
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "studio_driver":
        try:
            from NEXUS.studio_coordinator import build_studio_coordination_summary_safe
            from NEXUS.studio_driver import build_studio_driver_result_safe
            states_by_project = {}
            for key in PROJECTS:
                p = PROJECTS[key].get("path")
                if p:
                    states_by_project[key] = load_project_state(p)
            coord = build_studio_coordination_summary_safe(states_by_project)
            driver = build_studio_driver_result_safe(
                studio_coordination_summary=coord,
                states_by_project=states_by_project,
            )
            summary_line = f"driver_status={driver.get('driver_status')}; target_project={driver.get('target_project')}"
            return _result(
                command=cmd,
                status="ok",
                project_name=None,
                summary=summary_line,
                payload=driver,
            )
        except Exception as e:
            return _result(command=cmd, status="error", summary=str(e), payload={"error": str(e)})

    if cmd == "launch_next_cycle":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            from NEXUS.autonomous_launcher import launch_project_cycle
            loaded = load_project_state(path)
            project_key = next((k for k in PROJECTS if PROJECTS[k].get("path") == path), None) or (str(proj_name or loaded.get("active_project") or "jarvis").strip().lower())
            if project_key not in PROJECTS:
                project_key = "jarvis"
            result = launch_project_cycle(project_path=path, project_name=project_key, project_state=loaded)
            summary_line = f"launch_status={result.get('launch_status')}; execution_started={result.get('execution_started')}"
            log_system_event(
                project=project_key,
                subsystem="command_surface",
                action="launch_next_cycle",
                status=result.get("launch_status") or "ok",
                reason=result.get("launch_reason") or summary_line,
            )
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=result)
        except Exception as e:
            log_system_event(
                project=proj_name,
                subsystem="command_surface",
                action="launch_next_cycle",
                status="error",
                reason=str(e),
            )
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "launch_studio_cycle":
        try:
            from NEXUS.autonomous_launcher import launch_studio_cycle
            result = launch_studio_cycle()
            summary_line = f"launch_status={result.get('launch_status')}; target_project={result.get('target_project')}; execution_started={result.get('execution_started')}"
            log_system_event(
                project=result.get("target_project"),
                subsystem="command_surface",
                action="launch_studio_cycle",
                status=result.get("launch_status") or "ok",
                reason=result.get("launch_reason") or summary_line,
            )
            return _result(command=cmd, status="ok", project_name=result.get("target_project"), summary=summary_line, payload=result)
        except Exception as e:
            log_system_event(
                project=None,
                subsystem="command_surface",
                action="launch_studio_cycle",
                status="error",
                reason=str(e),
            )
            return _result(command=cmd, status="error", summary=str(e), payload={"error": str(e)})

    if cmd == "launch_status":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(
                    command=cmd,
                    status="error",
                    project_name=proj_name,
                    summary=loaded.get("load_error", "Failed to load state."),
                    payload=loaded,
                )
            lr = loaded.get("launch_result") or {}
            payload = {
                "launch_status": loaded.get("launch_status") or lr.get("launch_status"),
                "launch_action": lr.get("launch_action"),
                "launch_reason": lr.get("launch_reason"),
                "target_project": lr.get("target_project"),
                "execution_started": lr.get("execution_started"),
                "bounded_execution": lr.get("bounded_execution"),
                "source": lr.get("source"),
            }
            summary_line = f"launch_status={payload.get('launch_status')}; execution_started={payload.get('execution_started')}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=payload)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "autonomous_cycle":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            from NEXUS.continuous_autonomy import run_project_autonomy
            loaded = load_project_state(path)
            project_key = next((k for k in PROJECTS if PROJECTS[k].get("path") == path), None) or (str(proj_name or loaded.get("active_project") or "jarvis").strip().lower())
            if project_key not in PROJECTS:
                project_key = "jarvis"
            result = run_project_autonomy(project_path=path, project_name=project_key, project_state=loaded)
            summary_line = f"autonomy_status={result.get('autonomy_status')}; autonomous_run_started={result.get('autonomous_run_started')}"
            log_system_event(
                project=project_key,
                subsystem="command_surface",
                action="autonomous_cycle",
                status=result.get("autonomy_status") or "ok",
                reason=result.get("autonomy_reason") or summary_line,
            )
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=result)
        except Exception as e:
            log_system_event(
                project=proj_name,
                subsystem="command_surface",
                action="autonomous_cycle",
                status="error",
                reason=str(e),
            )
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "autonomous_studio_cycle":
        try:
            from NEXUS.continuous_autonomy import run_studio_autonomy
            result = run_studio_autonomy()
            summary_line = f"autonomy_status={result.get('autonomy_status')}; target_project={result.get('target_project')}; autonomous_run_started={result.get('autonomous_run_started')}"
            log_system_event(
                project=result.get("target_project"),
                subsystem="command_surface",
                action="autonomous_studio_cycle",
                status=result.get("autonomy_status") or "ok",
                reason=result.get("autonomy_reason") or summary_line,
            )
            return _result(command=cmd, status="ok", project_name=result.get("target_project"), summary=summary_line, payload=result)
        except Exception as e:
            log_system_event(
                project=None,
                subsystem="command_surface",
                action="autonomous_studio_cycle",
                status="error",
                reason=str(e),
            )
            return _result(command=cmd, status="error", summary=str(e), payload={"error": str(e)})

    if cmd == "autonomy_status":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(
                    command=cmd,
                    status="error",
                    project_name=proj_name,
                    summary=loaded.get("load_error", "Failed to load state."),
                    payload=loaded,
                )
            ar = loaded.get("autonomy_result") or {}
            payload = {
                "autonomy_status": loaded.get("autonomy_status") or ar.get("autonomy_status") or "idle",
                "autonomy_action": ar.get("autonomy_action") or "none",
                "autonomy_reason": ar.get("autonomy_reason") or "",
                "target_project": ar.get("target_project") or (loaded.get("active_project") or proj_name or ""),
                "autonomous_run_started": bool(ar.get("autonomous_run_started", False)),
                "bounded_operation": bool(ar.get("bounded_operation", True)),
                "autonomy_mode": "bounded_multi_step",
                "last_bounded_run": None,
                "approval_blocked": False,
                "safety_blocked": False,
            }
            try:
                from NEXUS.autonomy_registry import read_autonomy_journal_tail
                tail = read_autonomy_journal_tail(project_path=path, n=1)
                if tail:
                    last = tail[-1]
                    payload["last_bounded_run"] = last
                    payload["approval_blocked"] = bool(last.get("approval_blocked"))
                    payload["safety_blocked"] = bool(last.get("safety_blocked"))
            except Exception:
                pass
            summary_line = f"autonomy_status={payload.get('autonomy_status')}; autonomous_run_started={payload.get('autonomous_run_started')}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=payload)
        except Exception as e:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary=str(e),
                payload={
                    "autonomy_status": "error",
                    "autonomy_action": "none",
                    "autonomy_reason": str(e),
                    "target_project": proj_name or "",
                    "autonomous_run_started": False,
                    "bounded_operation": True,
                    "autonomy_mode": "bounded_multi_step",
                    "last_bounded_run": None,
                    "approval_blocked": False,
                    "safety_blocked": False,
                    "error": str(e),
                },
            )

    if cmd == "autonomy_run":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            from NEXUS.bounded_autonomy_runner import run_bounded_autonomy
            loaded = load_project_state(path)
            project_key = next((k for k in PROJECTS if PROJECTS[k].get("path") == path), None) or (str(proj_name or loaded.get("active_project") or "jarvis").strip().lower())
            if project_key not in PROJECTS:
                project_key = "jarvis"
            max_steps = int(kwargs.get("max_steps") or 3)
            max_steps = max(1, min(10, max_steps))
            result = run_bounded_autonomy(project_path=path, project_name=project_key, max_steps=max_steps)
            summary_line = f"autonomy_status={result.get('autonomy_status')}; steps_attempted={result.get('steps_attempted')}; steps_completed={result.get('steps_completed')}; stop_reason={result.get('stop_reason')}"
            log_system_event(
                project=project_key,
                subsystem="command_surface",
                action="autonomy_run",
                status=result.get("autonomy_status") or "ok",
                reason=summary_line,
            )
            return _result(command=cmd, status="ok", project_name=project_key, summary=summary_line, payload=result)
        except Exception as e:
            log_system_event(
                project=proj_name,
                subsystem="command_surface",
                action="autonomy_run",
                status="error",
                reason=str(e),
            )
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary=str(e),
                payload={
                    "autonomy_id": "",
                    "run_id": "",
                    "project_name": proj_name or "",
                    "autonomy_status": "error",
                    "autonomy_mode": "bounded_multi_step",
                    "max_steps": 0,
                    "steps_attempted": 0,
                    "steps_completed": 0,
                    "stop_reason": "error",
                    "approval_blocked": False,
                    "safety_blocked": False,
                    "reached_limit": False,
                    "step_results": [],
                    "started_at": "",
                    "finished_at": "",
                    "error": str(e),
                },
            )

    if cmd == "autonomy_trace":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            from NEXUS.autonomy_registry import read_autonomy_journal_tail
            trace = read_autonomy_journal_tail(project_path=path, n=50)
            payload = {
                "trace_count": len(trace),
                "trace": trace,
                "project_name": proj_name or "",
            }
            summary_line = f"trace_count={len(trace)}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=payload)
        except Exception as e:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary=str(e),
                payload={
                    "trace_count": 0,
                    "trace": [],
                    "project_name": proj_name or "",
                    "error": str(e),
                },
            )

    if cmd == "persistent_kill_switch_status":
        try:
            from NEXUS.portfolio_autonomy_controls import read_portfolio_kill_switch, set_portfolio_kill_switch
            from NEXUS.portfolio_autonomy_trace import append_portfolio_trace_event_safe

            enabled_value = kwargs.get("enabled")
            if enabled_value is None and "set_to" in kwargs:
                enabled_value = kwargs.get("set_to")
            if enabled_value is None and "value" in kwargs:
                enabled_value = kwargs.get("value")
            changed = enabled_value is not None

            if changed:
                if isinstance(enabled_value, str):
                    enabled_flag = enabled_value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
                else:
                    enabled_flag = bool(enabled_value)
                reason = str(kwargs.get("reason") or ("Operator enabled persistent kill switch." if enabled_flag else "Operator disabled persistent kill switch.")).strip()
                changed_by = str(kwargs.get("changed_by") or kwargs.get("source") or "command_surface")
                scope = str(kwargs.get("scope") or "portfolio_autonomy")
                payload = set_portfolio_kill_switch(
                    enabled=enabled_flag,
                    reason=reason,
                    changed_by=changed_by,
                    source="command_surface.persistent_kill_switch_status",
                    scope=scope,
                )
                append_portfolio_trace_event_safe(
                    {
                        "event_type": "kill_switch_state_changed",
                        "reason": reason,
                        "decision_inputs": {"enabled": enabled_flag, "changed_by": changed_by, "scope": scope},
                        "resulting_action": "stop" if enabled_flag else "resume_eligible",
                        "visibility": "operator",
                        "source": "command_surface",
                    }
                )
                summary_line = f"enabled={payload.get('enabled')}; changed_by={payload.get('changed_by')}; scope={payload.get('scope')}"
            else:
                payload = read_portfolio_kill_switch()
                summary_line = f"enabled={payload.get('enabled')}; changed_at={payload.get('changed_at')}"
            return _result(command=cmd, status="ok", summary=summary_line, payload=payload)
        except Exception as e:
            return _result(command=cmd, status="error", summary=str(e), payload={"error": str(e)})

    if cmd == "portfolio_autonomy_trace":
        try:
            from NEXUS.portfolio_autonomy_trace import read_portfolio_trace_tail

            limit = max(1, min(int(kwargs.get("n") or n or 50), 200))
            event_type = str(kwargs.get("event_type") or "").strip()
            trace = read_portfolio_trace_tail(limit, event_type=event_type)
            payload = {"trace_count": len(trace), "trace": trace}
            return _result(command=cmd, status="ok", summary=f"trace_count={len(trace)}", payload=payload)
        except Exception as e:
            return _result(command=cmd, status="error", summary=str(e), payload={"trace_count": 0, "trace": [], "error": str(e)})

    if cmd in {"portfolio_autonomy_status", "portfolio_autonomy_revenue_priority"}:
        try:
            from NEXUS.portfolio_autonomy_controls import read_portfolio_kill_switch
            from NEXUS.project_routing import evaluate_project_selection

            states: dict[str, dict[str, Any]] = {}
            for key, config in PROJECTS.items():
                project_path = str((config or {}).get("path") or "").strip()
                if not project_path:
                    continue
                loaded = load_project_state(project_path)
                if isinstance(loaded, dict) and not loaded.get("load_error"):
                    states[key] = loaded
            selection = evaluate_project_selection(states_by_project=states)
            kill_switch = read_portfolio_kill_switch()
            if cmd == "portfolio_autonomy_revenue_priority":
                payload = {
                    "selected_project_id": selection.get("selected_project_id") or "",
                    "revenue_priority_summary": selection.get("revenue_priority_summary") or {},
                    "why_selected": selection.get("why_selected") or "",
                    "why_not_selected": selection.get("why_not_selected") or [],
                    "next_action": selection.get("next_action") or "",
                    "next_reason": selection.get("next_reason") or "",
                    "persistent_kill_switch": kill_switch,
                }
                summary_line = (
                    f"selected={payload.get('selected_project_id')}; "
                    f"ranked={len((payload.get('revenue_priority_summary') or {}).get('ranking') or [])}; "
                    f"kill_switch={kill_switch.get('enabled')}"
                )
                return _result(command=cmd, status="ok", summary=summary_line, payload=payload)

            payload = {
                "selection_status": selection.get("status") or "",
                "selected_project_id": selection.get("selected_project_id") or "",
                "selection_reason": selection.get("selection_reason") or "",
                "why_selected": selection.get("why_selected") or "",
                "why_not_selected": selection.get("why_not_selected") or [],
                "next_action": selection.get("next_action") or "",
                "next_reason": selection.get("next_reason") or "",
                "routing_outcome": selection.get("routing_outcome") or "",
                "priority_basis": selection.get("priority_basis") or "",
                "eligible_projects": selection.get("eligible_projects") or [],
                "blocked_projects": selection.get("blocked_projects") or [],
                "contention_detected": bool(selection.get("contention_detected")),
                "revenue_priority_summary": selection.get("revenue_priority_summary") or {},
                "persistent_kill_switch": kill_switch,
            }
            summary_line = (
                f"status={payload.get('selection_status')}; "
                f"selected={payload.get('selected_project_id')}; "
                f"kill_switch={kill_switch.get('enabled')}; "
                f"next_action={payload.get('next_action')}"
            )
            return _result(command=cmd, status="ok", summary=summary_line, payload=payload)
        except Exception as e:
            return _result(command=cmd, status="error", summary=str(e), payload={"error": str(e)})

    if cmd == "helix_status":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={
                    "helix_posture": "error",
                    "last_helix_run": None,
                    "pipeline_status": "error",
                    "approval_blocked": False,
                    "safety_blocked": False,
                    "requires_surgeon": False,
                    "error": "Project path or project_name required.",
                },
            )
        try:
            from NEXUS.helix_registry import read_helix_journal_tail
            tail = read_helix_journal_tail(project_path=path, n=1)
            payload = {
                "helix_posture": "idle",
                "last_helix_run": None,
                "pipeline_status": "idle",
                "approval_blocked": False,
                "safety_blocked": False,
                "requires_surgeon": False,
            }
            if tail:
                last = tail[-1]
                payload["last_helix_run"] = last
                payload["pipeline_status"] = last.get("pipeline_status") or "idle"
                payload["approval_blocked"] = bool(last.get("approval_blocked"))
                payload["safety_blocked"] = bool(last.get("safety_blocked"))
                payload["requires_surgeon"] = bool(last.get("requires_surgeon"))
                if last.get("approval_blocked"):
                    payload["helix_posture"] = "approval_blocked"
                elif last.get("safety_blocked"):
                    payload["helix_posture"] = "safety_blocked"
                elif last.get("pipeline_status") == "completed":
                    payload["helix_posture"] = "capable"
            summary_line = f"helix_posture={payload.get('helix_posture')}; pipeline_status={payload.get('pipeline_status')}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=payload)
        except Exception as e:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary=str(e),
                payload={
                    "helix_posture": "error",
                    "last_helix_run": None,
                    "pipeline_status": "error",
                    "approval_blocked": False,
                    "safety_blocked": False,
                    "requires_surgeon": False,
                    "error": str(e),
                },
            )

    if cmd == "helix_run":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={
                    "helix_id": "",
                    "pipeline_status": "error",
                    "stop_reason": "error",
                    "approval_blocked": False,
                    "safety_blocked": False,
                    "requires_surgeon": False,
                    "error": "Project path or project_name required.",
                },
            )
        try:
            from NEXUS.helix_pipeline import run_helix_pipeline
            loaded = load_project_state(path)
            project_key = next((k for k in PROJECTS if PROJECTS[k].get("path") == path), None) or (str(proj_name or loaded.get("active_project") or "jarvis").strip().lower())
            if project_key not in PROJECTS:
                project_key = "jarvis"
            requested_outcome = str(kwargs.get("requested_outcome") or kwargs.get("outcome") or "Engineering task")
            result = run_helix_pipeline(
                project_path=path,
                project_name=project_key,
                requested_outcome=requested_outcome,
            )
            summary_line = f"pipeline_status={result.get('pipeline_status')}; stop_reason={result.get('stop_reason')}; requires_surgeon={result.get('requires_surgeon')}"
            log_system_event(
                project=project_key,
                subsystem="command_surface",
                action="helix_run",
                status=result.get("pipeline_status") or "ok",
                reason=summary_line,
            )
            return _result(command=cmd, status="ok", project_name=project_key, summary=summary_line, payload=result)
        except Exception as e:
            log_system_event(
                project=proj_name,
                subsystem="command_surface",
                action="helix_run",
                status="error",
                reason=str(e),
            )
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary=str(e),
                payload={
                    "helix_id": "",
                    "pipeline_status": "error",
                    "stop_reason": "error",
                    "approval_blocked": False,
                    "safety_blocked": False,
                    "requires_surgeon": False,
                    "error": str(e),
                },
            )

    if cmd == "helix_trace":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={"trace_count": 0, "trace": [], "project_name": "", "error": "Project path or project_name required."},
            )
        try:
            from NEXUS.helix_registry import read_helix_journal_tail
            trace = read_helix_journal_tail(project_path=path, n=50)
            payload = {
                "trace_count": len(trace),
                "trace": trace,
                "project_name": proj_name or "",
            }
            summary_line = f"trace_count={len(trace)}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=payload)
        except Exception as e:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary=str(e),
                payload={"trace_count": 0, "trace": [], "project_name": proj_name or "", "error": str(e)},
            )

    if cmd == "guardrail_status":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(
                    command=cmd,
                    status="error",
                    project_name=proj_name,
                    summary=loaded.get("load_error", "Failed to load state."),
                    payload=loaded,
                )
            gr = loaded.get("guardrail_result") or {}
            if not gr or (loaded.get("guardrail_status") is None and gr.get("guardrail_status") is None):
                # Compute on-demand for stable output (and persist for later visibility).
                try:
                    from NEXUS.production_guardrails import evaluate_guardrails_safe
                    computed = evaluate_guardrails_safe(
                        autonomous_launch=False,
                        project_state=loaded,
                        review_queue_entry=loaded.get("review_queue_entry"),
                        recovery_result=loaded.get("recovery_result"),
                        reexecution_result=loaded.get("reexecution_result"),
                        studio_driver_result=None,
                        target_project=loaded.get("active_project") or proj_name,
                        states_by_project={},
                        execution_attempted=False,
                    )
                    update_project_state_fields(
                        path,
                        guardrail_status=computed.get("guardrail_status"),
                        guardrail_result=computed,
                    )
                    gr = computed
                except Exception:
                    pass
            payload = {
                "guardrail_status": loaded.get("guardrail_status") or gr.get("guardrail_status") or "passed",
                "guardrail_reason": gr.get("guardrail_reason") or "",
                "launch_allowed": bool(gr.get("launch_allowed", True)),
                "recursion_blocked": bool(gr.get("recursion_blocked", False)),
                "state_repair_recommended": bool(gr.get("state_repair_recommended", False)),
            }
            summary_line = f"guardrail_status={payload.get('guardrail_status')}; launch_allowed={payload.get('launch_allowed')}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=payload)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "runtime_route":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            from NEXUS.runtime_router import route_runtime_safe
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(command=cmd, status="error", project_name=proj_name, summary=loaded.get("load_error"), payload=loaded)
            patch_req = (loaded.get("architect_plan") or {}).get("patch_request") if isinstance(loaded.get("architect_plan"), dict) else None
            result = route_runtime_safe(
                active_project=loaded.get("active_project") or proj_name,
                runtime_node=(loaded.get("dispatch_plan_summary") or {}).get("runtime_node"),
                task_type=(loaded.get("dispatch_plan_summary") or {}).get("task_type"),
                patch_request=patch_req if isinstance(patch_req, dict) else None,
                purpose="runtime_route_command",
                primary_tool=None,
                secondary_tool=None,
            )
            update_project_state_fields(path, runtime_router_result=result)
            summary_line = f"runtime={result.get('selected_runtime')}; status={result.get('runtime_router_status')}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=result)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "model_route":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            from NEXUS.model_router import route_model_safe
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(command=cmd, status="error", project_name=proj_name, summary=loaded.get("load_error"), payload=loaded)
            result = route_model_safe(
                task_class=(kwargs.get("task_class") or "fallback"),
                active_project=loaded.get("active_project") or proj_name,
                agent_name=(loaded.get("agent_selection_summary") or {}).get("selected_agent") if isinstance(loaded.get("agent_selection_summary"), dict) else None,
                runtime_node=(loaded.get("dispatch_plan_summary") or {}).get("runtime_node"),
                request_text=(loaded.get("architect_plan") or {}).get("objective") if isinstance(loaded.get("architect_plan"), dict) else None,
            )
            update_project_state_fields(path, model_router_result=result)
            summary_line = f"provider={result.get('selected_provider')}; model={result.get('selected_model')}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=result)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "deployment_preflight":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            from NEXUS.deployment_preflight import evaluate_deployment_preflight_safe
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(command=cmd, status="error", project_name=proj_name, summary=loaded.get("load_error"), payload=loaded)
            guardrail = loaded.get("guardrail_result") if isinstance(loaded.get("guardrail_result"), dict) else None
            launch = loaded.get("launch_result") if isinstance(loaded.get("launch_result"), dict) else None
            rr = loaded.get("runtime_router_result") if isinstance(loaded.get("runtime_router_result"), dict) else None
            mr = loaded.get("model_router_result") if isinstance(loaded.get("model_router_result"), dict) else None
            result = evaluate_deployment_preflight_safe(
                active_project=loaded.get("active_project") or proj_name,
                project_state=loaded,
                guardrail_result=guardrail,
                launch_result=launch,
                runtime_router_result=rr,
                model_router_result=mr,
            )
            update_project_state_fields(path, deployment_preflight_result=result)
            summary_line = f"preflight={result.get('deployment_preflight_status')}; review_required={result.get('review_required')}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=result)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "operator_snapshot":
        # No project required; best-effort compact monitoring snapshot for UI.
        try:
            import json
            from collections import deque
            from pathlib import Path
            from NEXUS.studio_config import LOGS_DIR, PROJECTS_DIR
            from NEXUS.studio_coordinator import build_studio_coordination_summary_safe
            from NEXUS.studio_driver import build_studio_driver_result_safe

            states_by_project: dict[str, dict[str, Any]] = {}
            for key in PROJECTS:
                p = PROJECTS[key].get("path")
                if p:
                    loaded = load_project_state(p)
                    if isinstance(loaded, dict) and "load_error" not in loaded:
                        states_by_project[key] = loaded

            studio_coordination_summary = build_studio_coordination_summary_safe(states_by_project)
            studio_driver_summary = build_studio_driver_result_safe(
                studio_coordination_summary=studio_coordination_summary,
                states_by_project=states_by_project,
            )

            dashboard_summary = {}
            try:
                dashboard_summary = build_registry_dashboard_summary()
            except Exception:
                dashboard_summary = {}

            log_path = Path(LOGS_DIR) / "forge_operations.jsonl"
            log_exists = log_path.exists()
            log_tail_records: list[dict[str, Any]] = []
            tail_count = 0
            if log_exists:
                try:
                    dq: deque[str] = deque(maxlen=int(kwargs.get("tail", 10) or 10))
                    with log_path.open("r", encoding="utf-8") as f:
                        for line in f:
                            dq.append(line.rstrip("\n"))
                    for line in list(dq):
                        try:
                            log_tail_records.append(json.loads(line))
                        except Exception:
                            log_tail_records.append({"_raw": line[:500]})
                    tail_count = len(log_tail_records)
                except Exception:
                    log_tail_records = []
                    tail_count = 0

            # Compact project table for operator UI.
            projects_table: list[dict[str, Any]] = []
            for key in PROJECTS:
                state = states_by_project.get(key) or {}
                review_q = state.get("review_queue_entry") or {}
                projects_table.append(
                    {
                        "project": key,
                        "lifecycle_status": state.get("project_lifecycle_status")
                        or (state.get("project_lifecycle_result") or {}).get("lifecycle_status"),
                        "queue_status": review_q.get("queue_status"),
                        "recovery_status": state.get("recovery_status")
                        or (state.get("recovery_result") or {}).get("recovery_status"),
                        "scheduler_status": state.get("scheduler_status") or (state.get("scheduler_result") or {}).get("scheduler_status"),
                        "autonomy_status": state.get("autonomy_status"),
                        "launch_status": state.get("launch_status")
                        or (state.get("launch_result") or {}).get("launch_status"),
                        "deployment_preflight_status": (state.get("deployment_preflight_result") or {}).get("deployment_preflight_status"),
                        "priority_project": key == studio_coordination_summary.get("priority_project"),
                    }
                )

            # Discover scaffolded-but-unregistered projects under projects/ (visibility only).
            registered_folder_names_lower: set[str] = set()
            for k in PROJECTS:
                p = PROJECTS.get(k, {}).get("path")
                if p:
                    try:
                        registered_folder_names_lower.add(Path(str(p)).name.strip().lower())
                    except Exception:
                        continue
            expected_scaffold_dirs = ["docs", "memory", "tasks", "generated", "state", "src"]
            scaffolded_unregistered_projects: list[dict[str, Any]] = []
            projects_dir = Path(PROJECTS_DIR) if PROJECTS_DIR else None
            if projects_dir and projects_dir.exists():
                for entry in projects_dir.iterdir():
                    try:
                        if not entry.is_dir():
                            continue
                        entry_key = entry.name.strip().lower()
                        if entry_key in registered_folder_names_lower:
                            continue
                        scaffold_dirs = {}
                        missing = []
                        for d in expected_scaffold_dirs:
                            exists = (entry / d).exists()
                            scaffold_dirs[d] = bool(exists)
                            if not exists:
                                missing.append(d)
                        state_file = entry / "state" / "project_state.json"
                        state_file_exists = bool(state_file.exists())

                        state_row: dict[str, Any] = {}
                        if state_file_exists:
                            loaded_unreg = load_project_state(str(entry))
                            if isinstance(loaded_unreg, dict) and "load_error" not in loaded_unreg:
                                review_q = loaded_unreg.get("review_queue_entry") or {}
                                state_row = {
                                    "lifecycle_status": loaded_unreg.get("project_lifecycle_status")
                                    or (loaded_unreg.get("project_lifecycle_result") or {}).get("lifecycle_status"),
                                    "queue_status": review_q.get("queue_status"),
                                    "recovery_status": loaded_unreg.get("recovery_status")
                                    or (loaded_unreg.get("recovery_result") or {}).get("recovery_status"),
                                    "scheduler_status": loaded_unreg.get("scheduler_status")
                                    or (loaded_unreg.get("scheduler_result") or {}).get("scheduler_status"),
                                    "autonomy_status": loaded_unreg.get("autonomy_status")
                                    or (loaded_unreg.get("autonomy_result") or {}).get("autonomy_status"),
                                    "launch_status": loaded_unreg.get("launch_status")
                                    or (loaded_unreg.get("launch_result") or {}).get("launch_status"),
                                    "deployment_preflight_status": (loaded_unreg.get("deployment_preflight_result") or {}).get("deployment_preflight_status"),
                                }

                        scaffolded_unregistered_projects.append(
                            {
                                "project": entry.name,
                                "folder_path": str(entry),
                                "registered": False,
                                "state_file_exists": state_file_exists,
                                "scaffold_dirs": scaffold_dirs,
                                "scaffold_missing": missing,
                                "state": state_row,
                            }
                        )
                    except Exception:
                        continue

            payload = {
                "studio_coordination_summary": studio_coordination_summary,
                "studio_driver_summary": studio_driver_summary,
                "dashboard_summary": dashboard_summary,
                # Backward compatible: projects_table was the previous single list.
                "projects_table": projects_table,
                # New explicit split for operator discoverability.
                "registered_projects": projects_table,
                "scaffolded_unregistered_projects": scaffolded_unregistered_projects,
                "log_tail_status": {
                    "log_path": str(log_path),
                    "exists": log_exists,
                    "tail_count": tail_count,
                },
                "log_tail_records": log_tail_records,
            }
            return _result(command=cmd, status="ok", project_name=None, summary="Operator snapshot ready.", payload=payload)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=None, summary=str(e), payload={"error": str(e)})

    if cmd == "portfolio_status":
        try:
            dashboard_summary = build_registry_dashboard_summary()
            fallback = {
                "portfolio_status": "error_fallback",
                "total_projects": 0,
                "active_projects": 0,
                "blocked_projects": 0,
                "priority_project": None,
                "portfolio_reason": "Forge portfolio summary unavailable.",
            }
            payload = dashboard_summary.get("portfolio_summary") if isinstance(dashboard_summary, dict) else None
            if not isinstance(payload, dict) or not payload:
                payload = fallback
            summary_line = f"portfolio_status={payload.get('portfolio_status')}; active={payload.get('active_projects')}; blocked={payload.get('blocked_projects')}; priority={payload.get('priority_project')}"
            return _result(command=cmd, status="ok", project_name=None, summary=summary_line, payload=payload)
        except Exception as e:
            return _result(
                command=cmd,
                status="error",
                project_name=None,
                summary=str(e),
                payload={
                    "portfolio_status": "error_fallback",
                    "total_projects": 0,
                    "active_projects": 0,
                    "blocked_projects": 0,
                    "priority_project": None,
                    "portfolio_reason": "Forge portfolio summary failed.",
                    "error": str(e),
                },
            )

    if cmd == "runtime_infrastructure":
        try:
            dashboard_summary = build_registry_dashboard_summary()
            fallback = {
                "runtime_infrastructure_status": "error_fallback",
                "available_runtimes": [],
                "future_runtimes": [],
                "reason": "Forge runtime infrastructure summary unavailable.",
            }
            payload = dashboard_summary.get("runtime_infrastructure_summary") if isinstance(dashboard_summary, dict) else None
            if not isinstance(payload, dict) or not payload:
                payload = fallback
            summary_line = f"runtime_infrastructure_status={payload.get('runtime_infrastructure_status')}; available={len(payload.get('available_runtimes') or [])}; future={len(payload.get('future_runtimes') or [])}"
            return _result(command=cmd, status="ok", project_name=None, summary=summary_line, payload=payload)
        except Exception as e:
            return _result(
                command=cmd,
                status="error",
                project_name=None,
                summary=str(e),
                payload={
                    "runtime_infrastructure_status": "error_fallback",
                    "available_runtimes": [],
                    "future_runtimes": [],
                    "reason": "Forge runtime infrastructure summary failed.",
                    "error": str(e),
                },
            )

    if cmd == "execution_environment":
        try:
            dashboard_summary = build_registry_dashboard_summary()
            fallback = {
                "execution_environment_status": "error_fallback",
                "active_environments": [],
                "planned_environments": [],
                "runtime_target_mapping": [],
                "environments": [],
                "per_project_summaries": {},
                "reason": "Execution environment summary unavailable.",
            }
            payload = dashboard_summary.get("execution_environment_summary") if isinstance(dashboard_summary, dict) else None
            if not isinstance(payload, dict) or not payload:
                payload = dict(fallback)
            else:
                payload = dict(payload)
            if path or proj_name:
                per_project = build_per_project_environment_summary(
                    project_name=proj_name,
                    project_path=path,
                    active_runtime_target="local",
                )
                payload["per_project_environment_summary"] = per_project
            summary_line = (
                f"execution_environment_status={payload.get('execution_environment_status')}; "
                f"active={len(payload.get('active_environments') or [])}; "
                f"planned={len(payload.get('planned_environments') or [])}"
            )
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=payload)
        except Exception as e:
            return _result(
                command=cmd,
                status="error",
                project_name=None,
                summary=str(e),
                payload={
                    "execution_environment_status": "error_fallback",
                    "active_environments": [],
                    "planned_environments": [],
                    "runtime_target_mapping": [],
                    "environments": [],
                    "per_project_summaries": {},
                    "reason": "Execution environment summary failed.",
                    "error": str(e),
                },
            )

    if cmd == "memory_status":
        try:
            scope = str(kwargs.get("scope") or ("project" if proj_name else "cross_project")).strip().lower()
            purpose = str(kwargs.get("purpose") or "advisory_context").strip() or "advisory_context"
            actor = str(kwargs.get("actor") or "nexus").strip() or "nexus"
            limit = max(1, min(int(kwargs.get("limit") or 10), 50))
            summary_payload = build_memory_layer_summary_safe(project_name=proj_name if scope == "project" else None)
            read_payload = read_governed_memory_safe(
                actor=actor,
                purpose=purpose,
                scope=scope,
                project_name=proj_name,
                category=kwargs.get("category"),
                source_type=kwargs.get("source_type"),
                limit=limit,
                allowed_components=("nexus", "helios"),
            )
            payload = {
                "memory_summary": summary_payload,
                "memory_read": read_payload,
            }
            summary_line = (
                f"memory_status={read_payload.get('status')}; "
                f"scope={read_payload.get('memory_scope')}; "
                f"records={read_payload.get('record_count', len(read_payload.get('records') or []))}; "
                f"advisory_only=True"
            )
            status = "ok" if read_payload.get("status") == "ok" else "blocked" if read_payload.get("status") == "denied" else "error"
            return _result(command=cmd, status=status, project_name=proj_name, summary=summary_line, payload=payload)
        except Exception as e:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary=str(e),
                payload={
                    "memory_summary": build_memory_layer_summary_safe(project_name=proj_name),
                    "memory_read": {
                        "status": "error",
                        "operation": "read",
                        "memory_scope": "project" if proj_name else "cross_project",
                        "actor": "nexus",
                        "source_type": "",
                        "reason": str(e),
                        "governance_trace": {"advisory_only": True},
                        "records": [],
                    },
                },
            )

    if cmd == "meta_engine_status":
        try:
            dashboard_summary = build_registry_dashboard_summary()
            fallback_engine = {
                "engine_status": "error_fallback",
                "engine_reason": "Meta engine evaluation unavailable.",
                "review_required": True,
            }
            fallback = {
                "safety_engine": fallback_engine,
                "security_engine": fallback_engine,
                "compliance_engine": fallback_engine,
                "risk_engine": fallback_engine,
                "policy_engine": fallback_engine,
                "cost_engine": fallback_engine,
                "audit_engine": fallback_engine,
            }
            payload = dashboard_summary.get("meta_engine_summary") if isinstance(dashboard_summary, dict) else None
            if not isinstance(payload, dict) or not payload:
                payload = fallback
            summary_line = f"meta_engines_ready_count={len([v for v in payload.values() if isinstance(v, dict) and v.get('review_required') is False])}; total={len(payload)}"
            return _result(command=cmd, status="ok", project_name=None, summary=summary_line, payload=payload)
        except Exception as e:
            fallback_engine = {
                "engine_status": "error_fallback",
                "engine_reason": "Meta engine evaluation unavailable.",
                "review_required": True,
            }
            fallback = {
                "safety_engine": fallback_engine,
                "security_engine": fallback_engine,
                "compliance_engine": fallback_engine,
                "risk_engine": fallback_engine,
                "policy_engine": fallback_engine,
                "cost_engine": fallback_engine,
                "audit_engine": fallback_engine,
            }
            return _result(command=cmd, status="error", project_name=None, summary=str(e), payload=fallback)

    if cmd == "forge_os_snapshot":
        try:
            dashboard_summary = build_registry_dashboard_summary()
            fallback_portfolio = {
                "portfolio_status": "error_fallback",
                "total_projects": 0,
                "active_projects": 0,
                "blocked_projects": 0,
                "priority_project": None,
                "portfolio_reason": "Forge portfolio summary unavailable.",
            }
            fallback_runtime = {
                "runtime_infrastructure_status": "error_fallback",
                "available_runtimes": [],
                "future_runtimes": [],
                "reason": "Forge runtime infrastructure summary unavailable.",
            }
            fallback_exec_env = {
                "execution_environment_status": "error_fallback",
                "active_environments": [],
                "planned_environments": [],
                "runtime_target_mapping": [],
                "environments": [],
                "reason": "Execution environment summary unavailable.",
            }
            fallback_engine = {
                "engine_status": "error_fallback",
                "engine_reason": "Meta engine evaluation unavailable.",
                "review_required": True,
            }
            fallback_meta = {
                "safety_engine": fallback_engine,
                "security_engine": fallback_engine,
                "compliance_engine": fallback_engine,
                "risk_engine": fallback_engine,
                "policy_engine": fallback_engine,
                "cost_engine": fallback_engine,
                "audit_engine": fallback_engine,
            }

            portfolio_summary = dashboard_summary.get("portfolio_summary") if isinstance(dashboard_summary, dict) else None
            if not isinstance(portfolio_summary, dict) or not portfolio_summary:
                portfolio_summary = fallback_portfolio

            runtime_infrastructure_summary = dashboard_summary.get("runtime_infrastructure_summary") if isinstance(dashboard_summary, dict) else None
            if not isinstance(runtime_infrastructure_summary, dict) or not runtime_infrastructure_summary:
                runtime_infrastructure_summary = fallback_runtime

            execution_environment_summary = dashboard_summary.get("execution_environment_summary") if isinstance(dashboard_summary, dict) else None
            if not isinstance(execution_environment_summary, dict) or not execution_environment_summary:
                execution_environment_summary = fallback_exec_env

            meta_engine_summary = dashboard_summary.get("meta_engine_summary") if isinstance(dashboard_summary, dict) else None
            if not isinstance(meta_engine_summary, dict) or not meta_engine_summary:
                meta_engine_summary = fallback_meta

            studio_coordination_summary = dashboard_summary.get("studio_coordination_summary") if isinstance(dashboard_summary, dict) else None
            if not isinstance(studio_coordination_summary, dict):
                studio_coordination_summary = {}

            studio_driver_summary = dashboard_summary.get("studio_driver_summary") if isinstance(dashboard_summary, dict) else None
            if not isinstance(studio_driver_summary, dict):
                studio_driver_summary = {}

            payload = {
                "portfolio_summary": portfolio_summary,
                "runtime_infrastructure_summary": runtime_infrastructure_summary,
                "execution_environment_summary": execution_environment_summary,
                "meta_engine_summary": meta_engine_summary,
                "studio_coordination_summary": studio_coordination_summary,
                "studio_driver_summary": studio_driver_summary,
                "dashboard_summary": dashboard_summary if isinstance(dashboard_summary, dict) else {},
            }

            summary_line = (
                f"forge_os_status={payload.get('portfolio_summary', {}).get('portfolio_status')}; "
                f"runtime_status={payload.get('runtime_infrastructure_summary', {}).get('runtime_infrastructure_status')}; "
                f"exec_env_status={payload.get('execution_environment_summary', {}).get('execution_environment_status')}; "
                f"meta_review_required={sum(1 for v in (payload.get('meta_engine_summary') or {}).values() if isinstance(v, dict) and bool(v.get('review_required')))}"
            )
            return _result(command=cmd, status="ok", project_name=None, summary=summary_line, payload=payload)
        except Exception as e:
            fallback_portfolio = {
                "portfolio_status": "error_fallback",
                "total_projects": 0,
                "active_projects": 0,
                "blocked_projects": 0,
                "priority_project": None,
                "portfolio_reason": "Forge portfolio summary unavailable.",
            }
            fallback_runtime = {
                "runtime_infrastructure_status": "error_fallback",
                "available_runtimes": [],
                "future_runtimes": [],
                "reason": "Forge runtime infrastructure summary unavailable.",
            }
            fallback_engine = {
                "engine_status": "error_fallback",
                "engine_reason": "Meta engine evaluation unavailable.",
                "review_required": True,
            }
            fallback_meta = {
                "safety_engine": fallback_engine,
                "security_engine": fallback_engine,
                "compliance_engine": fallback_engine,
                "risk_engine": fallback_engine,
                "policy_engine": fallback_engine,
                "cost_engine": fallback_engine,
                "audit_engine": fallback_engine,
            }
            fallback_exec_env = {
                "execution_environment_status": "error_fallback",
                "active_environments": [],
                "planned_environments": [],
                "runtime_target_mapping": [],
                "environments": [],
                "reason": "Execution environment summary unavailable.",
            }
            payload = {
                "portfolio_summary": fallback_portfolio,
                "runtime_infrastructure_summary": fallback_runtime,
                "execution_environment_summary": fallback_exec_env,
                "meta_engine_summary": fallback_meta,
                "studio_coordination_summary": {},
                "studio_driver_summary": {},
                "dashboard_summary": {},
            }
            return _result(command=cmd, status="error", project_name=None, summary=str(e), payload=payload)

    if cmd == "integrity_check":
        try:
            from NEXUS.integrity_checker import run_integrity_check_safe
            result = run_integrity_check_safe(project_path=path)
            status = "ok" if result.get("all_valid", False) else "issues_detected"
            summary_line = f"integrity_status={result.get('integrity_status')}; all_valid={result.get('all_valid')}"
            return _result(command=cmd, status=status, project_name=None, summary=summary_line, payload=result)
        except Exception as e:
            return _result(
                command=cmd,
                status="error",
                project_name=None,
                summary=str(e),
                payload={
                    "integrity_status": "error",
                    "reason": str(e),
                    "checks": [],
                    "all_valid": False,
                },
            )

    if cmd in {"titan_status", "leviathan_status", "veritas_status", "sentinel_status"}:
        try:
            dashboard_summary = build_registry_dashboard_summary()

            field_map = {
                "titan_status": "titan_summary",
                "leviathan_status": "leviathan_summary",
                "veritas_status": "veritas_summary",
                "sentinel_status": "sentinel_summary",
            }
            payload_field = field_map.get(cmd) or ""

            payload = dashboard_summary.get(payload_field) if isinstance(dashboard_summary, dict) else None
            if not isinstance(payload, dict) or not payload:
                payload = {
                    "titan_status": {
                        "titan_status": "error_fallback",
                        "execution_mode": "idle",
                        "next_execution_action": "idle",
                        "execution_reason": "TITAN summary unavailable.",
                        "run_permitted": False,
                    },
                    "leviathan_status": {
                        "leviathan_status": "error_fallback",
                        "highest_leverage_project": None,
                        "highest_leverage_reason": "LEVIATHAN summary unavailable.",
                        "recommended_focus": "Review required.",
                        "defer_projects": [],
                    },
                    "veritas_status": {
                        "veritas_status": "error_fallback",
                        "truth_reason": "VERITAS summary unavailable.",
                        "contradictions_detected": False,
                        "assumption_review_required": True,
                        "truth_confidence": "low",
                        "issues": [],
                        "source_signals": {
                            "state_validator": None,
                            "guardrails": None,
                            "prism_recommendation": None,
                            "aegis_decision": None,
                        },
                    },
                    "sentinel_status": {
                        "sentinel_status": "error_fallback",
                        "threat_reason": "SENTINEL summary unavailable.",
                        "high_risk_detected": False,
                        "review_required": True,
                        "risk_level": "unknown",
                        "active_warnings": [],
                        "source_signals": {
                            "safety_engine": None,
                            "security_engine": None,
                            "compliance_engine": None,
                            "risk_engine": None,
                            "aegis_decision": None,
                            "deployment_preflight": None,
                        },
                    },
                }.get(cmd, {})

            if cmd == "titan_status":
                summary_line = f"titan_status={payload.get('titan_status')}"
            elif cmd == "leviathan_status":
                summary_line = f"leviathan_status={payload.get('leviathan_status')}"
            elif cmd == "veritas_status":
                summary_line = f"veritas_status={payload.get('veritas_status')}"
            else:
                summary_line = f"sentinel_status={payload.get('sentinel_status')}"
            return _result(command=cmd, status="ok", project_name=None, summary=summary_line, payload=payload)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=None, summary=str(e), payload={})

    if cmd == "helios_status":
        # HELIOS is planning/gating visibility; run live regression checks on demand.
        try:
            from elite_layers.helios import build_helios_summary_safe

            dashboard_summary = build_registry_dashboard_summary()
            studio_coordination_summary = dashboard_summary.get("studio_coordination_summary") or {}
            studio_driver_summary = dashboard_summary.get("studio_driver_summary") or {}
            project_name = (studio_coordination_summary.get("priority_project") or "jarvis") if isinstance(studio_coordination_summary, dict) else "jarvis"

            payload = build_helios_summary_safe(
                dashboard_summary=dashboard_summary,
                studio_coordination_summary=studio_coordination_summary,
                studio_driver_summary=studio_driver_summary,
                project_name=str(project_name),
                live_regression=True,
                helios_evaluation_mode="live",
            )

            cp = payload.get("change_proposal") or {}
            summary_line = (
                f"helios_status={payload.get('helios_status')}; helios_mode={payload.get('helios_evaluation_mode')}; "
                f"execution_gated={payload.get('execution_gated')}; proposal_recommended_path={cp.get('recommended_path')}; "
                f"risk={cp.get('risk_level')}; target_area={cp.get('target_area')}"
            )
            return _result(command=cmd, status="ok", project_name=None, summary=summary_line, payload=payload)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=None, summary=str(e), payload={"error": str(e)})

    if cmd == "helios_proposal":
        # Focused proposal packet only (no execution).
        try:
            from elite_layers.helios import build_helios_summary_safe

            dashboard_summary = build_registry_dashboard_summary()
            studio_coordination_summary = dashboard_summary.get("studio_coordination_summary") or {}
            studio_driver_summary = dashboard_summary.get("studio_driver_summary") or {}
            project_name = (
                studio_coordination_summary.get("priority_project") or "jarvis"
                if isinstance(studio_coordination_summary, dict)
                else "jarvis"
            )

            helios_res = build_helios_summary_safe(
                dashboard_summary=dashboard_summary,
                studio_coordination_summary=studio_coordination_summary,
                studio_driver_summary=studio_driver_summary,
                project_name=str(project_name),
                live_regression=True,
                helios_evaluation_mode="live",
            )
            proposal = helios_res.get("change_proposal") or {}
            cp_summary_line = (
                f"proposal_id={proposal.get('proposal_id')}; recommended_path={proposal.get('recommended_path')}; "
                f"helios_mode={helios_res.get('helios_evaluation_mode')}"
            )
            return _result(command=cmd, status="ok", project_name=None, summary=cp_summary_line, payload=proposal)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=None, summary=str(e), payload={"error": str(e)})

    if cmd == "studio_loop_tick":
        # One bounded studio loop tick: one path selected + one bounded follow-through step.
        try:
            from studio_loop import run_studio_loop_tick_safe

            dashboard_summary = build_registry_dashboard_summary()
            result = run_studio_loop_tick_safe(dashboard_summary=dashboard_summary)
            summary_line = (
                f"studio_loop_status={result.get('studio_loop_status')}; "
                f"selected_path={result.get('selected_path')}; "
                f"executed_command={result.get('executed_command')}; "
                f"execution_started={result.get('execution_started')}"
            )
            return _result(command=cmd, status="ok", project_name=None, summary=summary_line, payload=result)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=None, summary=str(e), payload={"error": str(e)})

    if cmd == "elite_systems_snapshot":
        try:
            from elite_layers.helios import build_helios_summary_safe

            dashboard_summary = build_registry_dashboard_summary()
            studio_coordination_summary = dashboard_summary.get("studio_coordination_summary") or {}
            studio_driver_summary = dashboard_summary.get("studio_driver_summary") or {}
            project_name = (studio_coordination_summary.get("priority_project") or "jarvis") if isinstance(studio_coordination_summary, dict) else "jarvis"

            helios_live = build_helios_summary_safe(
                dashboard_summary=dashboard_summary,
                studio_coordination_summary=studio_coordination_summary,
                studio_driver_summary=studio_driver_summary,
                project_name=str(project_name),
                live_regression=True,
            )

            payload = {
                "titan_summary": dashboard_summary.get("titan_summary") if isinstance(dashboard_summary, dict) else {},
                "leviathan_summary": dashboard_summary.get("leviathan_summary") if isinstance(dashboard_summary, dict) else {},
                "helios_summary": helios_live,
                "veritas_summary": dashboard_summary.get("veritas_summary") if isinstance(dashboard_summary, dict) else {},
                "sentinel_summary": dashboard_summary.get("sentinel_summary") if isinstance(dashboard_summary, dict) else {},
            }
            summary_line = f"elite_snapshot: titan={payload.get('titan_summary', {}).get('titan_status')}; helios={payload.get('helios_summary', {}).get('helios_status')}; veritas={payload.get('veritas_summary', {}).get('veritas_status')}; sentinel={payload.get('sentinel_summary', {}).get('sentinel_status')}"
            return _result(command=cmd, status="ok", project_name=None, summary=summary_line, payload=payload)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=None, summary=str(e), payload={"error": str(e)})

    if cmd == "prism_evaluate":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            from PRISM.prism_engine import evaluate_prism_safe

            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(command=cmd, status="error", project_name=proj_name, summary=loaded.get("load_error"), payload=loaded)

            architect_plan = loaded.get("architect_plan") or {}
            if not isinstance(architect_plan, dict):
                architect_plan = {}

            project_name_for_prism = str(loaded.get("active_project") or proj_name or "")

            # Phase 1.5: pass CLI inputs + state inputs separately; merge inside PRISM engine.
            cli_inputs: dict[str, Any] = {}
            for k in (
                "product_concept",
                "problem_solved",
                "target_audience",
                "comparable_products",
                "launch_angle",
                "monetization_model",
                "feature_list",
                "notes",
            ):
                v = kwargs.get(k)
                if v is not None:
                    cli_inputs[k] = v

            state_inputs: dict[str, Any] = {
                "product_concept": architect_plan.get("objective") or loaded.get("notes") or "",
                "problem_solved": architect_plan.get("problem_solved") or architect_plan.get("problem") or "",
                "target_audience": architect_plan.get("target_audience") or architect_plan.get("audience") or "",
                "comparable_products": architect_plan.get("comparable_products")
                or architect_plan.get("comparables")
                or [],
                "launch_angle": architect_plan.get("launch_angle") or "",
                "monetization_model": architect_plan.get("monetization_model") or "",
                "feature_list": architect_plan.get("feature_list") or architect_plan.get("features") or [],
                "notes": loaded.get("notes") or "",
            }

            result = evaluate_prism_safe(
                project_name=project_name_for_prism,
                cli_inputs=cli_inputs,
                state_inputs=state_inputs,
            )

            last_prism_summary = {
                "recommendation": result.get("recommendation"),
                "success_estimate": (result.get("scores") or {}).get("success_estimate"),
                "strongest_audience_segment": result.get("strongest_audience_segment"),
                "strongest_launch_angle": result.get("strongest_launch_angle"),
            }
            update_project_state_fields(
                path,
                prism_status=result.get("prism_status"),
                prism_result=result,
                last_prism_summary=last_prism_summary,
            )

            scores = result.get("scores") or {}
            summary_line = (
                f"prism_status={result.get('prism_status')}; recommendation={result.get('recommendation')}; "
                f"success_estimate={scores.get('success_estimate')}"
            )
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=result)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "prism_status":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(command=cmd, status="error", project_name=proj_name, summary=loaded.get("load_error"), payload=loaded)

            prism_result = loaded.get("prism_result") or {}
            if not isinstance(prism_result, dict) or not prism_result:
                # Return stable PRISM result shape with zeros.
                prism_result = {
                    "prism_status": "insufficient_input",
                    "project_name": str(loaded.get("active_project") or proj_name or "") or None,
                    "scores": {
                        "novelty": 0,
                        "clarity": 0,
                        "emotional_pull": 0,
                        "curiosity": 0,
                        "virality_potential": 0,
                        "monetization_potential": 0,
                        "success_estimate": 0,
                    },
                    "strongest_audience_segment": None,
                    "strongest_launch_angle": None,
                    "audience_friction_points": [],
                    "recommendation": "hold",
                    "recommendation_reason": "No persisted PRISM evaluation found for this project.",
                }

            recommendation = prism_result.get("recommendation")
            scores = prism_result.get("scores") or {}
            summary_line = f"recommendation={recommendation}; success_estimate={(scores or {}).get('success_estimate')}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=prism_result)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd in {"genesis_generate", "genesis_refine", "genesis_rank"}:
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )

        try:
            from elite_layers.genesis_engine import build_genesis_engine_safe

            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(command=cmd, status="error", project_name=proj_name, summary=loaded.get("load_error"), payload=loaded)

            project_name_for_genesis = str(loaded.get("active_project") or proj_name or "")
            if not project_name_for_genesis:
                project_name_for_genesis = proj_name or "project"

            n_ideas = int(kwargs.get("n_ideas") or kwargs.get("n") or 4)
            if n_ideas < 1:
                n_ideas = 4

            if cmd == "genesis_generate":
                result = build_genesis_engine_safe(
                    genesis_mode="generate",
                    project_state=loaded,
                    project_name=project_name_for_genesis,
                    n_ideas=n_ideas,
                )
                summary_line = f"genesis_status={result.get('genesis_status')}; ideas={len(result.get('ideas') or [])}"
                return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=result)

            if cmd == "genesis_refine":
                idea_in: dict[str, Any] = {}
                if isinstance(kwargs.get("idea"), dict):
                    idea_in = kwargs.get("idea")  # type: ignore[assignment]
                else:
                    idea_json = kwargs.get("idea_json") or kwargs.get("idea")
                    if isinstance(idea_json, str) and idea_json.strip():
                        import json

                        idea_in = json.loads(idea_json)
                    elif idea_json is not None and not idea_in:
                        # Best-effort: ignore malformed inputs.
                        idea_in = {}

                if not isinstance(idea_in, dict) or not idea_in:
                    # Conservative fallback: refine from freshly generated candidate #1.
                    gen = build_genesis_engine_safe(
                        genesis_mode="generate",
                        project_state=loaded,
                        project_name=project_name_for_genesis,
                        n_ideas=1,
                    )
                    ideas = gen.get("ideas") or []
                    idea_in = ideas[0] if ideas else {}

                result = build_genesis_engine_safe(
                    genesis_mode="refine",
                    project_state=loaded,
                    project_name=project_name_for_genesis,
                    idea=idea_in,
                )
                summary_line = f"genesis_status={result.get('genesis_status')}; refined_ideas={len(result.get('ideas') or [])}"
                return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=result)

            if cmd == "genesis_rank":
                ideas_in = kwargs.get("ideas")
                if isinstance(ideas_in, str) and ideas_in.strip():
                    import json

                    ideas_in = json.loads(ideas_in)
                if not isinstance(ideas_in, list):
                    ideas_in = []

                result = build_genesis_engine_safe(
                    genesis_mode="rank",
                    project_state=loaded,
                    project_name=project_name_for_genesis,
                    n_ideas=n_ideas,
                    ideas=ideas_in,
                )
                ranking = result.get("ranking") or []
                top_score = ranking[0].get("total_score") if ranking and isinstance(ranking[0], dict) else None
                ranking_conf = result.get("ranking_confidence")
                aegis_dec = result.get("aegis_decision")
                gaps = result.get("context_gaps") or []
                gaps_count = len(gaps) if isinstance(gaps, list) else 0
                summary_line = (
                    f"genesis_status={result.get('genesis_status')}; ranking_confidence={ranking_conf}; "
                    f"aegis_decision={aegis_dec}; top_total_score={top_score}; context_gaps={gaps_count}"
                )
                return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=result)

            return _result(command=cmd, status="error", project_name=proj_name, summary="Unknown GENESIS mode.", payload={})
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "project_onboard":
        # Requires project context (project_name). Creates project scaffold in projects/<name>.
        if not proj_name:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="project_name required.",
                payload={},
            )
        try:
            from NEXUS.project_onboarding import create_project_scaffold_safe

            result = create_project_scaffold_safe(project_name=proj_name)
            return _result(
                command=cmd,
                status="ok" if result.get("onboarding_status") != "error_fallback" else "error",
                project_name=proj_name,
                summary=result.get("reason") or result.get("onboarding_status"),
                payload=result,
            )
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "self_improvement_backlog":
        # No project required. Pure planning/visibility.
        try:
            from NEXUS.self_improvement_engine import build_self_improvement_backlog_safe, select_next_improvement_safe
            from NEXUS.studio_coordinator import build_studio_coordination_summary_safe
            from NEXUS.studio_driver import build_studio_driver_result_safe

            # Load states for deterministic coordination/driver summaries.
            states_by_project: dict[str, dict[str, Any]] = {}
            for key in PROJECTS:
                p = PROJECTS[key].get("path")
                if p:
                    loaded = load_project_state(p)
                    if isinstance(loaded, dict) and "load_error" not in loaded:
                        states_by_project[key] = loaded

            studio_coordination_summary = build_studio_coordination_summary_safe(states_by_project)
            studio_driver_summary = build_studio_driver_result_safe(
                studio_coordination_summary=studio_coordination_summary,
                states_by_project=states_by_project,
            )

            dashboard_summary = build_registry_dashboard_summary()
            backlog_items = build_self_improvement_backlog_safe(
                dashboard_summary=dashboard_summary,
                studio_coordination_summary=studio_coordination_summary,
                driver_summary=studio_driver_summary,
            )
            selected = select_next_improvement_safe(backlog_items=backlog_items)
            # Keep response compact: return top N items.
            top_n = int(kwargs.get("n_backlog", 5) or 5)
            backlog_all_count = len(backlog_items)
            backlog_items = backlog_items[: max(1, top_n)]
            payload = {
                "backlog_status": "ok",
                "backlog_count": backlog_all_count,
                "selected_improvement_summary": selected,
                "backlog_items": backlog_items,
            }
            return _result(command=cmd, status="ok", project_name=None, summary="Self-improvement backlog ready.", payload=payload)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=None, summary=str(e), payload={"error": str(e)})

    if cmd == "improve_system":
        # Planning only: select one improvement candidate; run regression checks and return recommendation.
        try:
            project_key = proj_name or "jarvis"
            from NEXUS.self_improvement_engine import build_self_improvement_backlog_safe, select_next_improvement_safe
            from NEXUS.regression_checks import run_regression_checks_safe
            from NEXUS.change_safety_gate import evaluate_change_gate_safe
            from NEXUS.studio_coordinator import build_studio_coordination_summary_safe
            from NEXUS.studio_driver import build_studio_driver_result_safe

            states_by_project: dict[str, dict[str, Any]] = {}
            for key in PROJECTS:
                p = PROJECTS[key].get("path")
                if p:
                    loaded = load_project_state(p)
                    if isinstance(loaded, dict) and "load_error" not in loaded:
                        states_by_project[key] = loaded

            studio_coordination_summary = build_studio_coordination_summary_safe(states_by_project)
            studio_driver_summary = build_studio_driver_result_safe(
                studio_coordination_summary=studio_coordination_summary,
                states_by_project=states_by_project,
            )
            dashboard_summary = build_registry_dashboard_summary()

            backlog_items = build_self_improvement_backlog_safe(
                dashboard_summary=dashboard_summary,
                studio_coordination_summary=studio_coordination_summary,
                driver_summary=studio_driver_summary,
            )
            selected = select_next_improvement_safe(backlog_items=backlog_items)

            # Regression checks gate acceptance (planning-only).
            regression = run_regression_checks_safe(project_name=project_key or "jarvis")

            # Change gate: conservative (no execution in this sprint).
            selected_item = next((i for i in backlog_items if i.get("item_id") == selected.get("selected_item_id")), {})  # type: ignore[arg-type]
            gate = evaluate_change_gate_safe(
                target_area=selected_item.get("target_area"),
                category=selected_item.get("category"),
                priority=selected_item.get("priority"),
                project_name=project_key or "jarvis",
                core_files_touched=False,
            )

            regression_status = (regression or {}).get("regression_status")
            if regression_status == "passed" and gate.get("execution_allowed") is False:
                improvement_status = "planned"
            elif regression_status in ("warning",) and gate.get("execution_allowed") is False:
                improvement_status = "planned"
            elif regression_status == "blocked":
                improvement_status = "error_fallback"
            else:
                improvement_status = "none_available"

            improvement_reason = (
                f"Selected={selected.get('selected_item_id')}; regression={regression_status}; gate={gate.get('change_gate_status')}."
            )
            payload = {
                "improvement_status": improvement_status,
                "selected_item_id": selected.get("selected_item_id"),
                "selected_title": selected.get("selected_title"),
                "selected_category": selected.get("selected_category"),
                "improvement_reason": improvement_reason,
                "execution_recommended": False,
            }

            # Persist compact planning results for operator visibility.
            if path:
                update_project_state_fields(
                    path,
                    self_improvement_status=payload.get("improvement_status"),
                    self_improvement_result=payload,
                    regression_status=(regression or {}).get("regression_status"),
                    regression_result=regression,
                    change_gate_status=(gate or {}).get("change_gate_status"),
                    change_gate_result=gate,
                )

            return _result(command=cmd, status="ok", project_name=proj_name, summary=f"improvement_status={payload.get('improvement_status')}", payload=payload)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "change_gate":
        # Compact gate evaluation; planning only.
        try:
            from NEXUS.change_safety_gate import evaluate_change_gate_safe
            target_area = kwargs.get("target_area")
            category = kwargs.get("category")
            priority = kwargs.get("priority")
            core_files_touched = bool(kwargs.get("core_files_touched", False))
            gate = evaluate_change_gate_safe(
                target_area=target_area,
                category=category,
                priority=priority,
                project_name=proj_name or "unknown",
                core_files_touched=core_files_touched,
            )
            if path:
                update_project_state_fields(
                    path,
                    change_gate_status=gate.get("change_gate_status"),
                    change_gate_result=gate,
                )
            payload = {
                "change_gate_status": gate.get("change_gate_status") or "blocked",
                "change_gate_reason": gate.get("change_gate_reason") or "",
                "execution_allowed": bool(gate.get("execution_allowed", False)),
                "review_required": bool(gate.get("review_required", False)),
            }
            return _result(command=cmd, status="ok", project_name=proj_name, summary=f"gate={payload.get('change_gate_status')}", payload=payload)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "regression_check":
        try:
            from NEXUS.regression_checks import run_regression_checks_safe
            project_key = proj_name or "jarvis"
            regression = run_regression_checks_safe(project_name=project_key)
            if path:
                update_project_state_fields(
                    path,
                    regression_status=regression.get("regression_status"),
                    regression_result=regression,
                )
            payload = regression
            return _result(command=cmd, status="ok", project_name=proj_name, summary=f"regression_status={payload.get('regression_status')}", payload=payload)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "aegis_status":
        try:
            from AEGIS.aegis_contract import normalize_aegis_result
            from AEGIS.aegis_core import evaluate_action_safe
            if path:
                loaded = load_project_state(path)
                aegis_raw = (loaded.get("last_aegis_decision") or {}) if isinstance(loaded.get("last_aegis_decision"), dict) else None
                if not aegis_raw:
                    aegis_raw = evaluate_action_safe(request={"project_name": proj_name, "project_path": path, "action_mode": "evaluation"})
                payload = normalize_aegis_result(aegis_raw)
            else:
                payload = normalize_aegis_result(evaluate_action_safe(request={"project_name": proj_name, "action_mode": "evaluation"}))
            summary = f"aegis_decision={payload.get('aegis_decision')}; scope={payload.get('aegis_scope')}; approval_required={payload.get('approval_required')}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary, payload=payload)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "forgeshell_status":
        try:
            from AEGIS.forgeshell import get_forgeshell_status_cached_safe

            payload = get_forgeshell_status_cached_safe(project_path=path)
            status_key = payload.get("forgeshell_status")
            summary = f"forgeshell_status={status_key}; security_level={payload.get('forgeshell_security_level')}; summary_reason={payload.get('summary_reason')}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary, payload=payload)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "forgeshell_test":
        try:
            from AEGIS.forgeshell import execute_forgeshell_command_safe
            result = execute_forgeshell_command_safe(
                command_family="shell_test",
                project_path=path,
                timeout_seconds=15.0,
            )
            status_key = result.get("forgeshell_status")
            summary = (
                f"forgeshell_status={status_key}; exit_code={result.get('exit_code')}; timeout_hit={result.get('timeout_hit')}; "
                f"security_level={result.get('forgeshell_security_level')}; summary_reason={result.get('summary_reason')}"
            )
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary, payload=result)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e), "forgeshell_status": "error_fallback"})

    if cmd == "tool_gateway_status":
        try:
            from AEGIS.tool_gateway import route_tool_request_safe
            result = route_tool_request_safe(
                tool_family="evaluation",
                project_path=path,
                action_mode="evaluation",
            )
            summary = f"tool_gateway_status={result.get('tool_gateway_status')}; tool_family={result.get('tool_family')}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary, payload=result)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "pending_approvals":
        try:
            from NEXUS.approval_summary import build_approval_summary_safe
            summary_data = build_approval_summary_safe(n_recent=20, n_tail=100)
            if path or proj_name:
                proj_path = path
                if not proj_path and proj_name:
                    key = str(proj_name).strip().lower()
                    if key in PROJECTS:
                        proj_path = PROJECTS[key].get("path")
                if proj_path:
                    from NEXUS.approval_registry import get_pending_approvals
                    pending = get_pending_approvals(project_path=proj_path, n=50)
                    summary_data["pending_for_project"] = pending
            payload = summary_data
            summary_line = f"approval_status={payload.get('approval_status')}; pending_count={payload.get('pending_count_total')}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=payload)
        except Exception as e:
            fallback = {
                "approval_status": "error_fallback",
                "pending_count_total": 0,
                "pending_by_project": {},
                "recent_approvals": [],
                "approval_types": [],
                "stale_count": 0,
                "approved_pending_apply_count": 0,
                "reason": str(e),
                "error": str(e),
            }
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload=fallback)

    if cmd == "approval_details":
        try:
            approval_id = (kwargs.get("approval_id") or "").strip() or None
            proj_path = path
            if not proj_path and proj_name:
                key = str(proj_name).strip().lower()
                if key in PROJECTS:
                    proj_path = PROJECTS[key].get("path")
            from NEXUS.approval_registry import read_approval_journal_tail
            from NEXUS.approval_summary import build_approval_summary_safe
            if approval_id:
                found = None
                found_project = None
                for proj_key in PROJECTS:
                    p = PROJECTS[proj_key].get("path")
                    if p:
                        tail = read_approval_journal_tail(project_path=p, n=200)
                        for r in tail:
                            if r.get("approval_id") == approval_id:
                                found = {**r, "_project": proj_key}
                                found_project = proj_key
                                ctx = r.get("context") or {}
                                if ctx.get("patch_id"):
                                    found["patch_id_ref"] = ctx.get("patch_id")
                                try:
                                    from NEXUS.approval_staleness import evaluate_approval_staleness
                                    is_stale, hours = evaluate_approval_staleness(r)
                                    found["_stale"] = is_stale
                                    found["_hours_since_decision"] = round(hours, 1)
                                except Exception:
                                    pass
                                break
                    if found:
                        break
                payload = {"approval": found, "found_in_project": found_project}
                summary_line = "approval_found" if found else "approval_not_found"
                return _result(command=cmd, status="ok", project_name=found_project, summary=summary_line, payload=payload)
            if proj_path:
                tail = read_approval_journal_tail(project_path=proj_path, n=50)
                payload = {"recent_approvals": tail[:20]}
                return _result(command=cmd, status="ok", project_name=proj_name, summary=f"recent={len(payload['recent_approvals'])}", payload=payload)
            summary_data = build_approval_summary_safe(n_recent=30, n_tail=200)
            payload = {"recent_approvals": summary_data.get("recent_approvals", []), "approval_summary": summary_data}
            return _result(command=cmd, status="ok", project_name=None, summary=f"recent={len(payload.get('recent_approvals', []))}", payload=payload)
        except Exception as e:
            fallback = {
                "approval": None,
                "found_in_project": None,
                "recent_approvals": [],
                "error": str(e),
            }
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload=fallback)

    if cmd == "product_manifest":
        try:
            if not path and not proj_name:
                return _result(command=cmd, status="error", project_name=None, summary="Project path or project_name required.", payload={})
            proj_path = path
            if not proj_path and proj_name:
                key = str(proj_name).strip().lower()
                if key in PROJECTS:
                    proj_path = PROJECTS[key].get("path")
            if not proj_path:
                return _result(command=cmd, status="error", project_name=proj_name, summary="Project not found.", payload={})
            from NEXUS.product_builder import build_product_manifest_safe
            manifest = build_product_manifest_safe(
                project_name=proj_name or "",
                project_path=proj_path,
                project_key=str(proj_name).strip().lower() if proj_name else None,
            )
            summary_line = f"product_id={manifest.get('product_id')}; status={manifest.get('status')}; risk={manifest.get('risk_profile')}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=manifest)
        except Exception as e:
            fallback = {
                "product_id": "",
                "project_name": proj_name or "",
                "status": "error_fallback",
                "approval_requirements": {},
                "safety_summary": {},
                "risk_profile": {},
                "reason": str(e),
                "error": str(e),
            }
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload=fallback)

    if cmd == "product_summary":
        try:
            from NEXUS.product_summary import build_product_summary_safe
            summary_data = build_product_summary_safe(use_cached=True)
            payload = summary_data
            summary_line = f"product_status={payload.get('product_status')}; draft={payload.get('draft_count')}; ready={payload.get('ready_count')}; restricted={payload.get('restricted_count')}"
            return _result(command=cmd, status="ok", project_name=None, summary=summary_line, payload=payload)
        except Exception as e:
            fallback = {
                "product_status": "error_fallback",
                "draft_count": 0,
                "ready_count": 0,
                "restricted_count": 0,
                "total_count": 0,
                "products_by_project": {},
                "safety_indicators": {"safety_issues": [], "restricted_count": 0},
                "learning_linkage_present": False,
                "approval_linkage_present": False,
                "autonomy_linkage_present": False,
                "reason": str(e),
                "error": str(e),
            }
            return _result(command=cmd, status="error", project_name=None, summary=str(e), payload=fallback)

    if cmd == "patch_proposals":
        try:
            from NEXUS.patch_proposal_summary import build_patch_proposal_summary_safe
            summary_data = build_patch_proposal_summary_safe(n_recent=20, n_tail=100)
            if path or proj_name:
                proj_path = path
                if not proj_path and proj_name:
                    key = str(proj_name).strip().lower()
                    if key in PROJECTS:
                        proj_path = PROJECTS[key].get("path")
                if proj_path:
                    from NEXUS.patch_proposal_registry import read_patch_proposal_journal_tail
                    tail = read_patch_proposal_journal_tail(project_path=proj_path, n=50)
                    summary_data["proposals_for_project"] = tail[:20]
            payload = summary_data
            summary_line = f"patch_proposal_status={payload.get('patch_proposal_status')}; pending={payload.get('pending_count')}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=payload)
        except Exception as e:
            fallback = {
                "patch_proposal_status": "error_fallback",
                "pending_count": 0,
                "proposed_count": 0,
                "approval_required_count": 0,
                "approved_pending_apply_count": 0,
                "approved_pending_apply_stale_count": 0,
                "rejected_count": 0,
                "blocked_count": 0,
                "applied_count": 0,
                "approval_blocked_count": 0,
                "status_counts": {},
                "by_project": {},
                "recent_proposals": [],
                "by_risk_level": {},
                "reason": str(e),
                "error": str(e),
            }
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload=fallback)

    if cmd == "patch_proposal_details":
        try:
            patch_id = (kwargs.get("patch_id") or "").strip() or None
            proj_path = path
            if not proj_path and proj_name:
                key = str(proj_name).strip().lower()
                if key in PROJECTS:
                    proj_path = PROJECTS[key].get("path")
            from NEXUS.patch_proposal_registry import find_proposal_and_project, get_proposal_effective_status, read_patch_proposal_journal_tail
            from NEXUS.patch_proposal_summary import build_patch_proposal_summary_safe
            if patch_id:
                found, found_path, found_key = find_proposal_and_project(patch_id)
                if found and found_path:
                    effective_status, resolution = get_proposal_effective_status(project_path=found_path, patch_id=patch_id)
                    payload = {
                        "patch_proposal": {**found, "effective_status": effective_status},
                        "found_in_project": found_key,
                        "resolution": resolution,
                    }
                    return _result(command=cmd, status="ok", project_name=found_key, summary="patch_proposal_found", payload=payload)
            if proj_path:
                tail = read_patch_proposal_journal_tail(project_path=proj_path, n=50)
                enriched = []
                for r in tail[:20]:
                    es, _ = get_proposal_effective_status(proj_path, r.get("patch_id") or "")
                    enriched.append({**r, "effective_status": es})
                payload = {"recent_proposals": enriched}
                return _result(command=cmd, status="ok", project_name=proj_name, summary=f"recent={len(payload['recent_proposals'])}", payload=payload)
            summary_data = build_patch_proposal_summary_safe(n_recent=30, n_tail=200)
            payload = {"recent_proposals": summary_data.get("recent_proposals", []), "patch_proposal_summary": summary_data}
            return _result(command=cmd, status="ok", project_name=None, summary=f"recent={len(payload.get('recent_proposals', []))}", payload=payload)
        except Exception as e:
            fallback = {
                "patch_proposal": None,
                "found_in_project": None,
                "recent_proposals": [],
                "error": str(e),
            }
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload=fallback)

    if cmd == "approve_patch_proposal":
        try:
            patch_id = (kwargs.get("patch_id") or "").strip() or None
            reason = (kwargs.get("reason") or "").strip() or ""
            if not patch_id:
                return _result(command=cmd, status="error", project_name=proj_name, summary="patch_id required.", payload={"resolved": False, "error": "patch_id required."})
            from NEXUS.patch_proposal_registry import find_proposal_and_project, resolve_patch_proposal
            found, found_path, found_key = find_proposal_and_project(patch_id)
            if not found or not found_path:
                return _result(command=cmd, status="error", project_name=proj_name, summary="Patch proposal not found.", payload={"resolved": False, "error": "Patch proposal not found.", "patch_id": patch_id})
            result = resolve_patch_proposal(project_path=found_path, patch_id=patch_id, decision="approve", project_name=found_key or "", reason=reason)
            if result.get("resolved"):
                try:
                    from NEXUS.learning_writer import append_learning_record_safe
                    aid = result.get("approval_id") or ""
                    append_learning_record_safe(project_path=found_path, record={
                        "record_type": "patch_proposal_approved",
                        "project_name": found_key or "",
                        "workflow_stage": "approval_resolution",
                        "decision_source": "approve_patch_proposal",
                        "decision_type": "approve",
                        "decision_summary": f"patch_id={patch_id}; approval_id={aid}",
                        "downstream_effects": {"patch_id": patch_id, "approval_id": aid},
                        "patch_id_refs": [patch_id],
                        "approval_id_refs": [aid] if aid else [],
                        "tags": ["patch_proposal", "approval"],
                    })
                except Exception:
                    pass
            return _result(command=cmd, status="ok" if result.get("resolved") else "error", project_name=found_key, summary=result.get("reason") or result.get("error", ""), payload=result)
        except Exception as e:
            fallback = {"resolved": False, "patch_id": kwargs.get("patch_id", ""), "decision": "approve", "effective_status": "", "approval_id": "", "reason": "", "error": str(e)}
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload=fallback)

    if cmd == "reject_patch_proposal":
        try:
            patch_id = (kwargs.get("patch_id") or "").strip() or None
            reason = (kwargs.get("reason") or "").strip() or ""
            if not patch_id:
                return _result(command=cmd, status="error", project_name=proj_name, summary="patch_id required.", payload={"resolved": False, "error": "patch_id required."})
            from NEXUS.patch_proposal_registry import find_proposal_and_project, resolve_patch_proposal
            found, found_path, found_key = find_proposal_and_project(patch_id)
            if not found or not found_path:
                return _result(command=cmd, status="error", project_name=proj_name, summary="Patch proposal not found.", payload={"resolved": False, "error": "Patch proposal not found.", "patch_id": patch_id})
            result = resolve_patch_proposal(project_path=found_path, patch_id=patch_id, decision="reject", project_name=found_key or "", reason=reason)
            if result.get("resolved"):
                try:
                    from NEXUS.learning_writer import append_learning_record_safe
                    aid = result.get("approval_id") or ""
                    append_learning_record_safe(project_path=found_path, record={
                        "record_type": "patch_proposal_rejected",
                        "project_name": found_key or "",
                        "workflow_stage": "approval_resolution",
                        "decision_source": "reject_patch_proposal",
                        "decision_type": "reject",
                        "decision_summary": f"patch_id={patch_id}; approval_id={aid}",
                        "downstream_effects": {"patch_id": patch_id, "approval_id": aid},
                        "patch_id_refs": [patch_id],
                        "approval_id_refs": [aid] if aid else [],
                        "tags": ["patch_proposal", "approval"],
                    })
                except Exception:
                    pass
            return _result(command=cmd, status="ok" if result.get("resolved") else "error", project_name=found_key, summary=result.get("reason") or result.get("error", ""), payload=result)
        except Exception as e:
            fallback = {"resolved": False, "patch_id": kwargs.get("patch_id", ""), "decision": "reject", "effective_status": "", "approval_id": "", "reason": "", "error": str(e)}
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload=fallback)

    if cmd == "apply_patch_proposal":
        try:
            patch_id = (kwargs.get("patch_id") or "").strip() or None
            if not patch_id:
                return _result(command=cmd, status="error", project_name=proj_name, summary="patch_id required.", payload={"applied": False, "error": "patch_id required.", "patch_applied": False})
            from NEXUS.patch_proposal_registry import find_proposal_and_project, get_proposal_effective_status
            from NEXUS.diff_patch import apply_safe_patch, write_patch_report
            found, found_path, found_key = find_proposal_and_project(patch_id)
            if not found or not found_path:
                return _result(command=cmd, status="error", project_name=proj_name, summary="Patch proposal not found.", payload={"applied": False, "error": "Patch proposal not found.", "patch_id": patch_id, "patch_applied": False})
            effective_status, resolution = get_proposal_effective_status(project_path=found_path, patch_id=patch_id)
            if effective_status != "approved_pending_apply":
                return _result(command=cmd, status="error", project_name=found_key, summary=f"Proposal must be approved_pending_apply; current={effective_status}.", payload={"applied": False, "error": f"Status={effective_status}", "effective_status": effective_status, "patch_applied": False})
            from NEXUS.approval_staleness import is_proposal_approval_stale
            is_stale, hours_since, _ = is_proposal_approval_stale(found_path, patch_id)
            if is_stale:
                try:
                    from NEXUS.learning_writer import append_learning_record_safe
                    append_learning_record_safe(project_path=found_path, record={
                        "record_type": "patch_apply_blocked_stale",
                        "project_name": found_key or "",
                        "decision_source": "apply_patch_proposal",
                        "decision_summary": f"patch_id={patch_id}; blocked: approval stale ({hours_since:.1f}h)",
                        "patch_id_refs": [patch_id],
                        "tags": ["patch_proposal", "stale"],
                    })
                except Exception:
                    pass
                return _result(command=cmd, status="error", project_name=found_key, summary=f"Approval expired; {hours_since:.1f}h since approval. Re-approve required.", payload={"applied": False, "error": "approval_stale", "hours_since_approval": round(hours_since, 1), "patch_applied": False})
            change_type = str(found.get("change_type") or "").strip().lower()
            if change_type != "diff_patch":
                return _result(command=cmd, status="error", project_name=found_key, summary=f"Only diff_patch supported; change_type={change_type}.", payload={"applied": False, "error": f"change_type={change_type}", "patch_applied": False})
            payload_data = found.get("patch_payload") or {}
            target = payload_data.get("target_relative_path")
            search_text = payload_data.get("search_text")
            replacement_text = payload_data.get("replacement_text")
            if not target or not isinstance(search_text, str) or not isinstance(replacement_text, str) or not search_text.strip():
                return _result(command=cmd, status="error", project_name=found_key, summary="Invalid patch_payload.", payload={"applied": False, "error": "Invalid patch_payload", "patch_applied": False})
            patch_request = {
                "approved": True,
                "target_relative_path": target,
                "search_text": search_text,
                "replacement_text": replacement_text,
                "replace_all": bool(payload_data.get("replace_all", False)),
            }
            summary = apply_safe_patch(project_path=found_path, project_name=found_key or "", patch_request=patch_request)
            patch_applied = bool(summary.get("patch_applied", False))
            if patch_applied:
                write_patch_report(found_path, found_key or "", summary, run_id=found.get("run_id"))
                from NEXUS.patch_proposal_registry import append_patch_proposal_resolution
                approval_id_for_apply = (resolution or {}).get("approval_id") or ""
                append_patch_proposal_resolution(found_path, patch_id, "apply", "applied", approval_id_for_apply, project_name=found_key or "", reason="Patch applied successfully.")
                try:
                    from NEXUS.learning_writer import append_learning_record_safe
                    append_learning_record_safe(project_path=found_path, record={
                        "record_type": "patch_proposal_applied",
                        "project_name": found_key or "",
                        "workflow_stage": "apply_patch_proposal",
                        "decision_source": "apply_patch_proposal",
                        "decision_type": "applied",
                        "decision_summary": f"patch_id={patch_id}; target={target}",
                        "downstream_effects": {"patch_id": patch_id, "target": target, "patch_applied": True},
                        "patch_id_refs": [patch_id],
                        "approval_id_refs": [approval_id_for_apply] if approval_id_for_apply else [],
                        "tags": ["patch_proposal", "applied"],
                    })
                except Exception:
                    pass
            return _result(command=cmd, status="ok", project_name=found_key, summary=summary.get("reason", ""), payload={"applied": patch_applied, "patch_applied": patch_applied, "patch_summary": summary, "patch_id": patch_id})
        except Exception as e:
            fallback = {"applied": False, "patch_applied": False, "patch_id": kwargs.get("patch_id", ""), "error": str(e)}
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload=fallback)

    if cmd == "retry_patch_proposal":
        try:
            patch_id = (kwargs.get("patch_id") or "").strip() or None
            if not patch_id:
                return _result(command=cmd, status="error", project_name=proj_name, summary="patch_id required.", payload={"ready_for_apply": False, "error": "patch_id required.", "patch_id": ""})
            from NEXUS.patch_proposal_registry import find_proposal_and_project, get_proposal_effective_status
            from NEXUS.approval_staleness import is_proposal_approval_stale, APPROVAL_STALENESS_HOURS
            found, found_path, found_key = find_proposal_and_project(patch_id)
            if not found or not found_path:
                return _result(command=cmd, status="error", project_name=proj_name, summary="Patch proposal not found.", payload={"ready_for_apply": False, "error": "Patch proposal not found.", "patch_id": patch_id})
            effective_status, resolution = get_proposal_effective_status(project_path=found_path, patch_id=patch_id)
            if effective_status != "approved_pending_apply":
                return _result(command=cmd, status="error", project_name=found_key, summary=f"Proposal must be approved_pending_apply; current={effective_status}.", payload={"ready_for_apply": False, "error": f"status={effective_status}", "effective_status": effective_status, "patch_id": patch_id})
            is_stale, hours_since, _ = is_proposal_approval_stale(found_path, patch_id)
            if is_stale:
                try:
                    from NEXUS.learning_writer import append_learning_record_safe
                    append_learning_record_safe(project_path=found_path, record={
                        "record_type": "retry_checked_stale",
                        "project_name": found_key or "",
                        "decision_source": "retry_patch_proposal",
                        "decision_summary": f"patch_id={patch_id}; retry checked: approval stale ({hours_since:.1f}h)",
                        "patch_id_refs": [patch_id],
                        "tags": ["patch_proposal", "retry", "stale"],
                    })
                except Exception:
                    pass
                return _result(command=cmd, status="error", project_name=found_key, summary=f"Approval expired; {hours_since:.1f}h since approval. Re-approve required.", payload={"ready_for_apply": False, "error": "approval_stale", "hours_since_approval": round(hours_since, 1), "patch_id": patch_id, "staleness_hours": APPROVAL_STALENESS_HOURS})
            change_type = str(found.get("change_type") or "").strip().lower()
            payload_ok = change_type == "diff_patch" and found.get("patch_payload", {}).get("target_relative_path") and found.get("patch_payload", {}).get("search_text")
            return _result(command=cmd, status="ok", project_name=found_key, summary="Ready for apply.", payload={"ready_for_apply": True, "patch_id": patch_id, "effective_status": effective_status, "hours_since_approval": round(hours_since, 1), "patch_payload_valid": payload_ok, "patch_proposal": {k: v for k, v in found.items() if k != "patch_payload"}})
        except Exception as e:
            fallback = {"ready_for_apply": False, "patch_id": kwargs.get("patch_id", ""), "error": str(e)}
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload=fallback)

    if cmd == "approval_trace":
        try:
            approval_id = (kwargs.get("approval_id") or "").strip() or None
            patch_id = (kwargs.get("patch_id") or "").strip() or None
            from NEXUS.approval_registry import read_approval_journal_tail
            from NEXUS.patch_proposal_registry import find_proposal_and_project, get_proposal_effective_status, get_latest_resolution_for_patch, read_patch_proposal_resolution_tail
            from NEXUS.approval_staleness import evaluate_approval_staleness, evaluate_proposal_approval_staleness
            trace: dict[str, Any] = {"approval": None, "patch_proposal": None, "resolution": None, "linked_approvals": [], "is_stale": False, "hours_since": 0.0}
            if approval_id:
                for proj_key in PROJECTS:
                    p = PROJECTS[proj_key].get("path")
                    if p:
                        tail = read_approval_journal_tail(project_path=p, n=200)
                        for r in tail:
                            if r.get("approval_id") == approval_id:
                                trace["approval"] = {**r, "_project": proj_key}
                                is_stale, hours = evaluate_approval_staleness(r)
                                trace["is_stale"] = is_stale
                                trace["hours_since"] = hours
                                ctx = r.get("context") or {}
                                pid = ctx.get("patch_id")
                                if pid:
                                    prop, prop_path, prop_key = find_proposal_and_project(pid)
                                    if prop and prop_path:
                                        trace["patch_proposal"] = {**prop, "_project": prop_key}
                                        trace["resolution"] = get_latest_resolution_for_patch(prop_path, pid)
                                        if trace["resolution"]:
                                            ps, ph = evaluate_proposal_approval_staleness(trace["resolution"])
                                            trace["proposal_stale"] = ps
                                            trace["proposal_hours_since"] = ph
                                break
                    if trace["approval"]:
                        break
                return _result(command=cmd, status="ok", project_name=trace.get("approval", {}).get("_project"), summary="approval_trace" if trace["approval"] else "approval_not_found", payload=trace)
            if patch_id:
                prop, prop_path, prop_key = find_proposal_and_project(patch_id)
                if prop and prop_path:
                    trace["patch_proposal"] = {**prop, "_project": prop_key}
                    trace["resolution"] = get_latest_resolution_for_patch(prop_path, patch_id)
                    effective_status, _ = get_proposal_effective_status(prop_path, patch_id)
                    trace["effective_status"] = effective_status
                    if trace["resolution"]:
                        is_stale, hours = evaluate_proposal_approval_staleness(trace["resolution"])
                        trace["is_stale"] = is_stale
                        trace["hours_since"] = hours
                        try:
                            from NEXUS.approval_lifecycle import evaluate_resolution_lifecycle
                            trace["lifecycle"] = evaluate_resolution_lifecycle(trace["resolution"])
                        except Exception:
                            trace["lifecycle"] = {}
                    aid = trace["resolution"].get("approval_id") if trace["resolution"] else None
                    if aid:
                        for proj_key in PROJECTS:
                            p = PROJECTS[proj_key].get("path")
                            if p:
                                atail = read_approval_journal_tail(project_path=p, n=100)
                                for ar in atail:
                                    if ar.get("approval_id") == aid:
                                        trace["approval"] = {**ar, "_project": proj_key}
                                        break
                            if trace["approval"]:
                                break
                return _result(command=cmd, status="ok", project_name=prop_key if prop else None, summary="patch_trace" if prop else "patch_not_found", payload=trace)
            return _result(command=cmd, status="error", project_name=None, summary="approval_id or patch_id required.", payload={"error": "approval_id or patch_id required."})
        except Exception as e:
            fallback = {"approval": None, "patch_proposal": None, "resolution": None, "linked_approvals": [], "is_stale": False, "error": str(e)}
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload=fallback)

    if cmd == "approval_lifecycle_status":
        try:
            approval_id = (kwargs.get("approval_id") or "").strip() or None
            patch_id = (kwargs.get("patch_id") or "").strip() or None
            from NEXUS.approval_summary import build_approval_summary_safe
            from NEXUS.approval_lifecycle import evaluate_approval_lifecycle, evaluate_resolution_lifecycle
            from NEXUS.patch_proposal_registry import find_proposal_and_project, get_proposal_effective_status, get_latest_resolution_for_patch
            summary = build_approval_summary_safe(n_recent=30, n_tail=100)
            lifecycle_items: list[dict[str, Any]] = []
            if approval_id:
                for proj_key in PROJECTS:
                    p = PROJECTS.get(proj_key, {}).get("path")
                    if p:
                        from NEXUS.approval_registry import read_approval_journal_tail
                        tail = read_approval_journal_tail(project_path=p, n=100)
                        for ar in tail:
                            if ar.get("approval_id") == approval_id:
                                lc = evaluate_approval_lifecycle(ar)
                                lifecycle_items.append({**lc, "approval_id": approval_id, "project": proj_key})
                                break
                    if lifecycle_items:
                        break
            elif patch_id:
                prop, prop_path, prop_key = find_proposal_and_project(patch_id)
                if prop and prop_path:
                    effective, resolution = get_proposal_effective_status(project_path=prop_path, patch_id=patch_id)
                    lc = evaluate_resolution_lifecycle(resolution) if resolution else {"approval_lifecycle_status": "unknown", "lifecycle_next_step": "No resolution yet."}
                    lifecycle_items.append({**lc, "patch_id": patch_id, "project": prop_key, "effective_status": effective})
            else:
                for ar in summary.get("recent_approvals", [])[:10]:
                    if str(ar.get("status") or "").strip().lower() == "approved":
                        lc = evaluate_approval_lifecycle(ar)
                        lifecycle_items.append({**lc, "approval_id": ar.get("approval_id"), "project": ar.get("_project")})
            payload = {
                "approval_lifecycle_status": lifecycle_items[0].get("approval_lifecycle_status") if lifecycle_items else "unknown",
                "lifecycle_items": lifecycle_items,
                "reapproval_required_count": summary.get("reapproval_required_count", 0),
                "approval_summary": summary,
            }
            summary_line = f"lifecycle={payload['approval_lifecycle_status']}; reapproval_required={payload['reapproval_required_count']}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=payload)
        except Exception as e:
            fallback = {"approval_lifecycle_status": "unknown", "lifecycle_items": [], "reapproval_required_count": 0, "error": str(e)}
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload=fallback)

    if cmd == "reapproval_status":
        try:
            from NEXUS.approval_summary import build_approval_summary_safe
            from NEXUS.approval_lifecycle import get_reapproval_required_count
            summary = build_approval_summary_safe(n_recent=20, n_tail=100)
            reapproval_count = summary.get("reapproval_required_count", 0)
            items: list[dict[str, Any]] = []
            for proj_key in PROJECTS:
                path = PROJECTS.get(proj_key, {}).get("path")
                if not path:
                    continue
                from NEXUS.patch_proposal_registry import read_patch_proposal_resolution_tail
                tail = read_patch_proposal_resolution_tail(project_path=path, n=50)
                for r in tail:
                    if str(r.get("new_status") or "").strip().lower() != "approved_pending_apply":
                        continue
                    from NEXUS.approval_lifecycle import evaluate_resolution_lifecycle
                    lc = evaluate_resolution_lifecycle(r)
                    if lc.get("reapproval_required"):
                        items.append({"patch_id": r.get("patch_id"), "project": proj_key, "lifecycle": lc})
            payload = {"reapproval_required_count": reapproval_count, "items_requiring_reapproval": items[:20], "approval_summary": summary}
            summary_line = f"reapproval_required={reapproval_count}; items={len(items)}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=payload)
        except Exception as e:
            fallback = {"reapproval_required_count": 0, "items_requiring_reapproval": [], "error": str(e)}
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload=fallback)

    if cmd == "retry_after_expiry_status":
        try:
            patch_id = (kwargs.get("patch_id") or "").strip() or None
            from NEXUS.approval_lifecycle import evaluate_resolution_lifecycle
            from NEXUS.patch_proposal_registry import find_proposal_and_project, get_proposal_effective_status, get_latest_resolution_for_patch
            if not patch_id:
                return _result(command=cmd, status="error", project_name=proj_name, summary="patch_id required.", payload={"retry_ready": False, "error": "patch_id required."})
            prop, prop_path, prop_key = find_proposal_and_project(patch_id)
            if not prop or not prop_path:
                return _result(command=cmd, status="error", project_name=proj_name, summary="Patch not found.", payload={"retry_ready": False, "patch_id": patch_id})
            effective, resolution = get_proposal_effective_status(project_path=prop_path, patch_id=patch_id)
            if effective != "approved_pending_apply":
                return _result(command=cmd, status="ok", project_name=prop_key, summary=f"Status={effective}; retry not applicable.", payload={"retry_ready": False, "effective_status": effective, "lifecycle": {"lifecycle_next_step": f"Proposal status is {effective}; retry applies only to approved_pending_apply."}})
            lc = evaluate_resolution_lifecycle(resolution)
            retry_ready = lc.get("retry_after_expiry_ready", False)
            payload = {"retry_ready": retry_ready, "patch_id": patch_id, "effective_status": effective, "lifecycle": lc}
            summary_line = f"retry_ready={retry_ready}; {lc.get('lifecycle_next_step', '')[:80]}"
            return _result(command=cmd, status="ok", project_name=prop_key, summary=summary_line, payload=payload)
        except Exception as e:
            fallback = {"retry_ready": False, "patch_id": kwargs.get("patch_id", ""), "error": str(e)}
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload=fallback)

    if cmd in ("release_readiness", "operator_release_summary"):
        try:
            from NEXUS.release_readiness import build_release_readiness_safe, build_operator_release_summary
            if cmd == "operator_release_summary":
                data = build_operator_release_summary(project_name=proj_name)
            else:
                data = build_release_readiness_safe(project_name=proj_name)
            status_val = data.get("release_readiness_status", "error_fallback")
            summary_line = f"release_readiness={status_val}; blockers={len(data.get('critical_blockers', []))}; review_items={len(data.get('review_items', []))}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=data)
        except Exception as e:
            fallback = {
                "release_readiness_status": "error_fallback",
                "project_name": proj_name,
                "product_status": "unknown",
                "approval_status": "unknown",
                "execution_environment_status": "unknown",
                "patch_status": "unknown",
                "autonomy_status": "unknown",
                "helix_status": "unknown",
                "critical_blockers": [str(e)],
                "review_items": [],
                "readiness_reason": str(e),
                "ready_for_operator_release": False,
                "trace_links_present": {"approval_linked": False, "patch_linked": False, "autonomy_linked": False, "product_linked": False, "helix_linked": False},
                "generated_at": "",
                "error": str(e),
            }
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload=fallback)

    # Phase 40: runtime isolation (read-only; no execution)
    if cmd in ("runtime_isolation_status", "sandbox_posture"):
        try:
            from NEXUS.runtime_isolation import build_runtime_isolation_posture_safe
            dash = build_registry_dashboard_summary()
            exec_env = dash.get("execution_environment_summary") or {}
            data = build_runtime_isolation_posture_safe(
                execution_environment_summary=exec_env,
            )
            iso = data.get("isolation_posture", "unknown")
            summary_line = f"isolation_posture={iso}; file={data.get('file_scope_status')}; network={data.get('network_scope_status')}"
            return _result(command=cmd, status="ok", project_name=None, summary=summary_line, payload=data)
        except Exception as e:
            fallback = {
                "isolation_posture": "error_fallback",
                "file_scope_status": "unknown",
                "network_scope_status": "unknown",
                "secret_scope_status": "unknown",
                "connector_scope_status": "unknown",
                "mutation_scope_status": "unknown",
                "rollback_posture": "unknown",
                "isolation_reason": str(e),
                "runtime_restrictions": [],
                "allowed_execution_domains": [],
                "blocked_execution_domains": [],
                "destructive_risk_posture": "unknown",
                "generated_at": "",
                "error": str(e),
            }
            return _result(command=cmd, status="error", project_name=None, summary=str(e), payload=fallback)

    if cmd == "artifact_trace":
        try:
            from NEXUS.cross_artifact_trace import build_cross_artifact_trace_safe
            data = build_cross_artifact_trace_safe(project_name=proj_name, project_path=path)
            status_val = data.get("trace_status", "error_fallback")
            summary_line = f"trace_status={status_val}; links={sum(1 for v in (data.get('link_completeness') or {}).values() if v)}; missing={len(data.get('missing_links', []))}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=data)
        except Exception as e:
            from NEXUS.cross_artifact_trace import _fallback_trace
            from datetime import datetime
            fallback = _fallback_trace(datetime.now().isoformat(), str(e), proj_name)
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload=fallback)

    if cmd == "candidate_review_status":
        try:
            from NEXUS.patch_proposal_summary import build_patch_proposal_summary_safe
            from NEXUS.candidate_review_workflow import evaluate_candidate_review_readiness
            summary = build_patch_proposal_summary_safe(n_recent=30, n_tail=100)
            proposals = summary.get("recent_proposals", [])
            ready_count = 0
            not_ready_count = 0
            by_readiness: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
            candidates: list[dict[str, Any]] = []
            for p in proposals[:20]:
                pn = p.get("_project") or p.get("project_name") or ""
                effective = p.get("effective_status") or p.get("status") or "proposed"
                if effective not in ("proposed", "approval_required"):
                    continue
                rev = evaluate_candidate_review_readiness(p)
                rs = rev.get("review_status", "not_ready_for_review")
                rr = rev.get("review_readiness", "low")
                by_readiness[rr] = by_readiness.get(rr, 0) + 1
                if rs == "ready_for_review":
                    ready_count += 1
                else:
                    not_ready_count += 1
                candidates.append({
                    "patch_id": p.get("patch_id"),
                    "project": pn,
                    "effective_status": effective,
                    "review_status": rs,
                    "review_readiness": rr,
                    "review_reason": rev.get("review_reason", "")[:300],
                    "next_step_recommendation": rev.get("next_step_recommendation", "")[:200],
                })
            payload = {
                "ready_for_review_count": ready_count,
                "not_ready_for_review_count": not_ready_count,
                "by_readiness": by_readiness,
                "candidates": candidates,
                "patch_proposal_summary": summary,
            }
            summary_line = f"ready={ready_count}; not_ready={not_ready_count}; by_readiness={by_readiness}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=payload)
        except Exception as e:
            fallback = {
                "ready_for_review_count": 0,
                "not_ready_for_review_count": 0,
                "by_readiness": {"high": 0, "medium": 0, "low": 0},
                "candidates": [],
                "error": str(e),
            }
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload=fallback)

    if cmd == "review_candidate":
        try:
            patch_id = (kwargs.get("patch_id") or "").strip() or None
            review_outcome = (kwargs.get("review_outcome") or "reviewed").strip().lower()
            reviewer_notes = (kwargs.get("reviewer_notes") or "").strip()[:1000]
            followup_actions = kwargs.get("followup_actions")
            if isinstance(followup_actions, str):
                followup_actions = [x.strip() for x in followup_actions.split(",") if x.strip()][:10]
            elif isinstance(followup_actions, list):
                followup_actions = [str(x)[:200] for x in followup_actions[:10]]
            else:
                followup_actions = []
            if not patch_id:
                return _result(command=cmd, status="error", project_name=proj_name, summary="patch_id required.", payload={"review_id": "", "error": "patch_id required."})
            from NEXUS.patch_proposal_registry import find_proposal_and_project, normalize_patch_proposal
            from NEXUS.candidate_review_registry import append_candidate_review_record_safe, normalize_review_record
            from NEXUS.candidate_review_workflow import evaluate_candidate_review_readiness
            found, found_path, found_key = find_proposal_and_project(patch_id)
            if not found or not found_path:
                return _result(command=cmd, status="error", project_name=proj_name, summary="Patch proposal not found.", payload={"review_id": "", "error": "Patch proposal not found.", "patch_id": patch_id})
            norm = normalize_patch_proposal(found)
            rev = evaluate_candidate_review_readiness(norm)
            if review_outcome not in ("reviewed", "changes_requested", "approved_for_approval"):
                review_outcome = "reviewed"
            record = {
                "patch_id": patch_id,
                "project_name": found_key or norm.get("project_name", ""),
                "review_status": review_outcome,
                "review_reason": rev.get("review_reason", "")[:300],
                "review_readiness": rev.get("review_readiness", "medium"),
                "review_requirements_met": rev.get("review_requirements_met", [])[:10],
                "review_requirements_missing": rev.get("review_requirements_missing", [])[:10],
                "reviewer_notes": reviewer_notes,
                "review_outcome": review_outcome,
                "followup_actions": followup_actions,
                "human_review_required": False,
                "approval_progression_ready": review_outcome == "approved_for_approval" and rev.get("approval_progression_ready", False),
            }
            normalized_record = normalize_review_record(record)
            review_id = normalized_record.get("review_id", "")
            written = append_candidate_review_record_safe(project_path=found_path, record=record)
            if written:
                try:
                    from NEXUS.learning_writer import append_learning_record_safe
                    append_learning_record_safe(project_path=found_path, record={
                        "record_type": "candidate_review_recorded",
                        "project_name": found_key or "",
                        "workflow_stage": "candidate_review",
                        "decision_source": "review_candidate",
                        "decision_type": "review_recorded",
                        "decision_summary": f"patch_id={patch_id}; review_outcome={review_outcome}; review_id={review_id}",
                        "downstream_effects": {"patch_id": patch_id, "review_id": review_id, "review_status": review_outcome, "review_readiness": rev.get("review_readiness"), "approval_progression_ready": record.get("approval_progression_ready")},
                        "patch_id_refs": [patch_id],
                        "tags": ["patch_proposal", "candidate_review"],
                    })
                except Exception:
                    pass
            payload = {"review_id": review_id, "patch_id": patch_id, "review_outcome": review_outcome, "written": bool(written), "record": normalized_record}
            return _result(command=cmd, status="ok", project_name=found_key, summary=f"review_recorded; outcome={review_outcome}", payload=payload)
        except Exception as e:
            fallback = {"review_id": "", "patch_id": kwargs.get("patch_id", ""), "error": str(e)}
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload=fallback)

    if cmd == "candidate_review_details":
        try:
            patch_id = (kwargs.get("patch_id") or "").strip() or None
            proj_path = path
            if not proj_path and proj_name:
                from NEXUS.registry import PROJECTS as _PROJECTS
                key = str(proj_name).strip().lower()
                if key in _PROJECTS:
                    proj_path = _PROJECTS[key].get("path")
            from NEXUS.patch_proposal_registry import find_proposal_and_project, normalize_patch_proposal, get_proposal_effective_status
            from NEXUS.candidate_review_registry import get_latest_review_for_patch, read_candidate_review_journal_tail
            from NEXUS.candidate_review_workflow import evaluate_candidate_review_readiness
            if patch_id:
                found, found_path, found_key = find_proposal_and_project(patch_id)
                if found and found_path:
                    norm = normalize_patch_proposal(found)
                    rev = evaluate_candidate_review_readiness(norm)
                    effective_status, resolution = get_proposal_effective_status(project_path=found_path, patch_id=patch_id)
                    latest_review = get_latest_review_for_patch(project_path=found_path, patch_id=patch_id)
                    display_status = latest_review.get("review_status") if latest_review else rev.get("review_status")
                    payload = {
                        "patch_proposal": {k: v for k, v in norm.items() if k != "patch_payload"},
                        "patch_id": patch_id,
                        "project": found_key,
                        "effective_status": effective_status,
                        "review_readiness": rev,
                        "display_review_status": display_status,
                        "latest_review_record": latest_review,
                        "resolution": resolution,
                    }
                    return _result(command=cmd, status="ok", project_name=found_key, summary=f"patch_id={patch_id}; review_status={display_status}", payload=payload)
            if proj_path:
                tail = read_candidate_review_journal_tail(project_path=proj_path, n=30)
                payload = {"recent_reviews": tail[:20], "project": proj_name}
                return _result(command=cmd, status="ok", project_name=proj_name, summary=f"recent_reviews={len(payload['recent_reviews'])}", payload=payload)
            return _result(command=cmd, status="error", project_name=proj_name, summary="patch_id or project_name required.", payload={"error": "patch_id or project_name required."})
        except Exception as e:
            fallback = {"patch_proposal": None, "review_readiness": None, "latest_review_record": None, "error": str(e)}
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload=fallback)

    if cmd == "health":
        try:
            if path:
                loaded = load_project_state(path)
                if "load_error" in loaded:
                    session_summary = {}
                    policy_summary = {}
                else:
                    session_summary = loaded.get("execution_session_summary") or {}
                    policy_summary = loaded.get("execution_policy_summary") or {}
                health_payload = loaded.get("system_health_summary")
                if health_payload:
                    return _result(
                        command=cmd,
                        status="ok",
                        project_name=proj_name,
                        summary=health_payload.get("overall_status", "unknown"),
                        payload=health_payload,
                    )
                result = evaluate_system_health(
                    project_path=path,
                    run_id=loaded.get("run_id"),
                    execution_session_summary=session_summary,
                    execution_policy_summary=policy_summary,
                    agent_routing_report_path=loaded.get("agent_routing_report_path"),
                )
            else:
                result = evaluate_system_health(project_path=None)
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=result.get("overall_status", "unknown"),
                payload=result,
            )
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "latest_session":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(
                    command=cmd,
                    status="error",
                    project_name=proj_name,
                    summary=loaded.get("load_error", "Failed to load state."),
                    payload=loaded,
                )
            session = loaded.get("execution_session_summary") or {}
            run_id = loaded.get("run_id")
            payload = {"run_id": run_id, "execution_session_summary": session}
            summary = f"run_id={run_id}; status={session.get('status', 'unknown')}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary, payload=payload)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "ledger_tail":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={"entries": []},
            )
        try:
            entries = read_ledger_tail(path, n=n)
            ledger_path = get_ledger_path(path)
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=f"Last {len(entries)} entries.",
                payload={"ledger_path": ledger_path, "count": len(entries), "entries": entries},
            )
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"entries": [], "error": str(e)})

    if cmd == "project_summary":
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            loaded = load_project_state(path)
            if "load_error" in loaded:
                return _result(
                    command=cmd,
                    status="error",
                    project_name=proj_name,
                    summary=loaded.get("load_error", "Failed to load state."),
                    payload=loaded,
                )
            payload = {
                "active_project": loaded.get("active_project"),
                "project_path": path,
                "saved_at": loaded.get("saved_at"),
                "run_id": loaded.get("run_id"),
                "execution_ledger_path": loaded.get("execution_ledger_path"),
                "execution_package_id": loaded.get("execution_package_id"),
                "execution_package_path": loaded.get("execution_package_path"),
                "coder_output_path": loaded.get("coder_output_path"),
                "execution_report_path": loaded.get("execution_report_path"),
                "full_automation_report_path": loaded.get("full_automation_report_path"),
                "persistent_state_path": loaded.get("persistent_state_path"),
                "system_health_report_path": loaded.get("system_health_report_path"),
            }
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=f"Project {loaded.get('active_project', proj_name)} at {path}",
                payload=payload,
            )
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd in (
        "project_autopilot_start",
        "project_autopilot_status",
        "project_autopilot_pause",
        "project_autopilot_resume",
        "project_autopilot_stop",
    ):
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            from NEXUS.project_autopilot import (
                get_project_autopilot_status,
                pause_project_autopilot,
                resume_project_autopilot,
                start_project_autopilot,
                stop_project_autopilot,
            )

            if cmd == "project_autopilot_start":
                result = start_project_autopilot(
                    project_path=path,
                    project_name=proj_name or "",
                    iteration_limit=kwargs.get("iteration_limit"),
                    autopilot_mode=kwargs.get("autopilot_mode"),
                )
            elif cmd == "project_autopilot_pause":
                result = pause_project_autopilot(project_path=path, project_name=proj_name or "")
            elif cmd == "project_autopilot_resume":
                result = resume_project_autopilot(project_path=path, project_name=proj_name or "")
            elif cmd == "project_autopilot_stop":
                result = stop_project_autopilot(project_path=path, project_name=proj_name or "")
            else:
                result = get_project_autopilot_status(project_path=path, project_name=proj_name or "")

            session = result.get("session") if isinstance(result.get("session"), dict) else {}
            summary_line = (
                f"autopilot_status={session.get('autopilot_status')}; "
                f"iteration={session.get('autopilot_iteration_count')}/{session.get('autopilot_iteration_limit')}; "
                f"next_action={session.get('autopilot_next_action')}"
            )
            return _result(
                command=cmd,
                status="ok" if result.get("status") == "ok" else "error",
                project_name=proj_name,
                summary=summary_line if result.get("status") == "ok" else str(result.get("reason") or "Autopilot command failed."),
                payload={
                    "status": result.get("status"),
                    "reason": result.get("reason"),
                    "project_path": path,
                    "autopilot": session,
                },
            )
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd in ("project_autonomy_mode_set", "project_autonomy_mode_status", "project_routing_status"):
        if not path:
            return _result(
                command=cmd,
                status="error",
                project_name=proj_name,
                summary="Project path or project_name required.",
                payload={},
            )
        try:
            from NEXUS.autonomy_modes import build_autonomy_mode_state, normalize_autonomy_mode
            from NEXUS.execution_package_registry import read_execution_package
            from NEXUS.project_routing import build_project_routing_decision

            loaded = load_project_state(path)
            if not isinstance(loaded, dict) or loaded.get("load_error"):
                reason = str((loaded or {}).get("load_error") or "Failed to load project state.")
                return _result(command=cmd, status="error", project_name=proj_name, summary=reason, payload={"error": reason})

            package_id = str(loaded.get("execution_package_id") or loaded.get("autopilot_last_package_id") or "")
            active_package = read_execution_package(project_path=path, package_id=package_id) if package_id else None

            if cmd == "project_autonomy_mode_set":
                requested_mode = normalize_autonomy_mode(kwargs.get("autonomy_mode"))
                reason = str(kwargs.get("reason") or f"Operator set autonomy mode to {requested_mode}.").strip()
                mode_state = build_autonomy_mode_state(mode=requested_mode, reason=reason)
                routing = build_project_routing_decision(
                    project_key=proj_name or "",
                    state={**loaded, **mode_state},
                    active_package=active_package,
                    autonomy_mode=requested_mode,
                )
                update_project_state_fields(
                    path,
                    **mode_state,
                    project_routing_status=routing.get("routing_status"),
                    project_routing_result=routing,
                )
                return _result(
                    command=cmd,
                    status="ok",
                    project_name=proj_name,
                    summary=f"autonomy_mode={requested_mode}; routing_status={routing.get('routing_status')}",
                    payload={
                        "project_path": path,
                        "autonomy_mode_state": mode_state,
                        "project_routing": routing,
                    },
                )

            if cmd == "project_autonomy_mode_status":
                current_mode = normalize_autonomy_mode(loaded.get("autonomy_mode"))
                mode_state = {
                    **build_autonomy_mode_state(mode=current_mode, reason=loaded.get("autonomy_mode_reason")),
                    "autonomy_mode_status": loaded.get("autonomy_mode_status") or "active",
                    "allowed_actions": list(loaded.get("allowed_actions") or []),
                    "blocked_actions": list(loaded.get("blocked_actions") or []),
                    "escalation_threshold": loaded.get("escalation_threshold") or build_autonomy_mode_state(mode=current_mode).get("escalation_threshold"),
                    "approval_required_actions": list(loaded.get("approval_required_actions") or []),
                }
                return _result(
                    command=cmd,
                    status="ok",
                    project_name=proj_name,
                    summary=f"autonomy_mode={mode_state.get('autonomy_mode')}; status={mode_state.get('autonomy_mode_status')}",
                    payload={"project_path": path, "autonomy_mode_state": mode_state},
                )

            routing = build_project_routing_decision(
                project_key=proj_name or "",
                state=loaded,
                active_package=active_package,
                autonomy_mode=loaded.get("autonomy_mode"),
            )
            stored_status = str(loaded.get("project_routing_status") or routing.get("routing_status") or "idle")
            payload = {
                "project_path": path,
                "project_routing_status": stored_status,
                "project_routing": routing,
            }
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=f"routing_status={stored_status}; action={routing.get('selected_action')}",
                payload=payload,
            )
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    return _result(command=cmd, status="error", summary="Not implemented.", payload={})
