import json
from pathlib import Path
from datetime import datetime

from NEXUS.path_utils import normalize_display_data, to_studio_relative_path


def ensure_state_folder(project_path: str) -> Path:
    base_path = Path(project_path)
    state_path = base_path / "state"
    state_path.mkdir(parents=True, exist_ok=True)
    return state_path


def get_project_state_file(project_path: str) -> Path:
    state_folder = ensure_state_folder(project_path)
    return state_folder / "project_state.json"


def load_project_state(project_path: str) -> dict:
    state_file = get_project_state_file(project_path)

    if not state_file.exists():
        return {}

    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except Exception as e:
        return {
            "load_error": str(e)
        }


def save_project_state(
    project_path: str,
    active_project: str | None,
    notes: str | None,
    architect_plan: dict | None,
    task_queue: list,
    coder_output_path: str | None,
    implementation_file_path: str | None,
    test_report_path: str | None,
    docs_output_path: str | None,
    execution_report_path: str | None,
    workspace_report_path: str | None,
    operator_log_path: str | None,
    supervisor_report_path: str | None,
    supervisor_decision: dict | None,
    autonomous_cycle_report_path: str | None,
    autonomous_cycle_summary: dict | None,
    computer_use_report_path: str | None,
    computer_use_summary: dict | None,
    tool_execution_report_path: str | None,
    tool_execution_summary: dict | None,
    file_modification_report_path: str | None,
    file_modification_summary: dict | None,
    diff_patch_report_path: str | None,
    diff_patch_summary: dict | None,
    agent_routing_report_path: str | None,
    agent_routing_summary: dict | None,
    execution_bridge_report_path: str | None,
    execution_bridge_summary: dict | None,
    engine_registry_report_path: str | None,
    engine_registry_summary: dict | None,
    capability_registry_report_path: str | None,
    capability_registry_summary: dict | None,
    terminal_report_path: str | None,
    terminal_summary: dict | None,
    browser_research_report_path: str | None,
    browser_research_summary: dict | None,
    full_automation_report_path: str | None,
    full_automation_summary: dict | None,
    task_queue_snapshot: list | None = None,
    tool_registry_report_path: str | None = None,
    tool_registry_summary: dict | None = None,
    tool_routing_summary: dict | None = None,
    workspace_boundary_report_path: str | None = None,
    workspace_boundary_summary: dict | None = None,
    path_migration_report_path: str | None = None,
    path_migration_summary: dict | None = None,
    execution_policy_summary: dict | None = None,
    execution_ledger_path: str | None = None,
    run_id: str | None = None,
    execution_session_summary: dict | None = None,
    system_health_summary: dict | None = None,
    system_health_report_path: str | None = None,
    dispatch_plan_summary: dict | None = None,
    dispatch_status: str | None = None,
    dispatch_result: dict | None = None,
    runtime_execution_status: str | None = None,
    automation_status: str | None = None,
    automation_result: dict | None = None,
    agent_selection_summary: dict | None = None,
    governance_status: str | None = None,
    governance_result: dict | None = None,
    project_lifecycle_status: str | None = None,
    project_lifecycle_result: dict | None = None,
    enforcement_status: str | None = None,
    enforcement_result: dict | None = None,
    workflow_route_status: str | None = None,
    workflow_route_reason: str | None = None,
    review_queue_entry: dict | None = None,
    resume_status: str | None = None,
    resume_result: dict | None = None,
    heartbeat_status: str | None = None,
    heartbeat_result: dict | None = None,
    scheduler_status: str | None = None,
    scheduler_result: dict | None = None,
    completion_result: dict | None = None,
    recovery_status: str | None = None,
    recovery_result: dict | None = None,
    reexecution_status: str | None = None,
    reexecution_result: dict | None = None,
    launch_status: str | None = None,
    launch_result: dict | None = None,
    autonomy_status: str | None = None,
    autonomy_result: dict | None = None,
    guardrail_status: str | None = None,
    guardrail_result: dict | None = None,
) -> str:
    state_file = get_project_state_file(project_path)

    # Compact audit summaries (no history arrays; derived from existing results)
    lr = (launch_result or {}) if isinstance(launch_result, dict) else {}
    rr = (recovery_result or {}) if isinstance(recovery_result, dict) else {}
    cr = (completion_result or {}) if isinstance(completion_result, dict) else {}
    last_run_summary = {
        "saved_at": datetime.now().isoformat(),
        "active_project": active_project or "",
        "run_id": run_id or "",
        "runtime_execution_status": runtime_execution_status or (dispatch_result or {}).get("execution_status") if isinstance(dispatch_result, dict) else runtime_execution_status,
        "dispatch_status": dispatch_status or "",
    }
    last_launch_summary = {
        "launch_status": launch_status or lr.get("launch_status") or "none",
        "launch_action": lr.get("launch_action") or "none",
        "launch_reason": lr.get("launch_reason") or "",
        "target_project": lr.get("target_project") or active_project or "",
        "execution_started": bool(lr.get("execution_started")),
        "bounded_execution": bool(lr.get("bounded_execution", True)),
        "source": lr.get("source") or "none",
    }
    last_recovery_summary = {
        "recovery_status": recovery_status or rr.get("recovery_status") or "none",
        "recovery_action": rr.get("recovery_action") or "none",
        "recovery_reason": rr.get("recovery_reason") or "",
        "retry_permitted": bool(rr.get("retry_permitted")),
        "repair_required": bool(rr.get("repair_required")),
        "retry_count_exceeded": bool(rr.get("retry_count_exceeded")),
    }
    last_completion_summary = {
        "completion_status": cr.get("completion_status") or "none",
        "completion_type": cr.get("completion_type") or "none",
        "queue_cleared": bool(cr.get("queue_cleared")),
        "resume_unlocked": bool(cr.get("resume_unlocked")),
        "completion_recorded": bool(cr.get("completion_recorded")),
    }

    payload = {
        "saved_at": datetime.now().isoformat(),
        "active_project": active_project,
        "project_state_file": to_studio_relative_path(str(state_file)),
        "notes": notes,
        "architect_plan": architect_plan,
        "task_queue": task_queue,
        # Explicit snapshot field for the Nexus task queue engine.
        "task_queue_snapshot": task_queue_snapshot or task_queue,
        "coder_output_path": coder_output_path,
        "implementation_file_path": implementation_file_path,
        "test_report_path": test_report_path,
        "docs_output_path": docs_output_path,
        "execution_report_path": execution_report_path,
        "workspace_report_path": workspace_report_path,
        "operator_log_path": operator_log_path,
        "supervisor_report_path": supervisor_report_path,
        "supervisor_decision": supervisor_decision,
        "autonomous_cycle_report_path": autonomous_cycle_report_path,
        "autonomous_cycle_summary": autonomous_cycle_summary,
        "computer_use_report_path": computer_use_report_path,
        "computer_use_summary": computer_use_summary,
        "tool_execution_report_path": tool_execution_report_path,
        "tool_execution_summary": tool_execution_summary,
        "file_modification_report_path": file_modification_report_path,
        "file_modification_summary": file_modification_summary,
        "diff_patch_report_path": diff_patch_report_path,
        "diff_patch_summary": diff_patch_summary,
        "agent_routing_report_path": agent_routing_report_path,
        "agent_routing_summary": agent_routing_summary,
        "execution_bridge_report_path": execution_bridge_report_path,
        "execution_bridge_summary": execution_bridge_summary,
        "engine_registry_report_path": engine_registry_report_path,
        "engine_registry_summary": engine_registry_summary,
        "capability_registry_report_path": capability_registry_report_path,
        "capability_registry_summary": capability_registry_summary,
        "terminal_report_path": terminal_report_path,
        "terminal_summary": terminal_summary,
        "browser_research_report_path": browser_research_report_path,
        "browser_research_summary": browser_research_summary,
        "full_automation_report_path": full_automation_report_path,
        "full_automation_summary": full_automation_summary,
        "tool_registry_report_path": tool_registry_report_path,
        "tool_registry_summary": tool_registry_summary or {},
        "tool_routing_summary": tool_routing_summary or {},
        "workspace_boundary_report_path": workspace_boundary_report_path,
        "workspace_boundary_summary": workspace_boundary_summary or {},
        "path_migration_report_path": path_migration_report_path,
        "path_migration_summary": path_migration_summary or {},
        "execution_policy_summary": execution_policy_summary or {},
        "execution_ledger_path": execution_ledger_path,
        "run_id": run_id,
        "execution_session_summary": execution_session_summary or {},
        "system_health_summary": system_health_summary or {},
        "system_health_report_path": system_health_report_path,
        "dispatch_plan_summary": dispatch_plan_summary or {},
        "dispatch_status": dispatch_status,
        "dispatch_result": dispatch_result or {},
        "runtime_execution_status": runtime_execution_status,
        "automation_status": automation_status,
        "automation_result": automation_result or {},
        "agent_selection_summary": agent_selection_summary or {},
        "governance_status": governance_status,
        "governance_result": governance_result or {},
        "project_lifecycle_status": project_lifecycle_status,
        "project_lifecycle_result": project_lifecycle_result or {},
        "enforcement_status": enforcement_status,
        "enforcement_result": enforcement_result or {},
        "workflow_route_status": workflow_route_status,
        "workflow_route_reason": workflow_route_reason,
        "review_queue_entry": review_queue_entry or {},
        "resume_status": resume_status,
        "resume_result": resume_result or {},
        "heartbeat_status": heartbeat_status,
        "heartbeat_result": heartbeat_result or {},
        "scheduler_status": scheduler_status,
        "scheduler_result": scheduler_result or {},
        "completion_result": completion_result or {},
        "recovery_status": recovery_status,
        "recovery_result": recovery_result or {},
        "reexecution_status": reexecution_status,
        "reexecution_result": reexecution_result or {},
        "launch_status": launch_status,
        "launch_result": launch_result or {},
        "autonomy_status": autonomy_status,
        "autonomy_result": autonomy_result or {},
        "guardrail_status": guardrail_status,
        "guardrail_result": guardrail_result or {},
        "last_run_summary": last_run_summary,
        "last_launch_summary": last_launch_summary,
        "last_recovery_summary": last_recovery_summary,
        "last_completion_summary": last_completion_summary,
    }

    payload = normalize_display_data(payload)

    state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(state_file)


def update_project_state_fields(project_path: str, **fields: object) -> str:
    """
    Update only the given fields in project state. Loads current state, merges
    fields, updates saved_at, and writes back. Minimal update; does not wipe
    unrelated state.
    """
    from datetime import datetime
    loaded = load_project_state(project_path)
    if not isinstance(loaded, dict) or loaded.get("load_error"):
        return ""
    merged = {**loaded, **fields, "saved_at": datetime.now().isoformat()}
    merged = normalize_display_data(merged)
    state_file = get_project_state_file(project_path)
    state_file.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return str(state_file)