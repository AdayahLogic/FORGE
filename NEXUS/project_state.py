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
    execution_package_id: str | None = None,
    execution_package_path: str | None = None,
    runtime_execution_status: str | None = None,
    automation_status: str | None = None,
    automation_result: dict | None = None,
    agent_selection_summary: dict | None = None,
    governance_status: str | None = None,
    governance_result: dict | None = None,
    project_selection_status: str | None = None,
    project_selection_result: dict | None = None,
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
    runtime_router_result: dict | None = None,
    model_router_result: dict | None = None,
    deployment_preflight_result: dict | None = None,
    self_improvement_status: str | None = None,
    self_improvement_result: dict | None = None,
    change_gate_status: str | None = None,
    change_gate_result: dict | None = None,
    regression_status: str | None = None,
    regression_result: dict | None = None,
    prism_status: str | None = None,
    prism_result: dict | None = None,
    last_prism_summary: dict | None = None,
    last_aegis_decision: dict | None = None,
    autopilot_enabled: bool | None = None,
    autopilot_status: str | None = None,
    autopilot_loop_state: str | None = None,
    autopilot_last_run_at: str | None = None,
    autopilot_next_run_at: str | None = None,
    autopilot_current_focus: str | None = None,
    autopilot_requires_operator_review: bool | None = None,
    autopilot_session_id: str | None = None,
    autopilot_project_key: str | None = None,
    autopilot_mode: str | None = None,
    autopilot_iteration_count: int | None = None,
    autopilot_iteration_limit: int | None = None,
    autopilot_started_at: str | None = None,
    autopilot_updated_at: str | None = None,
    autopilot_last_package_id: str | None = None,
    autopilot_last_result: dict | None = None,
    autopilot_next_action: str | None = None,
    autopilot_stop_reason: str | None = None,
    autopilot_escalation_reason: str | None = None,
    autopilot_progress_summary: dict | None = None,
    autopilot_retry_count: int | None = None,
    autopilot_retry_limit: int | None = None,
    autopilot_operation_count: int | None = None,
    autopilot_operation_limit: int | None = None,
    autopilot_runtime_started_at: str | None = None,
    autopilot_runtime_limit_seconds: int | None = None,
    autonomy_mode: str | None = None,
    autonomy_mode_status: str | None = None,
    autonomy_mode_reason: str | None = None,
    autonomy_stop_rail_config: dict | None = None,
    autonomy_current_counts: dict | None = None,
    autonomy_stop_rail_status: str | None = None,
    autonomy_stop_rail_result: dict | None = None,
    autonomy_governance_trace: dict | None = None,
    allowed_actions: list | None = None,
    blocked_actions: list | None = None,
    escalation_threshold: str | None = None,
    approval_required_actions: list | None = None,
    project_routing_status: str | None = None,
    project_routing_result: dict | None = None,
    mission_packet: dict | None = None,
    mission_id: str | None = None,
    mission_type: str | None = None,
    mission_title: str | None = None,
    mission_objective: str | None = None,
    mission_scope_boundary: dict | None = None,
    mission_allowed_actions: list | None = None,
    mission_forbidden_actions: list | None = None,
    mission_allowed_executors: list | None = None,
    mission_risk_level: str | None = None,
    mission_success_criteria: dict | None = None,
    mission_stop_conditions: list | None = None,
    mission_status: str | None = None,
    mission_created_at: str | None = None,
    mission_started_at: str | None = None,
    mission_completed_at: str | None = None,
    mission_failed_at: str | None = None,
    mission_requires_initial_approval: bool | None = None,
    mission_requires_final_approval: bool | None = None,
    mission_stop_condition_hit: bool | None = None,
    mission_stop_condition_reason: str | None = None,
    mission_escalation_required: bool | None = None,
    executor_route: str | None = None,
    executor_route_reason: str | None = None,
    executor_route_confidence: float | None = None,
    executor_route_status: str | None = None,
    executor_task_type: str | None = None,
    executor_task_packet: dict | None = None,
    executor_fallback_route: str | None = None,
) -> str:
    state_file = get_project_state_file(project_path)

    # Preserve router/preflight results across saves when not explicitly provided.
    previous: dict = {}
    try:
        if state_file.exists():
            previous = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        previous = {}
    if runtime_router_result is None and isinstance(previous.get("runtime_router_result"), dict):
        runtime_router_result = previous.get("runtime_router_result")
    if model_router_result is None and isinstance(previous.get("model_router_result"), dict):
        model_router_result = previous.get("model_router_result")
    if deployment_preflight_result is None and isinstance(previous.get("deployment_preflight_result"), dict):
        deployment_preflight_result = previous.get("deployment_preflight_result")

    # Preserve PRISM fields across saves when not explicitly provided.
    if prism_status is None and isinstance(previous.get("prism_status"), str):
        prism_status = previous.get("prism_status")
    if prism_result is None and isinstance(previous.get("prism_result"), dict):
        prism_result = previous.get("prism_result")
    if last_prism_summary is None and isinstance(previous.get("last_prism_summary"), dict):
        last_prism_summary = previous.get("last_prism_summary")
    if autopilot_enabled is None and isinstance(previous.get("autopilot_enabled"), bool):
        autopilot_enabled = previous.get("autopilot_enabled")
    if autopilot_status is None and isinstance(previous.get("autopilot_status"), str):
        autopilot_status = previous.get("autopilot_status")
    if autopilot_loop_state is None and isinstance(previous.get("autopilot_loop_state"), str):
        autopilot_loop_state = previous.get("autopilot_loop_state")
    if autopilot_last_run_at is None and isinstance(previous.get("autopilot_last_run_at"), str):
        autopilot_last_run_at = previous.get("autopilot_last_run_at")
    if autopilot_next_run_at is None and isinstance(previous.get("autopilot_next_run_at"), str):
        autopilot_next_run_at = previous.get("autopilot_next_run_at")
    if autopilot_current_focus is None and isinstance(previous.get("autopilot_current_focus"), str):
        autopilot_current_focus = previous.get("autopilot_current_focus")
    if autopilot_requires_operator_review is None and isinstance(previous.get("autopilot_requires_operator_review"), bool):
        autopilot_requires_operator_review = previous.get("autopilot_requires_operator_review")
    if autopilot_session_id is None and isinstance(previous.get("autopilot_session_id"), str):
        autopilot_session_id = previous.get("autopilot_session_id")
    if autopilot_project_key is None and isinstance(previous.get("autopilot_project_key"), str):
        autopilot_project_key = previous.get("autopilot_project_key")
    if autopilot_mode is None and isinstance(previous.get("autopilot_mode"), str):
        autopilot_mode = previous.get("autopilot_mode")
    if autopilot_iteration_count is None and isinstance(previous.get("autopilot_iteration_count"), int):
        autopilot_iteration_count = previous.get("autopilot_iteration_count")
    if autopilot_iteration_limit is None and isinstance(previous.get("autopilot_iteration_limit"), int):
        autopilot_iteration_limit = previous.get("autopilot_iteration_limit")
    if autopilot_started_at is None and isinstance(previous.get("autopilot_started_at"), str):
        autopilot_started_at = previous.get("autopilot_started_at")
    if autopilot_updated_at is None and isinstance(previous.get("autopilot_updated_at"), str):
        autopilot_updated_at = previous.get("autopilot_updated_at")
    if autopilot_last_package_id is None and isinstance(previous.get("autopilot_last_package_id"), str):
        autopilot_last_package_id = previous.get("autopilot_last_package_id")
    if autopilot_last_result is None and isinstance(previous.get("autopilot_last_result"), dict):
        autopilot_last_result = previous.get("autopilot_last_result")
    if autopilot_next_action is None and isinstance(previous.get("autopilot_next_action"), str):
        autopilot_next_action = previous.get("autopilot_next_action")
    if autopilot_stop_reason is None and isinstance(previous.get("autopilot_stop_reason"), str):
        autopilot_stop_reason = previous.get("autopilot_stop_reason")
    if autopilot_escalation_reason is None and isinstance(previous.get("autopilot_escalation_reason"), str):
        autopilot_escalation_reason = previous.get("autopilot_escalation_reason")
    if autopilot_progress_summary is None and isinstance(previous.get("autopilot_progress_summary"), dict):
        autopilot_progress_summary = previous.get("autopilot_progress_summary")
    if autopilot_retry_count is None and isinstance(previous.get("autopilot_retry_count"), int):
        autopilot_retry_count = previous.get("autopilot_retry_count")
    if autopilot_retry_limit is None and isinstance(previous.get("autopilot_retry_limit"), int):
        autopilot_retry_limit = previous.get("autopilot_retry_limit")
    if autopilot_operation_count is None and isinstance(previous.get("autopilot_operation_count"), int):
        autopilot_operation_count = previous.get("autopilot_operation_count")
    if autopilot_operation_limit is None and isinstance(previous.get("autopilot_operation_limit"), int):
        autopilot_operation_limit = previous.get("autopilot_operation_limit")
    if autopilot_runtime_started_at is None and isinstance(previous.get("autopilot_runtime_started_at"), str):
        autopilot_runtime_started_at = previous.get("autopilot_runtime_started_at")
    if autopilot_runtime_limit_seconds is None and isinstance(previous.get("autopilot_runtime_limit_seconds"), int):
        autopilot_runtime_limit_seconds = previous.get("autopilot_runtime_limit_seconds")
    if autonomy_mode is None and isinstance(previous.get("autonomy_mode"), str):
        autonomy_mode = previous.get("autonomy_mode")
    if autonomy_mode_status is None and isinstance(previous.get("autonomy_mode_status"), str):
        autonomy_mode_status = previous.get("autonomy_mode_status")
    if autonomy_mode_reason is None and isinstance(previous.get("autonomy_mode_reason"), str):
        autonomy_mode_reason = previous.get("autonomy_mode_reason")
    if autonomy_stop_rail_config is None and isinstance(previous.get("autonomy_stop_rail_config"), dict):
        autonomy_stop_rail_config = previous.get("autonomy_stop_rail_config")
    if autonomy_current_counts is None and isinstance(previous.get("autonomy_current_counts"), dict):
        autonomy_current_counts = previous.get("autonomy_current_counts")
    if autonomy_stop_rail_status is None and isinstance(previous.get("autonomy_stop_rail_status"), str):
        autonomy_stop_rail_status = previous.get("autonomy_stop_rail_status")
    if autonomy_stop_rail_result is None and isinstance(previous.get("autonomy_stop_rail_result"), dict):
        autonomy_stop_rail_result = previous.get("autonomy_stop_rail_result")
    if autonomy_governance_trace is None and isinstance(previous.get("autonomy_governance_trace"), dict):
        autonomy_governance_trace = previous.get("autonomy_governance_trace")
    if allowed_actions is None and isinstance(previous.get("allowed_actions"), list):
        allowed_actions = previous.get("allowed_actions")
    if blocked_actions is None and isinstance(previous.get("blocked_actions"), list):
        blocked_actions = previous.get("blocked_actions")
    if escalation_threshold is None and isinstance(previous.get("escalation_threshold"), str):
        escalation_threshold = previous.get("escalation_threshold")
    if approval_required_actions is None and isinstance(previous.get("approval_required_actions"), list):
        approval_required_actions = previous.get("approval_required_actions")
    if project_routing_status is None and isinstance(previous.get("project_routing_status"), str):
        project_routing_status = previous.get("project_routing_status")
    if project_routing_result is None and isinstance(previous.get("project_routing_result"), dict):
        project_routing_result = previous.get("project_routing_result")
    if mission_packet is None and isinstance(previous.get("mission_packet"), dict):
        mission_packet = previous.get("mission_packet")
    if mission_id is None and isinstance(previous.get("mission_id"), str):
        mission_id = previous.get("mission_id")
    if mission_type is None and isinstance(previous.get("mission_type"), str):
        mission_type = previous.get("mission_type")
    if mission_title is None and isinstance(previous.get("mission_title"), str):
        mission_title = previous.get("mission_title")
    if mission_objective is None and isinstance(previous.get("mission_objective"), str):
        mission_objective = previous.get("mission_objective")
    if mission_scope_boundary is None and isinstance(previous.get("mission_scope_boundary"), dict):
        mission_scope_boundary = previous.get("mission_scope_boundary")
    if mission_allowed_actions is None and isinstance(previous.get("mission_allowed_actions"), list):
        mission_allowed_actions = previous.get("mission_allowed_actions")
    if mission_forbidden_actions is None and isinstance(previous.get("mission_forbidden_actions"), list):
        mission_forbidden_actions = previous.get("mission_forbidden_actions")
    if mission_allowed_executors is None and isinstance(previous.get("mission_allowed_executors"), list):
        mission_allowed_executors = previous.get("mission_allowed_executors")
    if mission_risk_level is None and isinstance(previous.get("mission_risk_level"), str):
        mission_risk_level = previous.get("mission_risk_level")
    if mission_success_criteria is None and isinstance(previous.get("mission_success_criteria"), dict):
        mission_success_criteria = previous.get("mission_success_criteria")
    if mission_stop_conditions is None and isinstance(previous.get("mission_stop_conditions"), list):
        mission_stop_conditions = previous.get("mission_stop_conditions")
    if mission_status is None and isinstance(previous.get("mission_status"), str):
        mission_status = previous.get("mission_status")
    if mission_created_at is None and isinstance(previous.get("mission_created_at"), str):
        mission_created_at = previous.get("mission_created_at")
    if mission_started_at is None and isinstance(previous.get("mission_started_at"), str):
        mission_started_at = previous.get("mission_started_at")
    if mission_completed_at is None and isinstance(previous.get("mission_completed_at"), str):
        mission_completed_at = previous.get("mission_completed_at")
    if mission_failed_at is None and isinstance(previous.get("mission_failed_at"), str):
        mission_failed_at = previous.get("mission_failed_at")
    if mission_requires_initial_approval is None and isinstance(previous.get("mission_requires_initial_approval"), bool):
        mission_requires_initial_approval = previous.get("mission_requires_initial_approval")
    if mission_requires_final_approval is None and isinstance(previous.get("mission_requires_final_approval"), bool):
        mission_requires_final_approval = previous.get("mission_requires_final_approval")
    if mission_stop_condition_hit is None and isinstance(previous.get("mission_stop_condition_hit"), bool):
        mission_stop_condition_hit = previous.get("mission_stop_condition_hit")
    if mission_stop_condition_reason is None and isinstance(previous.get("mission_stop_condition_reason"), str):
        mission_stop_condition_reason = previous.get("mission_stop_condition_reason")
    if mission_escalation_required is None and isinstance(previous.get("mission_escalation_required"), bool):
        mission_escalation_required = previous.get("mission_escalation_required")
    if executor_route is None and isinstance(previous.get("executor_route"), str):
        executor_route = previous.get("executor_route")
    if executor_route_reason is None and isinstance(previous.get("executor_route_reason"), str):
        executor_route_reason = previous.get("executor_route_reason")
    if executor_route_confidence is None and isinstance(previous.get("executor_route_confidence"), (int, float)):
        executor_route_confidence = previous.get("executor_route_confidence")
    if executor_route_status is None and isinstance(previous.get("executor_route_status"), str):
        executor_route_status = previous.get("executor_route_status")
    if executor_task_type is None and isinstance(previous.get("executor_task_type"), str):
        executor_task_type = previous.get("executor_task_type")
    if executor_task_packet is None and isinstance(previous.get("executor_task_packet"), dict):
        executor_task_packet = previous.get("executor_task_packet")
    if executor_fallback_route is None and isinstance(previous.get("executor_fallback_route"), str):
        executor_fallback_route = previous.get("executor_fallback_route")
    if project_selection_status is None and isinstance(previous.get("project_selection_status"), str):
        project_selection_status = previous.get("project_selection_status")
    if project_selection_result is None and isinstance(previous.get("project_selection_result"), dict):
        project_selection_result = previous.get("project_selection_result")

    # Normalize AEGIS decision into the stable contract shape.
    from AEGIS.aegis_contract import normalize_aegis_result

    last_aegis_decision_normalized = normalize_aegis_result(last_aegis_decision)

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
        "execution_package_id": execution_package_id,
        "execution_package_path": execution_package_path,
        "runtime_execution_status": runtime_execution_status,
        "automation_status": automation_status,
        "automation_result": automation_result or {},
        "agent_selection_summary": agent_selection_summary or {},
        "governance_status": governance_status,
        "governance_result": governance_result or {},
        "project_selection_status": project_selection_status,
        "project_selection_result": project_selection_result or {},
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
        "runtime_router_result": runtime_router_result or {},
        "model_router_result": model_router_result or {},
        "deployment_preflight_result": deployment_preflight_result or {},
        "self_improvement_status": self_improvement_status,
        "self_improvement_result": self_improvement_result or {},
        "change_gate_status": change_gate_status,
        "change_gate_result": change_gate_result or {},
        "regression_status": regression_status,
        "regression_result": regression_result or {},
        # PRISM v1 (product launch probability + friction analysis) persisted outputs.
        "prism_status": prism_status,
        "prism_result": prism_result or {},
        "last_prism_summary": last_prism_summary or {},
        "last_aegis_decision": last_aegis_decision_normalized,
        "autopilot_enabled": bool(autopilot_enabled) if autopilot_enabled is not None else False,
        "autopilot_status": autopilot_status,
        "autopilot_loop_state": autopilot_loop_state,
        "autopilot_last_run_at": autopilot_last_run_at,
        "autopilot_next_run_at": autopilot_next_run_at,
        "autopilot_current_focus": autopilot_current_focus,
        "autopilot_requires_operator_review": bool(autopilot_requires_operator_review)
        if autopilot_requires_operator_review is not None
        else False,
        "autopilot_session_id": autopilot_session_id,
        "autopilot_project_key": autopilot_project_key,
        "autopilot_mode": autopilot_mode,
        "autopilot_iteration_count": autopilot_iteration_count,
        "autopilot_iteration_limit": autopilot_iteration_limit,
        "autopilot_started_at": autopilot_started_at,
        "autopilot_updated_at": autopilot_updated_at,
        "autopilot_last_package_id": autopilot_last_package_id,
        "autopilot_last_result": autopilot_last_result or {},
        "autopilot_next_action": autopilot_next_action,
        "autopilot_stop_reason": autopilot_stop_reason,
        "autopilot_escalation_reason": autopilot_escalation_reason,
        "autopilot_progress_summary": autopilot_progress_summary or {},
        "autopilot_retry_count": autopilot_retry_count,
        "autopilot_retry_limit": autopilot_retry_limit,
        "autopilot_operation_count": autopilot_operation_count,
        "autopilot_operation_limit": autopilot_operation_limit,
        "autopilot_runtime_started_at": autopilot_runtime_started_at,
        "autopilot_runtime_limit_seconds": autopilot_runtime_limit_seconds,
        "autonomy_mode": autonomy_mode,
        "autonomy_mode_status": autonomy_mode_status,
        "autonomy_mode_reason": autonomy_mode_reason,
        "autonomy_stop_rail_config": autonomy_stop_rail_config or {},
        "autonomy_current_counts": autonomy_current_counts or {},
        "autonomy_stop_rail_status": autonomy_stop_rail_status,
        "autonomy_stop_rail_result": autonomy_stop_rail_result or {},
        "autonomy_governance_trace": autonomy_governance_trace or {},
        "allowed_actions": allowed_actions or [],
        "blocked_actions": blocked_actions or [],
        "escalation_threshold": escalation_threshold,
        "approval_required_actions": approval_required_actions or [],
        "project_routing_status": project_routing_status,
        "project_routing_result": project_routing_result or {},
        "mission_packet": mission_packet or {},
        "mission_id": mission_id,
        "mission_type": mission_type,
        "mission_title": mission_title,
        "mission_objective": mission_objective,
        "mission_scope_boundary": mission_scope_boundary or {},
        "mission_allowed_actions": mission_allowed_actions or [],
        "mission_forbidden_actions": mission_forbidden_actions or [],
        "mission_allowed_executors": mission_allowed_executors or [],
        "mission_risk_level": mission_risk_level,
        "mission_success_criteria": mission_success_criteria or {},
        "mission_stop_conditions": mission_stop_conditions or [],
        "mission_status": mission_status,
        "mission_created_at": mission_created_at,
        "mission_started_at": mission_started_at,
        "mission_completed_at": mission_completed_at,
        "mission_failed_at": mission_failed_at,
        "mission_requires_initial_approval": bool(mission_requires_initial_approval)
        if mission_requires_initial_approval is not None
        else True,
        "mission_requires_final_approval": bool(mission_requires_final_approval)
        if mission_requires_final_approval is not None
        else True,
        "mission_stop_condition_hit": bool(mission_stop_condition_hit)
        if mission_stop_condition_hit is not None
        else False,
        "mission_stop_condition_reason": mission_stop_condition_reason,
        "mission_escalation_required": bool(mission_escalation_required)
        if mission_escalation_required is not None
        else False,
        "executor_route": executor_route,
        "executor_route_reason": executor_route_reason,
        "executor_route_confidence": float(executor_route_confidence)
        if executor_route_confidence is not None
        else 0.0,
        "executor_route_status": executor_route_status,
        "executor_task_type": executor_task_type,
        "executor_task_packet": executor_task_packet or {},
        "executor_fallback_route": executor_fallback_route,
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

    # Backfill compact audit summaries if missing (safe, deterministic, no history arrays).
    if "last_run_summary" not in merged or not isinstance(merged.get("last_run_summary"), dict):
        dispatch_result = merged.get("dispatch_result") if isinstance(merged.get("dispatch_result"), dict) else {}
        merged["last_run_summary"] = {
            "saved_at": merged.get("saved_at") or "",
            "active_project": merged.get("active_project") or "",
            "run_id": merged.get("run_id") or "",
            "runtime_execution_status": merged.get("runtime_execution_status") or dispatch_result.get("execution_status") or "",
            "dispatch_status": merged.get("dispatch_status") or "",
        }
    if "last_launch_summary" not in merged or not isinstance(merged.get("last_launch_summary"), dict):
        lr = merged.get("launch_result") if isinstance(merged.get("launch_result"), dict) else {}
        merged["last_launch_summary"] = {
            "launch_status": merged.get("launch_status") or lr.get("launch_status") or "none",
            "launch_action": lr.get("launch_action") or "none",
            "launch_reason": lr.get("launch_reason") or "",
            "target_project": lr.get("target_project") or merged.get("active_project") or "",
            "execution_started": bool(lr.get("execution_started", False)),
            "bounded_execution": bool(lr.get("bounded_execution", True)),
            "source": lr.get("source") or "none",
        }
    if "last_recovery_summary" not in merged or not isinstance(merged.get("last_recovery_summary"), dict):
        rr = merged.get("recovery_result") if isinstance(merged.get("recovery_result"), dict) else {}
        merged["last_recovery_summary"] = {
            "recovery_status": merged.get("recovery_status") or rr.get("recovery_status") or "none",
            "recovery_action": rr.get("recovery_action") or "none",
            "recovery_reason": rr.get("recovery_reason") or "",
            "retry_permitted": bool(rr.get("retry_permitted", False)),
            "repair_required": bool(rr.get("repair_required", False)),
            "retry_count_exceeded": bool(rr.get("retry_count_exceeded", False)),
        }
    if "last_completion_summary" not in merged or not isinstance(merged.get("last_completion_summary"), dict):
        cr = merged.get("completion_result") if isinstance(merged.get("completion_result"), dict) else {}
        merged["last_completion_summary"] = {
            "completion_status": cr.get("completion_status") or "none",
            "completion_type": cr.get("completion_type") or "none",
            "queue_cleared": bool(cr.get("queue_cleared", False)),
            "resume_unlocked": bool(cr.get("resume_unlocked", False)),
            "completion_recorded": bool(cr.get("completion_recorded", False)),
        }

    merged = normalize_display_data(merged)
    state_file = get_project_state_file(project_path)
    state_file.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return str(state_file)
