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

from NEXUS.logging_engine import log_system_event

SUPPORTED_COMMANDS = frozenset({
    "health",
    "latest_session",
    "ledger_tail",
    "project_summary",
    "registry_status",
    "dashboard_summary",
    "runtime_targets",
    "runtime_select",
    "dispatch_plan",
    "dispatch_status",
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
    "guardrail_status",
    "runtime_route",
    "model_route",
    "deployment_preflight",
    "operator_snapshot",
    "project_onboard",
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
            summary_line = f"dispatch_status={dispatch_status_val}; result_status={dr_status}; execution_status={dr_exec_status}"
            return _result(
                command=cmd,
                status="ok",
                project_name=proj_name,
                summary=summary_line,
                payload={
                    "dispatch_status": dispatch_status_val,
                    "runtime_target": (dispatch_result_val.get("runtime_target") or dispatch_result_val.get("runtime")),
                    "dispatch_result": {
                        "status": dr_status,
                        "execution_status": dr_exec_status,
                        "message": dispatch_result_val.get("message"),
                    },
                },
            )
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

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
            }
            summary_line = f"autonomy_status={payload.get('autonomy_status')}; autonomous_run_started={payload.get('autonomous_run_started')}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=payload)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

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

    return _result(command=cmd, status="error", summary="Not implemented.", payload={})
