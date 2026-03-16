"""
NEXUS studio command surface.

Small read-focused command layer for routine operations: health, latest_session,
ledger_tail, project_summary, registry_status. Returns normalized result dicts.
No async, no CLI framework; minimal safe changes.
"""

from __future__ import annotations

from typing import Any

from NEXUS.registry import PROJECTS
from NEXUS.project_state import load_project_state
from NEXUS.execution_ledger import get_ledger_path, read_ledger_tail
from NEXUS.system_health import evaluate_system_health
from NEXUS.agent_registry import get_runtime_routable_agents
from NEXUS.tool_registry import list_active_tools, list_planned_tools
from NEXUS.engine_registry import list_active_engines, list_planned_engines
from NEXUS.capability_registry import list_active_capabilities, list_planned_capabilities
from NEXUS.registry_dashboard import build_registry_dashboard_summary
from NEXUS.runtime_target_registry import get_runtime_target_summary
from NEXUS.runtime_target_selector import select_runtime_target


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
