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


SUPPORTED_COMMANDS = frozenset({
    "health",
    "latest_session",
    "ledger_tail",
    "project_summary",
    "registry_status",
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
) -> dict[str, Any]:
    """
    Execute a single studio command and return a normalized result dict.

    Supported commands: health, latest_session, ledger_tail, project_summary, registry_status.
    Result shape: command, status, project_name, summary, payload.
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
