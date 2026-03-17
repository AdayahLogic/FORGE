"""
NEXUS controlled continuous autonomy.

One bounded autonomous run per invocation; uses guardrails and existing launcher.
No infinite loops, no background scheduling, no recursion.
"""

from __future__ import annotations

from typing import Any

from NEXUS.logging_engine import log_system_event


def build_autonomy_result(
    *,
    autonomy_status: str = "idle",
    autonomy_action: str = "none",
    autonomy_reason: str = "",
    target_project: str | None = None,
    autonomous_run_started: bool = False,
    bounded_operation: bool = True,
) -> dict[str, Any]:
    """
    Build a stable autonomy result dict.

    Returns: autonomy_status, autonomy_action, autonomy_reason, target_project,
    autonomous_run_started, bounded_operation.
    """
    return {
        "autonomy_status": autonomy_status,
        "autonomy_action": autonomy_action,
        "autonomy_reason": autonomy_reason or "No autonomous run.",
        "target_project": target_project,
        "autonomous_run_started": autonomous_run_started,
        "bounded_operation": bounded_operation,
    }


def build_autonomy_result_safe(
    reexecution_result: dict[str, Any] | None = None,
    studio_driver_result: dict[str, Any] | None = None,
    guardrail_result: dict[str, Any] | None = None,
    launch_result: dict[str, Any] | None = None,
    source: str = "project",
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Build autonomy result from guardrail + launch/reexecution/driver; never raises.
    Does not perform execution.
    """
    try:
        gr = guardrail_result or {}
        if not gr.get("launch_allowed", True):
            return build_autonomy_result(
                autonomy_status="blocked" if gr.get("guardrail_status") == "blocked" else "idle",
                autonomy_action="defer" if gr.get("state_repair_recommended") else "stop",
                autonomy_reason=gr.get("guardrail_reason") or "Guardrails did not allow launch.",
                target_project=kwargs.get("target_project"),
                autonomous_run_started=False,
                bounded_operation=True,
            )
        lr = launch_result or {}
        if lr.get("execution_started"):
            return build_autonomy_result(
                autonomy_status="ran",
                autonomy_action=lr.get("launch_action") or "launch_project_cycle",
                autonomy_reason=lr.get("launch_reason") or "Autonomous run completed.",
                target_project=lr.get("target_project") or kwargs.get("target_project"),
                autonomous_run_started=True,
                bounded_operation=True,
            )
        if source == "project" and reexecution_result and not reexecution_result.get("run_permitted"):
            return build_autonomy_result(
                autonomy_status="idle",
                autonomy_action=reexecution_result.get("reexecution_action") or "defer",
                autonomy_reason=reexecution_result.get("reexecution_reason") or "Reexecution not permitted.",
                target_project=kwargs.get("target_project"),
                autonomous_run_started=False,
                bounded_operation=True,
            )
        if source == "studio" and studio_driver_result and not studio_driver_result.get("execution_permitted"):
            return build_autonomy_result(
                autonomy_status="idle",
                autonomy_action=studio_driver_result.get("driver_action") or "defer",
                autonomy_reason=studio_driver_result.get("driver_reason") or "Studio driver did not permit.",
                target_project=studio_driver_result.get("target_project"),
                autonomous_run_started=False,
                bounded_operation=True,
            )
        return build_autonomy_result(
            autonomy_status=kwargs.get("autonomy_status", "idle"),
            autonomy_action=kwargs.get("autonomy_action", "none"),
            autonomy_reason=kwargs.get("autonomy_reason", "No autonomous run."),
            target_project=kwargs.get("target_project"),
            autonomous_run_started=kwargs.get("autonomous_run_started", False),
            bounded_operation=True,
        )
    except Exception:
        return build_autonomy_result(
            autonomy_status="error_fallback",
            autonomy_action="stop",
            autonomy_reason="Autonomy result build failed.",
            target_project=None,
            autonomous_run_started=False,
            bounded_operation=True,
        )


def run_project_autonomy(
    project_path: str,
    project_name: str,
    project_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    One bounded autonomy run for the project: evaluate guardrails, then if allowed
    call launcher once. Persist autonomy_result and guardrail_result on project state.
    """
    from NEXUS.project_state import load_project_state, update_project_state_fields
    from NEXUS.production_guardrails import evaluate_guardrails_safe
    from NEXUS.autonomous_launcher import launch_project_cycle

    loaded = project_state if project_state is not None else load_project_state(project_path)
    if loaded.get("load_error"):
        log_system_event(
            project=project_name,
            subsystem="continuous_autonomy",
            action="run_project_autonomy",
            status="error",
            reason=loaded.get("load_error", "Failed to load state."),
        )
        result = build_autonomy_result_safe(
            autonomy_status="error_fallback",
            autonomy_reason=loaded.get("load_error", "Failed to load state."),
        )
        try:
            update_project_state_fields(
                project_path,
                autonomy_status=result.get("autonomy_status"),
                autonomy_result=result,
                guardrail_status="error_fallback",
                guardrail_result={"guardrail_reason": "Load error."},
            )
        except Exception:
            pass
        return result

    rex = loaded.get("reexecution_result") or {}
    qe = loaded.get("review_queue_entry") or {}
    rec = loaded.get("recovery_result") or {}
    gr = evaluate_guardrails_safe(
        autonomous_launch=False,
        project_state=loaded,
        review_queue_entry=qe,
        recovery_result=rec,
        reexecution_result=rex,
        target_project=project_name,
        states_by_project={project_name: loaded},
        execution_attempted=True,
    )
    try:
        update_project_state_fields(
            project_path,
            guardrail_status=gr.get("guardrail_status"),
            guardrail_result=gr,
        )
    except Exception:
        pass

    if not gr.get("launch_allowed"):
        log_system_event(
            project=project_name,
            subsystem="continuous_autonomy",
            action="guardrails_blocked",
            status="blocked",
            reason=gr.get("guardrail_reason") or "Guardrails did not allow launch.",
        )
        result = build_autonomy_result_safe(
            guardrail_result=gr,
            target_project=project_name,
            autonomy_status="blocked" if gr.get("guardrail_status") == "blocked" else "idle",
        )
        try:
            update_project_state_fields(
                project_path,
                autonomy_status=result.get("autonomy_status"),
                autonomy_result=result,
            )
        except Exception:
            pass
        return result

    if not rex.get("run_permitted"):
        log_system_event(
            project=project_name,
            subsystem="continuous_autonomy",
            action="reexecution_not_permitted",
            status="idle",
            reason=rex.get("reexecution_reason") or "Reexecution not permitted.",
        )
        result = build_autonomy_result_safe(
            reexecution_result=rex,
            guardrail_result=gr,
            target_project=project_name,
        )
        try:
            update_project_state_fields(
                project_path,
                autonomy_status=result.get("autonomy_status"),
                autonomy_result=result,
            )
        except Exception:
            pass
        return result

    try:
        log_system_event(
            project=project_name,
            subsystem="continuous_autonomy",
            action="launch_project_cycle",
            status="attempt",
            reason="Launching one bounded project cycle.",
        )
        launch_result = launch_project_cycle(
            project_path=project_path,
            project_name=project_name,
            project_state=loaded,
        )
        log_system_event(
            project=project_name,
            subsystem="continuous_autonomy",
            action="launch_project_cycle",
            status="ok" if launch_result.get("execution_started") else "idle",
            reason=launch_result.get("launch_reason") or "",
        )
        result = build_autonomy_result(
            autonomy_status="ran" if launch_result.get("execution_started") else "idle",
            autonomy_action=launch_result.get("launch_action") or "launch_project_cycle",
            autonomy_reason=launch_result.get("launch_reason") or "One bounded run.",
            target_project=launch_result.get("target_project") or project_name,
            autonomous_run_started=bool(launch_result.get("execution_started")),
            bounded_operation=True,
        )
        try:
            update_project_state_fields(
                project_path,
                autonomy_status=result.get("autonomy_status"),
                autonomy_result=result,
            )
        except Exception:
            pass
        return result
    except Exception as e:
        log_system_event(
            project=project_name,
            subsystem="continuous_autonomy",
            action="launch_project_cycle",
            status="error",
            reason=str(e),
        )
        result = build_autonomy_result(
            autonomy_status="error_fallback",
            autonomy_action="stop",
            autonomy_reason=str(e),
            target_project=project_name,
            autonomous_run_started=False,
            bounded_operation=True,
        )
        try:
            update_project_state_fields(
                project_path,
                autonomy_status=result.get("autonomy_status"),
                autonomy_result=result,
            )
        except Exception:
            pass
        return result


def run_studio_autonomy(
    states_by_project: dict[str, dict[str, Any]] | None = None,
    studio_driver_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    One bounded studio-scoped autonomy run: evaluate guardrails, then if allowed
    call launch_studio_cycle once. Persist autonomy_result and guardrail_result on target project.
    """
    from NEXUS.registry import PROJECTS
    from NEXUS.project_state import load_project_state, update_project_state_fields
    from NEXUS.studio_coordinator import build_studio_coordination_summary_safe
    from NEXUS.studio_driver import build_studio_driver_result_safe
    from NEXUS.production_guardrails import evaluate_guardrails_safe
    from NEXUS.autonomous_launcher import launch_studio_cycle

    if states_by_project is None:
        states_by_project = {}
        for key in PROJECTS:
            p = PROJECTS[key].get("path")
            if p:
                states_by_project[key] = load_project_state(p)
    if studio_driver_result is None:
        coord = build_studio_coordination_summary_safe(states_by_project)
        studio_driver_result = build_studio_driver_result_safe(
            studio_coordination_summary=coord,
            states_by_project=states_by_project,
        )

    target = studio_driver_result.get("target_project")
    gr = evaluate_guardrails_safe(
        autonomous_launch=False,
        project_state=(states_by_project or {}).get(target) if target else None,
        studio_driver_result=studio_driver_result,
        target_project=target,
        states_by_project=states_by_project,
        execution_attempted=True,
    )

    if not gr.get("launch_allowed"):
        log_system_event(
            project=target,
            subsystem="continuous_autonomy",
            action="studio_guardrails_blocked",
            status="blocked",
            reason=gr.get("guardrail_reason") or "Guardrails did not allow studio launch.",
        )
        result = build_autonomy_result_safe(
            guardrail_result=gr,
            studio_driver_result=studio_driver_result,
            target_project=target,
        )
        if target:
            path = (PROJECTS.get(target) or {}).get("path")
            if path:
                try:
                    update_project_state_fields(
                        path,
                        autonomy_status=result.get("autonomy_status"),
                        autonomy_result=result,
                        guardrail_status=gr.get("guardrail_status"),
                        guardrail_result=gr,
                    )
                except Exception:
                    pass
        return result

    if not studio_driver_result.get("execution_permitted") or not target:
        log_system_event(
            project=target,
            subsystem="continuous_autonomy",
            action="studio_driver_not_permitted",
            status="idle",
            reason=studio_driver_result.get("driver_reason") or "Studio driver did not permit.",
        )
        result = build_autonomy_result_safe(
            studio_driver_result=studio_driver_result,
            guardrail_result=gr,
            target_project=target,
        )
        if target:
            path = (PROJECTS.get(target) or {}).get("path")
            if path:
                try:
                    update_project_state_fields(
                        path,
                        autonomy_status=result.get("autonomy_status"),
                        autonomy_result=result,
                        guardrail_status=gr.get("guardrail_status"),
                        guardrail_result=gr,
                    )
                except Exception:
                    pass
        return result

    try:
        log_system_event(
            project=target,
            subsystem="continuous_autonomy",
            action="launch_studio_cycle",
            status="attempt",
            reason="Launching one bounded studio cycle.",
        )
        launch_result = launch_studio_cycle(
            states_by_project=states_by_project,
            studio_driver_result=studio_driver_result,
        )
        log_system_event(
            project=target,
            subsystem="continuous_autonomy",
            action="launch_studio_cycle",
            status="ok" if launch_result.get("execution_started") else "idle",
            reason=launch_result.get("launch_reason") or "",
        )
        result = build_autonomy_result(
            autonomy_status="ran" if launch_result.get("execution_started") else "idle",
            autonomy_action=launch_result.get("launch_action") or "launch_studio_cycle",
            autonomy_reason=launch_result.get("launch_reason") or "One bounded studio run.",
            target_project=launch_result.get("target_project") or target,
            autonomous_run_started=bool(launch_result.get("execution_started")),
            bounded_operation=True,
        )
        path = (PROJECTS.get(target) or {}).get("path") if target else None
        if path:
            try:
                update_project_state_fields(
                    path,
                    autonomy_status=result.get("autonomy_status"),
                    autonomy_result=result,
                    guardrail_status=gr.get("guardrail_status"),
                    guardrail_result=gr,
                )
            except Exception:
                pass
        return result
    except Exception as e:
        log_system_event(
            project=target,
            subsystem="continuous_autonomy",
            action="launch_studio_cycle",
            status="error",
            reason=str(e),
        )
        result = build_autonomy_result(
            autonomy_status="error_fallback",
            autonomy_action="stop",
            autonomy_reason=str(e),
            target_project=target,
            autonomous_run_started=False,
            bounded_operation=True,
        )
        if target:
            path = (PROJECTS.get(target) or {}).get("path")
            if path:
                try:
                    update_project_state_fields(
                        path,
                        autonomy_status=result.get("autonomy_status"),
                        autonomy_result=result,
                        guardrail_status=gr.get("guardrail_status"),
                        guardrail_result=gr,
                    )
                except Exception:
                    pass
        return result
