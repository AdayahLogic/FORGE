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

    previous_run_state: Dict[str, Any] = {}
    supervisor_decision: Dict[str, Any] = {}
    studio_supervisor_summary: List[Dict[str, Any]] = []
    autonomous_cycle_summary: Dict[str, Any] = {}
    computer_use_summary: Dict[str, Any] = {}
    tool_execution_summary: Dict[str, Any] = {}
    file_modification_summary: Dict[str, Any] = {}
    diff_patch_summary: Dict[str, Any] = {}
    agent_routing_summary: Dict[str, Any] = {}
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