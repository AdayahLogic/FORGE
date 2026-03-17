"""
NEXUS explicit autonomous run launcher.

Performs at most one bounded workflow run when reexecution or studio driver
permits. No daemon, no recursive launch, no background scheduling.
"""

from __future__ import annotations

from typing import Any

AUTONOMOUS_USER_INPUT_PREFIX = "Autonomous cycle (launch): "

# No-recursion guard: block nested autonomous launch from inside an already-launched run.
_in_autonomous_run: bool = False


def build_launch_result(
    *,
    launch_status: str = "not_launched",
    launch_action: str = "none",
    launch_reason: str = "",
    target_project: str | None = None,
    execution_started: bool = False,
    bounded_execution: bool = True,
    source: str = "none",
) -> dict[str, Any]:
    """
    Build a stable launch result dict.

    Returns: launch_status, launch_action, launch_reason, target_project,
    execution_started, bounded_execution, source.
    """
    return {
        "launch_status": launch_status,
        "launch_action": launch_action,
        "launch_reason": launch_reason or "No launch.",
        "target_project": target_project,
        "execution_started": execution_started,
        "bounded_execution": bounded_execution,
        "source": source,
    }


def build_launch_result_safe(
    reexecution_result: dict[str, Any] | None = None,
    studio_driver_result: dict[str, Any] | None = None,
    source: str = "none",
    execution_started: bool = False,
    target_project: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Build launch result from reexecution or studio_driver result; never raises.
    Does not perform execution.
    """
    try:
        if source == "reexecution" and reexecution_result:
            if reexecution_result.get("run_permitted"):
                return build_launch_result(
                    launch_status="launched",
                    launch_action=reexecution_result.get("reexecution_action") or "run_project_cycle",
                    launch_reason=reexecution_result.get("reexecution_reason") or "Reexecution permitted.",
                    target_project=target_project or reexecution_result.get("target_project"),
                    execution_started=execution_started,
                    bounded_execution=True,
                    source="reexecution",
                )
            return build_launch_result(
                launch_status="not_launched",
                launch_action=reexecution_result.get("reexecution_action") or "defer",
                launch_reason=reexecution_result.get("reexecution_reason") or "Reexecution not permitted.",
                target_project=target_project,
                execution_started=False,
                bounded_execution=True,
                source="reexecution",
            )
        if source == "studio_driver" and studio_driver_result:
            if studio_driver_result.get("execution_permitted") and studio_driver_result.get("target_project"):
                return build_launch_result(
                    launch_status="launched",
                    launch_action=studio_driver_result.get("driver_action") or "run_priority_project",
                    launch_reason=studio_driver_result.get("driver_reason") or "Studio driver permitted.",
                    target_project=studio_driver_result.get("target_project"),
                    execution_started=execution_started,
                    bounded_execution=True,
                    source="studio_driver",
                )
            return build_launch_result(
                launch_status="not_launched",
                launch_action=studio_driver_result.get("driver_action") or "defer",
                launch_reason=studio_driver_result.get("driver_reason") or "Studio driver did not permit.",
                target_project=studio_driver_result.get("target_project"),
                execution_started=False,
                bounded_execution=True,
                source="studio_driver",
            )
        return build_launch_result(
            launch_status=kwargs.get("launch_status", "not_launched"),
            launch_action=kwargs.get("launch_action", "none"),
            launch_reason=kwargs.get("launch_reason", "No launch."),
            target_project=kwargs.get("target_project"),
            execution_started=kwargs.get("execution_started", False),
            bounded_execution=True,
            source=kwargs.get("source", "none"),
        )
    except Exception:
        return build_launch_result(
            launch_status="error_fallback",
            launch_action="stop",
            launch_reason="Launch result build failed.",
            target_project=None,
            execution_started=False,
            bounded_execution=True,
            source="none",
        )


def _invoke_workflow_once(project_name: str, project_path: str, source: str) -> dict[str, Any]:
    """
    Build workflow, create state for the project, invoke exactly once.
    Returns launch result with execution_started=True. No recursive launch.
    Sets _in_autonomous_run for the duration so nested launch attempts are blocked.
    """
    global _in_autonomous_run
    from NEXUS.workflow import build_workflow
    from NEXUS.state import StudioState

    _in_autonomous_run = True
    try:
        user_input = f"{AUTONOMOUS_USER_INPUT_PREFIX}{project_name}"
        state = StudioState(user_input=user_input, active_project=project_name, project_path=project_path, autonomous_launch=True)
        workflow = build_workflow()
        workflow.invoke(state)
        return build_launch_result(
            launch_status="launched",
            launch_action="run_project_cycle",
            launch_reason=f"One bounded run completed for {project_name}.",
            target_project=project_name,
            execution_started=True,
            bounded_execution=True,
            source=source,
        )
    finally:
        _in_autonomous_run = False


def _blocked_nested_launch_result() -> dict[str, Any]:
    """Return standard result when nested autonomous launch is blocked."""
    return build_launch_result(
        launch_status="blocked",
        launch_action="stop",
        launch_reason="Nested autonomous launch blocked by no-recursion guard.",
        target_project=None,
        execution_started=False,
        bounded_execution=True,
        source="manual",
    )


def launch_project_cycle(
    project_path: str,
    project_name: str,
    project_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    If reexecution permits, run exactly one workflow cycle for the project.
    Otherwise return not_launched result. At most one run; no recursion.
    Blocks if already inside an autonomous run.
    """
    global _in_autonomous_run
    if _in_autonomous_run:
        return _blocked_nested_launch_result()
    from NEXUS.project_state import load_project_state, update_project_state_fields

    loaded = project_state if project_state is not None else load_project_state(project_path)
    if loaded.get("load_error"):
        return build_launch_result_safe(
            launch_status="error_fallback",
            launch_reason=loaded.get("load_error", "Failed to load state."),
            source="reexecution",
        )
    rex = loaded.get("reexecution_result") or {}
    if not rex.get("run_permitted"):
        result = build_launch_result_safe(
            reexecution_result=rex,
            source="reexecution",
            target_project=project_name,
            execution_started=False,
        )
        return result
    try:
        result = _invoke_workflow_once(project_name, project_path, "reexecution")
        update_project_state_fields(
            project_path,
            launch_status=result.get("launch_status"),
            launch_result=result,
        )
        return result
    except Exception as e:
        result = build_launch_result(
            launch_status="error_fallback",
            launch_action="stop",
            launch_reason=str(e),
            target_project=project_name,
            execution_started=False,
            bounded_execution=True,
            source="reexecution",
        )
        try:
            update_project_state_fields(
                project_path,
                launch_status=result.get("launch_status"),
                launch_result=result,
            )
        except Exception:
            pass
        return result


def launch_studio_cycle(
    states_by_project: dict[str, dict[str, Any]] | None = None,
    studio_driver_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    If studio driver permits, run exactly one workflow cycle for the target project.
    Otherwise return not_launched result. At most one run; no recursion.
    Blocks if already inside an autonomous run.
    """
    global _in_autonomous_run
    if _in_autonomous_run:
        return _blocked_nested_launch_result()
    from NEXUS.registry import PROJECTS
    from NEXUS.project_state import load_project_state, update_project_state_fields
    from NEXUS.studio_coordinator import build_studio_coordination_summary_safe
    from NEXUS.studio_driver import build_studio_driver_result_safe

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
    if not studio_driver_result.get("execution_permitted") or not studio_driver_result.get("target_project"):
        return build_launch_result_safe(
            studio_driver_result=studio_driver_result,
            source="studio_driver",
            execution_started=False,
        )
    target = studio_driver_result.get("target_project")
    path = (PROJECTS.get(target) or {}).get("path") if target else None
    if not path:
        return build_launch_result_safe(
            launch_status="error_fallback",
            launch_reason=f"No path for target project {target}.",
            source="studio_driver",
        )
    try:
        result = _invoke_workflow_once(target, path, "studio_driver")
        result["launch_action"] = studio_driver_result.get("driver_action") or result.get("launch_action")
        update_project_state_fields(
            path,
            launch_status=result.get("launch_status"),
            launch_result=result,
        )
        return result
    except Exception as e:
        result = build_launch_result(
            launch_status="error_fallback",
            launch_action="stop",
            launch_reason=str(e),
            target_project=target,
            execution_started=False,
            bounded_execution=True,
            source="studio_driver",
        )
        try:
            update_project_state_fields(path, launch_status=result.get("launch_status"), launch_result=result)
        except Exception:
            pass
        return result
