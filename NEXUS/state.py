from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class StudioState(BaseModel):
    user_input: str
    active_project: Optional[str] = None
    active_agents: List[str] = []
    task_status: str = "pending"
    notes: Optional[str] = None
    project_path: Optional[str] = None
    loaded_context: Dict[str, str] = {}
    # Optional normalized project memory snapshot produced by the core
    # memory engine. Existing callers can continue to rely on loaded_context.
    normalized_memory: Dict[str, Any] = {}
    architect_plan: Optional[Dict[str, Any]] = None
    task_queue: List[Dict[str, Any]] = []
    # Optional richer snapshot for Nexus task queue engine; mirrors task_queue
    # but can evolve independently without breaking existing consumers.
    task_queue_snapshot: List[Dict[str, Any]] = []
    current_task: int = 0

    coder_output_path: Optional[str] = None
    implementation_file_path: Optional[str] = None
    test_report_path: Optional[str] = None
    docs_output_path: Optional[str] = None
    execution_report_path: Optional[str] = None
    workspace_report_path: Optional[str] = None
    operator_log_path: Optional[str] = None
    supervisor_report_path: Optional[str] = None
    studio_supervisor_report_path: Optional[str] = None
    autonomous_cycle_report_path: Optional[str] = None
    computer_use_report_path: Optional[str] = None
    tool_execution_report_path: Optional[str] = None
    file_modification_report_path: Optional[str] = None
    diff_patch_report_path: Optional[str] = None
    agent_routing_report_path: Optional[str] = None
    execution_bridge_report_path: Optional[str] = None
    engine_registry_report_path: Optional[str] = None
    capability_registry_report_path: Optional[str] = None
    tool_registry_report_path: Optional[str] = None
    workspace_boundary_report_path: Optional[str] = None
    path_migration_report_path: Optional[str] = None
    terminal_report_path: Optional[str] = None
    browser_research_report_path: Optional[str] = None
    full_automation_report_path: Optional[str] = None
    persistent_state_path: Optional[str] = None
    execution_ledger_path: Optional[str] = None
    run_id: Optional[str] = None
    execution_session_summary: Dict[str, Any] = {}

    previous_run_state: Dict[str, Any] = {}
    supervisor_decision: Dict[str, Any] = {}
    studio_supervisor_summary: List[Dict[str, Any]] = []
    autonomous_cycle_summary: Dict[str, Any] = {}
    computer_use_summary: Dict[str, Any] = {}
    tool_execution_summary: Dict[str, Any] = {}
    file_modification_summary: Dict[str, Any] = {}
    diff_patch_summary: Dict[str, Any] = {}
    agent_routing_summary: Dict[str, Any] = {}
    agent_profile: Dict[str, Any] = {}
    agent_selection_summary: Dict[str, Any] = {}
    execution_bridge_summary: Dict[str, Any] = {}
    engine_registry_summary: Dict[str, Any] = {}
    capability_registry_summary: Dict[str, Any] = {}
    tool_registry_summary: Dict[str, Any] = {}
    tool_routing_summary: Dict[str, Any] = {}
    workspace_boundary_summary: Dict[str, Any] = {}
    path_migration_summary: Dict[str, Any] = {}
    terminal_summary: Dict[str, Any] = {}
    browser_research_summary: Dict[str, Any] = {}
    full_automation_summary: Dict[str, Any] = {}
    execution_policy_summary: Dict[str, Any] = {}
    system_health_summary: Dict[str, Any] = {}
    system_health_report_path: Optional[str] = None
    dispatch_plan: Dict[str, Any] = {}
    dispatch_plan_summary: Dict[str, Any] = {}
    dispatch_status: Optional[str] = None
    dispatch_result: Dict[str, Any] = {}
    runtime_execution_status: Optional[str] = None
    automation_status: Optional[str] = None
    automation_result: Dict[str, Any] = {}
    governance_status: Optional[str] = None
    governance_result: Dict[str, Any] = {}
    project_lifecycle_status: Optional[str] = None
    project_lifecycle_result: Dict[str, Any] = {}
    enforcement_status: Optional[str] = None
    enforcement_result: Dict[str, Any] = {}
    workflow_route_status: Optional[str] = None
    workflow_route_reason: Optional[str] = None
    review_queue_entry: Dict[str, Any] = {}
    resume_status: Optional[str] = None
    resume_result: Dict[str, Any] = {}
    heartbeat_status: Optional[str] = None
    heartbeat_result: Dict[str, Any] = {}
    scheduler_status: Optional[str] = None
    scheduler_result: Dict[str, Any] = {}
    completion_result: Dict[str, Any] = {}
    recovery_status: Optional[str] = None
    recovery_result: Dict[str, Any] = {}
    reexecution_status: Optional[str] = None
    reexecution_result: Dict[str, Any] = {}
    launch_status: Optional[str] = None
    launch_result: Dict[str, Any] = {}
    autonomous_launch: bool = False
    autonomy_status: Optional[str] = None
    autonomy_result: Dict[str, Any] = {}
    guardrail_status: Optional[str] = None
    guardrail_result: Dict[str, Any] = {}