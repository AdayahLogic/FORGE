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
) -> str:
    state_file = get_project_state_file(project_path)

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
    }

    payload = normalize_display_data(payload)

    state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(state_file)