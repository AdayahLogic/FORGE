from langgraph.graph import StateGraph, END
from NEXUS.state import StudioState
from NEXUS.router import detect_project
from NEXUS.registry import PROJECTS
from NEXUS.memory import load_project_context
from NEXUS.memory_engine import load_project_memory
from NEXUS.llm import generate_architect_plan
from NEXUS.tasks import build_task_queue
from NEXUS.queue import InMemoryTaskQueue, Task, TaskStatus
from NEXUS.coder import write_coder_output, mark_first_pending_task_complete
from NEXUS.implementer import write_controlled_implementation_file
from NEXUS.tester import write_test_report
from NEXUS.docs_writer import write_docs_update
from NEXUS.project_state import load_project_state, save_project_state
from NEXUS.executor import run_safe_commands, write_execution_report
from NEXUS.workspace import scan_workspace, write_workspace_report
from NEXUS.operator_agent import run_operator_sequence
from NEXUS.supervisor import build_supervisor_decision, write_supervisor_report
from NEXUS.studio_supervisor import summarize_all_projects, write_studio_supervisor_report
from NEXUS.autonomous_cycle import build_autonomous_cycle_summary, write_autonomous_cycle_report
from NEXUS.computer_use import build_computer_use_summary, write_computer_use_report
from NEXUS.tool_runner import run_tool_sequence, write_tool_execution_report
from NEXUS.file_modifier import append_controlled_update, write_file_modification_report
from NEXUS.diff_patch import (
    build_patch_request_from_architect_plan,
    apply_safe_patch,
    write_patch_report,
)
from NEXUS.agent_router import build_agent_route, write_agent_router_report
from NEXUS.execution_bridge import build_execution_bridge_packet, write_execution_bridge_report
from NEXUS.engine_inspector import build_engine_summary, write_engine_report
from NEXUS.capability_inspector import build_capability_summary, write_capability_report
from NEXUS.tool_inspector import build_tool_summary, write_tool_registry_report
from NEXUS.workspace_guard import (
    build_workspace_boundary_summary,
    write_workspace_boundary_report,
)
from NEXUS.path_migration import (
    build_path_migration_summary,
    write_path_migration_report,
)
from NEXUS.terminal_controller import run_allowed_commands, write_terminal_report
from NEXUS.browser_agent import open_safe_research_urls, write_browser_research_report
from NEXUS.full_automation import build_full_automation_summary, write_full_automation_report
from NEXUS.execution_ledger import get_ledger_path, append_entry as ledger_append
from NEXUS.run_context import create_run_context, finalize_run_context
from NEXUS.system_health import evaluate_health, write_system_health_report
from NEXUS.dispatch_planner import build_dispatch_plan_safe
from NEXUS.runtime_dispatcher import dispatch as runtime_dispatch
from NEXUS.automation_layer import evaluate_automation_outcome_safe
from NEXUS.governance_layer import evaluate_governance_outcome_safe
from NEXUS.project_lifecycle import evaluate_project_lifecycle_safe
from NEXUS.enforcement_layer import evaluate_enforcement_outcome_safe
from NEXUS.review_queue import build_review_queue_entry_safe
from NEXUS.resume_engine import evaluate_resume_outcome_safe
from NEXUS.heartbeat_loop import evaluate_heartbeat_safe
from NEXUS.cycle_scheduler import evaluate_cycle_scheduler_safe
from NEXUS.recovery_engine import evaluate_recovery_outcome_safe
from NEXUS.reexecution_engine import evaluate_reexecution_outcome_safe


def route_project(state: StudioState):
    project_key = detect_project(state.user_input)
    project = PROJECTS[project_key]

    state.active_project = project_key
    state.active_agents = project["agents"]
    state.project_path = project["path"]
    state.notes = f"Project context loaded: {project['name']}"

    print(f"\n[Router] Project detected: {project['name']}")
    return state


def load_persistent_project_state(state: StudioState):
    print("[State] Loading persistent project state...")

    if not state.project_path:
        state.notes = "No project path found for persistent state load."
        return state

    loaded = load_project_state(state.project_path)
    state.previous_run_state = loaded

    if loaded:
        state.notes = "Previous project state loaded."
    else:
        state.notes = "No previous project state found."

    # Run context: create run_id and write workflow_run_started
    run_ctx = create_run_context(
        project_name=state.active_project,
        user_input=state.user_input,
    )
    state.run_id = run_ctx["run_id"]
    state.execution_session_summary = run_ctx
    try:
        ledger_append(
            state.project_path,
            "workflow_run_started",
            "started",
            f"Workflow run started for project {state.active_project or 'unknown'}.",
            project_name=state.active_project,
            run_id=state.run_id,
            payload={"run_id": state.run_id, "user_input": (state.user_input or "")[:200]},
        )
    except Exception:
        pass
    return state


def load_memory(state: StudioState):
    print("[Memory] Loading project docs, memory, and tasks...")

    if not state.project_path:
        state.notes = "No project path found."
        return state

    # Preserve existing behavior: load aggregated docs/memory/tasks text.
    state.loaded_context = load_project_context(state.project_path)

    # In parallel, build a normalized, project-scoped memory snapshot
    # using the new Nexus core memory engine. This is stored separately
    # to keep existing planner and report flows intact.
    memory_snapshot = load_project_memory(
        project_path=state.project_path,
        project_name=state.active_project,
    )

    # Store normalized memory in the dedicated state field only (loaded_context
    # is Dict[str, str] and cannot hold a dict without triggering validation).
    state.normalized_memory = memory_snapshot.dict()

    state.notes = "Project memory loaded."
    return state


def architect_agent(state: StudioState):
    print("[Planner] Generating structured implementation plan...")

    project_name = state.active_project or "unknown_project"

    plan = generate_architect_plan(
        user_input=state.user_input,
        project_name=project_name,
        loaded_context=state.loaded_context
    )

    state.architect_plan = plan
    state.notes = "Planner generated structured plan."

    # Phase 15: outcome-learning (passive observer; never breaks workflow).
    try:
        from NEXUS.learning_engine import build_outcome_learning_record_safe
        from NEXUS.learning_writer import append_learning_record_safe

        decision_summary = ""
        if isinstance(plan, dict):
            decision_summary = plan.get("objective") or plan.get("problem_solved") or plan.get("product_concept") or ""

        record = build_outcome_learning_record_safe(
            state=state,
            workflow_stage="after_architect_plan",
            decision_source="architect_agent",
            decision_type="architect_plan",
            decision_summary=str(decision_summary),
        )
        append_learning_record_safe(project_path=state.project_path, record=record)
    except Exception:
        pass

    return state


def task_queue_builder(state: StudioState):
    print("[Task Manager] Building task queue...")

    # Preserve existing task construction semantics using the legacy builder.
    legacy_queue = build_task_queue(state.architect_plan)

    # Build a core Nexus in-memory queue in parallel, then snapshot it back
    # into the state in a fully backward-compatible structure.
    core_queue = InMemoryTaskQueue()

    for index, legacy_task in enumerate(legacy_queue):
        description = legacy_task.get("task", f"task-{index + 1}")
        status_str = legacy_task.get("status", "pending")

        # Map status into the TaskStatus enum, defaulting safely to PENDING.
        try:
            status = TaskStatus(status_str)
        except ValueError:
            status = TaskStatus.PENDING

        core_queue.add_task(
            Task(
                id=f"task-{index + 1}",
                type="implementation_step",
                payload={"description": description},
                priority=index,
                status=status,
            )
        )

    snapshot = core_queue.snapshot()
    state.task_queue = snapshot

    # If StudioState has an explicit snapshot field, populate it as well
    # without changing any existing consumers of task_queue.
    if hasattr(state, "task_queue_snapshot"):
        state.task_queue_snapshot = snapshot

    for i, task in enumerate(state.task_queue):
        print(f"Task {i + 1}: {task['task']} ({task['status']})")

    state.notes = "Task queue created."
    return state


def agent_router_node(state: StudioState):
    print("[Agent Router] Resolving safe next-agent handoff...")

    if not state.project_path:
        state.notes = "Agent router could not run: missing project path."
        return state

    try:
        summary = build_agent_route(
            architect_plan=state.architect_plan,
            active_project=state.active_project,
        )
        report_path = write_agent_router_report(
            project_path=state.project_path,
            project_name=state.active_project or "unknown_project",
            summary=summary,
            run_id=state.run_id,
        )
        state.agent_routing_summary = summary
        state.agent_profile = summary.get("agent_profile") or {}
        state.agent_selection_summary = summary.get("agent_selection_summary") or {}
        state.execution_policy_summary = summary.get("runtime_node_policy_summary") or {}
        state.agent_routing_report_path = report_path
        state.notes = f"Agent router report created at: {report_path}"
    except Exception as e:
        state.notes = f"Agent router failed: {e}"

    return state


def execution_bridge_node(state: StudioState):
    print("[Execution Bridge] Building Cursor/Codex handoff packet...")

    if not state.project_path:
        state.notes = "Execution bridge could not run: missing project path."
        return state

    try:
        packet = build_execution_bridge_packet(
            active_project=state.active_project,
            architect_plan=state.architect_plan,
            task_queue=state.task_queue,
            agent_routing_summary=state.agent_routing_summary,
        )
        report_path = write_execution_bridge_report(
            project_path=state.project_path,
            project_name=state.active_project or "unknown_project",
            packet=packet,
        )
        state.execution_bridge_summary = packet
        state.execution_bridge_report_path = report_path
        state.notes = f"Execution bridge report created at: {report_path}"
    except Exception as e:
        state.notes = f"Execution bridge failed: {e}"

    return state


def dispatch_planning_node(state: StudioState):
    """Build normalized dispatch plan from routing and execution bridge; planning only."""
    try:
        project_summary = {
            "project_id": state.active_project,
            "project_name": state.active_project,
            "active_project": state.active_project,
            "project_path": state.project_path,
        }
        plan = build_dispatch_plan_safe(
            project_summary=project_summary,
            request=state.user_input,
            planner_output=state.architect_plan,
            router_output=state.agent_routing_summary,
            execution_bridge_packet=state.execution_bridge_summary,
        )
        state.dispatch_plan = plan
        exec_block = plan.get("execution") or {}
        routing_block = plan.get("routing") or {}
        request_block = plan.get("request") or {}
        state.dispatch_plan_summary = {
            "dispatch_planning_status": plan.get("dispatch_planning_status", "planned"),
            "ready_for_dispatch": plan.get("ready_for_dispatch", False),
            "project_name": (plan.get("project") or {}).get("project_name") or state.active_project,
            "runtime_node": routing_block.get("runtime_node", ""),
            "runtime_target_id": exec_block.get("runtime_target_id", ""),
            "task_type": request_block.get("task_type", ""),
            "planned_at": (plan.get("timestamps") or {}).get("planned_at", ""),
        }
        base = state.execution_bridge_summary if isinstance(state.execution_bridge_summary, dict) else {}
        state.execution_bridge_summary = {**base, "dispatch_plan_summary": state.dispatch_plan_summary}
    except Exception:
        state.dispatch_plan = {}
        state.dispatch_plan_summary = {
            "dispatch_planning_status": "error_fallback",
            "ready_for_dispatch": False,
            "project_name": state.active_project or "",
            "runtime_node": "",
            "runtime_target_id": "local",
            "task_type": "",
            "planned_at": "",
        }

    return state


def runtime_dispatch_node(state: StudioState):
    """Simulate runtime dispatch from dispatch_plan; store status and result."""
    try:
        plan = state.dispatch_plan or {}
        result = runtime_dispatch(plan)
        state.dispatch_status = result.get("dispatch_status", "skipped")
        state.dispatch_result = result.get("dispatch_result", {}) or {}
        state.runtime_execution_status = (state.dispatch_result or {}).get("execution_status")
        state.execution_package_id = (state.dispatch_result or {}).get("execution_package_id")
        state.execution_package_path = (state.dispatch_result or {}).get("execution_package_path")
        if "runtime_target" not in state.dispatch_result and result.get("runtime_target"):
            state.dispatch_result = {**state.dispatch_result, "runtime_target": result.get("runtime_target")}
    except Exception:
        state.dispatch_status = "error"
        state.dispatch_result = {
            "runtime": "unknown",
            "status": "error",
            "message": "Dispatch failed.",
            "execution_status": "failed",
            "execution_mode": "safe_simulation",
            "next_action": "human_review",
            "artifacts": [],
            "errors": [{"reason": "exception"}],
        }
        state.execution_package_id = None
        state.execution_package_path = None
        state.runtime_execution_status = "failed"

    # Phase 15: outcome-learning after dispatch result (passive observer).
    try:
        from NEXUS.learning_engine import build_outcome_learning_record_safe
        from NEXUS.learning_writer import append_learning_record_safe

        dispatch_summary = ""
        if isinstance(state.dispatch_result, dict):
            dispatch_summary = state.dispatch_result.get("message") or state.dispatch_result.get("reason") or ""
        record = build_outcome_learning_record_safe(
            state=state,
            workflow_stage="after_runtime_dispatch",
            decision_source="runtime_dispatch_node",
            decision_type="dispatch_result",
            decision_summary=str(dispatch_summary),
        )
        append_learning_record_safe(project_path=state.project_path, record=record)
    except Exception:
        pass
    return state


def automation_layer_node(state: StudioState):
    """Evaluate automation outcome and recommend next action (no execution)."""
    result = evaluate_automation_outcome_safe(
        dispatch_status=state.dispatch_status,
        runtime_execution_status=state.runtime_execution_status,
        dispatch_result=state.dispatch_result,
        dispatch_plan=state.dispatch_plan,
        dispatch_plan_summary=state.dispatch_plan_summary,
        active_project=state.active_project,
        project_path=state.project_path,
    )
    state.automation_result = result
    state.automation_status = result.get("automation_status")
    return state


def governance_layer_node(state: StudioState):
    """Evaluate governance outcome after dispatch and automation (no execution)."""
    result = evaluate_governance_outcome_safe(
        dispatch_status=state.dispatch_status,
        runtime_execution_status=state.runtime_execution_status,
        dispatch_result=state.dispatch_result,
        automation_status=state.automation_status,
        automation_result=state.automation_result,
        agent_selection_summary=state.agent_selection_summary,
        dispatch_plan_summary=state.dispatch_plan_summary,
        active_project=state.active_project,
        project_path=state.project_path,
    )
    state.governance_result = result
    state.governance_status = result.get("governance_status")
    return state


def project_lifecycle_node(state: StudioState):
    """Evaluate project lifecycle from orchestration state (no execution)."""
    existing = {
        "dispatch_plan_summary": state.dispatch_plan_summary,
        "architect_plan": state.architect_plan,
        "task_queue": state.task_queue,
    }
    result = evaluate_project_lifecycle_safe(
        active_project=state.active_project,
        project_path=state.project_path,
        dispatch_status=state.dispatch_status,
        runtime_execution_status=state.runtime_execution_status,
        automation_status=state.automation_status,
        governance_status=state.governance_status,
        governance_result=state.governance_result,
        automation_result=state.automation_result,
        dispatch_result=state.dispatch_result,
        existing_project_state=existing,
    )
    state.project_lifecycle_result = result
    state.project_lifecycle_status = result.get("lifecycle_status")
    return state


def enforcement_layer_node(state: StudioState):
    """Evaluate enforcement outcome from governance and lifecycle (no execution)."""
    result = evaluate_enforcement_outcome_safe(
        governance_status=state.governance_status,
        governance_result=state.governance_result,
        project_lifecycle_status=state.project_lifecycle_status,
        project_lifecycle_result=state.project_lifecycle_result,
        active_project=state.active_project,
        project_path=state.project_path,
    )
    state.enforcement_result = result
    state.enforcement_status = result.get("enforcement_status")

    # Phase 15: outcome-learning after governance + enforcement evaluation.
    try:
        from NEXUS.learning_engine import build_outcome_learning_record_safe
        from NEXUS.learning_writer import append_learning_record_safe

        en_summary = ""
        if isinstance(result, dict):
            en_summary = result.get("reason") or result.get("decision_reason") or ""
        record = build_outcome_learning_record_safe(
            state=state,
            workflow_stage="after_governance_enforcement",
            decision_source="enforcement_layer_node",
            decision_type="enforcement_status",
            decision_summary=str(en_summary),
        )
        append_learning_record_safe(project_path=state.project_path, record=record)
    except Exception:
        pass
    return state


def determine_post_enforcement_route(state: StudioState) -> str:
    """
    Route after enforcement_layer based on workflow_action and enforcement_status.
    Returns node name: engine_registry, manual_review_hold, approval_hold, hold_state, blocked_stop.
    """
    er = state.enforcement_result or {}
    workflow_action = (er.get("workflow_action") or "").strip().lower()
    enforcement_status = (state.enforcement_status or er.get("enforcement_status") or "").strip().lower()

    if workflow_action == "proceed" or enforcement_status == "continue":
        return "engine_registry"
    if workflow_action == "manual_review" or enforcement_status == "manual_review_required":
        return "manual_review_hold"
    if workflow_action == "await_approval" or enforcement_status == "approval_required":
        return "approval_hold"
    if workflow_action == "hold" or enforcement_status == "hold":
        return "hold_state"
    if workflow_action == "stop_after_current_stage" or enforcement_status == "blocked":
        return "blocked_stop"
    # Missing/malformed: safe default to normal path
    return "engine_registry"


def _set_workflow_route_and_save(state: StudioState, route_status: str, route_reason: str) -> StudioState:
    """Set workflow route fields and leave state for persistent_state_save."""
    state.workflow_route_status = route_status
    state.workflow_route_reason = route_reason
    return state


def manual_review_hold_node(state: StudioState):
    """Hold node: manual review required; no external actions; then save and END."""
    er = state.enforcement_result or {}
    _set_workflow_route_and_save(state, "manual_review_hold", er.get("reason", "Manual review required."))
    state.review_queue_entry = build_review_queue_entry_safe(
        active_project=state.active_project,
        run_id=state.run_id,
        enforcement_status=state.enforcement_status,
        enforcement_result=state.enforcement_result,
        workflow_route_status=state.workflow_route_status,
        workflow_route_reason=state.workflow_route_reason,
        governance_status=state.governance_status,
        project_lifecycle_status=state.project_lifecycle_status,
    )
    return state


def approval_hold_node(state: StudioState):
    """Hold node: approval required; no external actions; then save and END."""
    er = state.enforcement_result or {}
    _set_workflow_route_and_save(state, "approval_hold", er.get("reason", "Approval required."))
    state.review_queue_entry = build_review_queue_entry_safe(
        active_project=state.active_project,
        run_id=state.run_id,
        enforcement_status=state.enforcement_status,
        enforcement_result=state.enforcement_result,
        workflow_route_status=state.workflow_route_status,
        workflow_route_reason=state.workflow_route_reason,
        governance_status=state.governance_status,
        project_lifecycle_status=state.project_lifecycle_status,
    )
    return state


def hold_state_node(state: StudioState):
    """Hold node: workflow held; no external actions; then save and END."""
    er = state.enforcement_result or {}
    _set_workflow_route_and_save(state, "hold_state", er.get("reason", "Workflow held."))
    state.review_queue_entry = build_review_queue_entry_safe(
        active_project=state.active_project,
        run_id=state.run_id,
        enforcement_status=state.enforcement_status,
        enforcement_result=state.enforcement_result,
        workflow_route_status=state.workflow_route_status,
        workflow_route_reason=state.workflow_route_reason,
        governance_status=state.governance_status,
        project_lifecycle_status=state.project_lifecycle_status,
    )
    return state


def blocked_stop_node(state: StudioState):
    """Hold node: blocked; no external actions; then save and END."""
    er = state.enforcement_result or {}
    _set_workflow_route_and_save(state, "blocked_stop", er.get("reason", "Workflow blocked."))
    state.review_queue_entry = build_review_queue_entry_safe(
        active_project=state.active_project,
        run_id=state.run_id,
        enforcement_status=state.enforcement_status,
        enforcement_result=state.enforcement_result,
        workflow_route_status=state.workflow_route_status,
        workflow_route_reason=state.workflow_route_reason,
        governance_status=state.governance_status,
        project_lifecycle_status=state.project_lifecycle_status,
    )
    return state


def resume_evaluation_node(state: StudioState):
    """Evaluate resume outcome from queue and enforcement state; store result."""
    result = evaluate_resume_outcome_safe(
        active_project=state.active_project,
        run_id=state.run_id,
        review_queue_entry=state.review_queue_entry,
        enforcement_status=state.enforcement_status,
        enforcement_result=state.enforcement_result,
        workflow_route_status=state.workflow_route_status,
        workflow_route_reason=state.workflow_route_reason,
        governance_status=state.governance_status,
        project_lifecycle_status=state.project_lifecycle_status,
    )
    state.resume_result = result
    state.resume_status = result.get("resume_status")
    return state


def heartbeat_evaluation_node(state: StudioState):
    """Evaluate heartbeat from resume, queue, governance, lifecycle; store result."""
    result = evaluate_heartbeat_safe(
        active_project=state.active_project,
        run_id=state.run_id,
        review_queue_entry=state.review_queue_entry,
        resume_result=state.resume_result,
        governance_status=state.governance_status,
        governance_result=state.governance_result,
        project_lifecycle_status=state.project_lifecycle_status,
        project_lifecycle_result=state.project_lifecycle_result,
        autonomous_cycle_summary=state.autonomous_cycle_summary,
        dispatch_status=state.dispatch_status,
    )
    state.heartbeat_result = result
    state.heartbeat_status = result.get("heartbeat_status")
    return state


def scheduler_evaluation_node(state: StudioState):
    """Evaluate cycle scheduler from heartbeat, resume, queue, lifecycle; store result."""
    result = evaluate_cycle_scheduler_safe(
        active_project=state.active_project,
        run_id=state.run_id,
        heartbeat_status=state.heartbeat_status,
        heartbeat_result=state.heartbeat_result,
        resume_status=state.resume_status,
        resume_result=state.resume_result,
        review_queue_entry=state.review_queue_entry,
        project_lifecycle_status=state.project_lifecycle_status,
        project_lifecycle_result=state.project_lifecycle_result,
        governance_status=state.governance_status,
        governance_result=state.governance_result,
        autonomous_cycle_summary=state.autonomous_cycle_summary,
    )
    state.scheduler_result = result
    state.scheduler_status = result.get("scheduler_status")
    return state


def recovery_evaluation_node(state: StudioState):
    """Evaluate recovery outcome from completion, resume, scheduler, governance, lifecycle; store result."""
    result = evaluate_recovery_outcome_safe(
        active_project=state.active_project,
        run_id=state.run_id,
        review_queue_entry=state.review_queue_entry,
        completion_result=state.completion_result,
        resume_result=state.resume_result,
        heartbeat_result=state.heartbeat_result,
        scheduler_result=state.scheduler_result,
        governance_status=state.governance_status,
        governance_result=state.governance_result,
        project_lifecycle_status=state.project_lifecycle_status,
        project_lifecycle_result=state.project_lifecycle_result,
        enforcement_status=state.enforcement_status,
        enforcement_result=state.enforcement_result,
    )
    state.recovery_result = result
    state.recovery_status = result.get("recovery_status")
    return state


def reexecution_evaluation_node(state: StudioState):
    """Evaluate re-execution outcome from scheduler, recovery, resume, queue; store result."""
    result = evaluate_reexecution_outcome_safe(
        active_project=state.active_project,
        run_id=state.run_id,
        scheduler_status=state.scheduler_status,
        scheduler_result=state.scheduler_result,
        recovery_status=state.recovery_status,
        recovery_result=state.recovery_result,
        resume_status=state.resume_status,
        resume_result=state.resume_result,
        review_queue_entry=state.review_queue_entry,
        autonomous_cycle_summary=state.autonomous_cycle_summary,
        project_lifecycle_status=state.project_lifecycle_status,
        project_lifecycle_result=state.project_lifecycle_result,
    )
    state.reexecution_result = result
    state.reexecution_status = result.get("reexecution_status")
    return state


def engine_registry_node(state: StudioState):
    print("[Engine Registry] Inspecting reusable engine inventory...")

    if not state.project_path:
        state.notes = "Engine registry could not run: missing project path."
        return state

    try:
        summary = build_engine_summary(state.active_project)
        report_path = write_engine_report(
            project_path=state.project_path,
            project_name=state.active_project or "unknown_project",
            summary=summary,
        )
        state.engine_registry_summary = summary
        state.engine_registry_report_path = report_path
        state.notes = f"Engine registry report created at: {report_path}"
    except Exception as e:
        state.notes = f"Engine registry failed: {e}"

    return state


def capability_registry_node(state: StudioState):
    print("[Capability Registry] Inspecting capability inventory...")

    if not state.project_path:
        state.notes = "Capability registry could not run: missing project path."
        return state

    try:
        summary = build_capability_summary(state.active_project)
        report_path = write_capability_report(
            project_path=state.project_path,
            project_name=state.active_project or "unknown_project",
            summary=summary,
        )
        state.capability_registry_summary = summary
        state.capability_registry_report_path = report_path
        state.notes = f"Capability registry report created at: {report_path}"
    except Exception as e:
        state.notes = f"Capability registry failed: {e}"

    return state


def tool_registry_node(state: StudioState):
    print("[Tool Registry] Inspecting tool inventory...")

    if not state.project_path:
        state.notes = "Tool registry could not run: missing project path."
        return state

    try:
        summary = build_tool_summary(
            active_project=state.active_project,
            active_agent=state.agent_routing_summary.get("resolved_agent_name") if state.agent_routing_summary else None,
        )
        report_path = write_tool_registry_report(
            project_path=state.project_path,
            project_name=state.active_project or "unknown_project",
            summary=summary,
        )
        state.tool_registry_summary = summary
        state.tool_registry_report_path = report_path
        state.notes = f"Tool registry report created at: {report_path}"
    except Exception as e:
        state.notes = f"Tool registry failed: {e}"

    return state


def workspace_boundary_node(state: StudioState):
    print("[Workspace Boundary] Inspecting layer and path boundaries...")

    if not state.project_path:
        state.notes = "Workspace boundary could not run: missing project path."
        return state

    try:
        summary = build_workspace_boundary_summary(
            project_path=state.project_path,
            active_project=state.active_project,
        )
        report_path = write_workspace_boundary_report(
            project_path=state.project_path,
            project_name=state.active_project or "unknown_project",
            summary=summary,
        )
        state.workspace_boundary_summary = summary
        state.workspace_boundary_report_path = report_path
        state.notes = f"Workspace boundary report created at: {report_path}"
    except Exception as e:
        state.notes = f"Workspace boundary failed: {e}"

    return state


def path_migration_node(state: StudioState):
    print("[Path Migration] Inspecting path aliases and migration status...")

    if not state.project_path:
        state.notes = "Path migration could not run: missing project path."
        return state

    try:
        summary = build_path_migration_summary(
            project_path=state.project_path,
            active_project=state.active_project,
        )
        report_path = write_path_migration_report(
            project_path=state.project_path,
            project_name=state.active_project or "unknown_project",
            summary=summary,
        )
        state.path_migration_summary = summary
        state.path_migration_report_path = report_path
        state.notes = f"Path migration report created at: {report_path}"
    except Exception as e:
        state.notes = f"Path migration failed: {e}"

    return state


def coder_agent(state: StudioState):
    print("[Coder] Executing controlled implementation task...")

    if not state.project_path or not state.active_project:
        state.notes = "Coder could not run: missing project path or project name."
        return state

    try:
        output_path = write_coder_output(
            project_path=state.project_path,
            project_name=state.active_project,
            task_queue=state.task_queue
        )

        implementation_path = write_controlled_implementation_file(
            project_path=state.project_path,
            project_name=state.active_project,
            architect_plan=state.architect_plan,
            task_queue=state.task_queue
        )

        state.task_queue = mark_first_pending_task_complete(state.task_queue)
        state.coder_output_path = output_path
        state.implementation_file_path = implementation_path
        state.notes = f"Coder created implementation file at: {implementation_path}"

    except Exception as e:
        state.notes = f"Coder execution failed: {e}"

    return state


def tester_agent(state: StudioState):
    print("[Tester] Running validation checks...")

    if not state.project_path:
        state.notes = "Tester could not run: missing project path."
        return state

    try:
        report_path = write_test_report(
            project_path=state.project_path,
            coder_output_path=state.coder_output_path,
            task_queue=state.task_queue,
            implementation_file_path=state.implementation_file_path
        )
        state.test_report_path = report_path
        state.notes = f"Tester created report at: {report_path}"
    except Exception as e:
        state.notes = f"Tester execution failed: {e}"

    return state


def docs_agent(state: StudioState):
    print("[Docs] Generating documentation update...")

    if not state.project_path or not state.active_project:
        state.notes = "Docs agent could not run: missing project info."
        return state

    try:
        docs_path = write_docs_update(
            project_path=state.project_path,
            project_name=state.active_project,
            architect_plan=state.architect_plan,
            task_queue=state.task_queue,
            coder_output_path=state.coder_output_path,
            test_report_path=state.test_report_path,
        )

        state.docs_output_path = docs_path
        state.notes = f"Docs update created at: {docs_path}"

    except Exception as e:
        state.notes = f"Docs generation failed: {e}"

    return state


def executor_agent(state: StudioState):
    print("[Executor] Running safe workspace inspection commands...")

    if not state.project_path or not state.active_project:
        state.notes = "Executor could not run: missing project info."
        return state

    try:
        results = run_safe_commands(state.project_path)
        report_path = write_execution_report(
            project_path=state.project_path,
            project_name=state.active_project,
            results=results
        )
        state.execution_report_path = report_path
        state.notes = f"Execution report created at: {report_path}"
    except Exception as e:
        state.notes = f"Executor failed: {e}"

    return state


def workspace_agent(state: StudioState):
    print("[Workspace] Scanning project workspace...")

    if not state.project_path or not state.active_project:
        state.notes = "Workspace agent could not run: missing project info."
        return state

    try:
        scan_data = scan_workspace(state.project_path)
        report_path = write_workspace_report(
            project_path=state.project_path,
            project_name=state.active_project,
            scan_data=scan_data
        )
        state.workspace_report_path = report_path
        state.notes = f"Workspace report created at: {report_path}"
    except Exception as e:
        state.notes = f"Workspace scan failed: {e}"

    return state


def operator_agent(state: StudioState):
    print("[Operator] Running safe operator tool sequence...")

    if not state.project_path:
        state.notes = "Operator agent could not run: missing project path."
        return state

    try:
        log_path = run_operator_sequence(state.project_path)
        state.operator_log_path = log_path
        state.notes = f"Operator tool log updated at: {log_path}"
    except Exception as e:
        state.notes = f"Operator agent failed: {e}"

    return state


def supervisor_agent(state: StudioState):
    print("[Supervisor] Evaluating project progress and next action...")

    if not state.project_path:
        state.notes = "Supervisor agent could not run: missing project path."
        return state

    try:
        decision = build_supervisor_decision(
            active_project=state.active_project,
            previous_run_state=state.previous_run_state,
            task_queue=state.task_queue
        )
        report_path = write_supervisor_report(
            project_path=state.project_path,
            decision=decision
        )
        state.supervisor_decision = decision
        state.supervisor_report_path = report_path
        state.notes = f"Supervisor report created at: {report_path}"
    except Exception as e:
        state.notes = f"Supervisor agent failed: {e}"

    return state


def studio_supervisor_agent(state: StudioState):
    print("[Studio Supervisor] Reviewing all registered projects...")

    try:
        summary = summarize_all_projects()
        report_path = write_studio_supervisor_report(summary)
        state.studio_supervisor_summary = summary
        state.studio_supervisor_report_path = report_path
        state.notes = f"Studio supervisor report created at: {report_path}"
    except Exception as e:
        state.notes = f"Studio supervisor agent failed: {e}"

    return state


def autonomous_cycle_agent(state: StudioState):
    print("[Autonomous Cycle] Building supervised multi-cycle summary...")

    if not state.project_path or not state.active_project:
        state.notes = "Autonomous cycle agent could not run: missing project info."
        return state

    try:
        summary = build_autonomous_cycle_summary(
            supervisor_decision=state.supervisor_decision,
            max_cycles=3
        )
        report_path = write_autonomous_cycle_report(
            project_path=state.project_path,
            project_name=state.active_project,
            summary=summary
        )
        state.autonomous_cycle_summary = summary
        state.autonomous_cycle_report_path = report_path
        state.notes = f"Autonomous cycle report created at: {report_path}"
    except Exception as e:
        state.notes = f"Autonomous cycle agent failed: {e}"

    return state


def computer_use_agent(state: StudioState):
    print("[Computer Use] Running safe computer-use foundation actions...")

    if not state.project_path or not state.active_project:
        state.notes = "Computer use agent could not run: missing project info."
        return state

    try:
        summary = build_computer_use_summary(
            project_path=state.project_path,
            docs_output_path=state.docs_output_path,
            workspace_report_path=state.workspace_report_path,
            open_project=True,
            open_docs=False,
            open_workspace_report=False,
            open_url=None,
        )
        report_path = write_computer_use_report(
            project_path=state.project_path,
            project_name=state.active_project,
            summary=summary
        )
        state.computer_use_summary = summary
        state.computer_use_report_path = report_path
        state.notes = f"Computer use report created at: {report_path}"
    except Exception as e:
        state.notes = f"Computer use agent failed: {e}"

    return state


def tool_execution_agent(state: StudioState):
    print("[Tool Execution] Running structured internal tools...")

    if not state.project_path or not state.active_project:
        state.notes = "Tool execution agent could not run: missing project info."
        return state

    try:
        summary = run_tool_sequence(
            project_path=state.project_path,
            project_name=state.active_project,
            architect_plan=state.architect_plan
        )
        report_path = write_tool_execution_report(
            project_path=state.project_path,
            project_name=state.active_project,
            summary=summary
        )
        state.tool_execution_summary = summary
        state.tool_execution_report_path = report_path
        state.notes = f"Tool execution report created at: {report_path}"
    except Exception as e:
        state.notes = f"Tool execution agent failed: {e}"

    return state


def terminal_agent(state: StudioState):
    print("[Terminal] Running allowlisted terminal commands...")

    if not state.project_path or not state.active_project:
        state.notes = "Terminal agent could not run: missing project info."
        return state

    try:
        results = run_allowed_commands(state.project_path)

        report_path = write_terminal_report(
            state.project_path,
            state.active_project or "unknown_project",
            results,
            run_id=state.run_id,
        )

        state.terminal_summary = {"commands_run": len(results)}
        state.terminal_report_path = report_path
        state.notes = f"Terminal report created at: {report_path}"

    except Exception as e:
        state.notes = f"Terminal execution failed: {e}"

    return state


def browser_research_agent(state: StudioState):
    print("[Browser] Launching safe research resources...")

    if not state.project_path or not state.active_project:
        state.notes = "Browser research agent could not run: missing project info."
        return state

    try:
        summary = open_safe_research_urls(max_urls=2)
        report_path = write_browser_research_report(
            project_path=state.project_path,
            project_name=state.active_project,
            summary=summary
        )
        state.browser_research_summary = summary
        state.browser_research_report_path = report_path
        state.notes = f"Browser research report created at: {report_path}"
    except Exception as e:
        state.notes = f"Browser research agent failed: {e}"

    return state


def file_modification_agent(state: StudioState):
    print("[File Modification] Applying controlled file update...")

    if not state.project_path:
        state.notes = "File modification agent could not run: missing project path."
        return state

    try:
        summary = append_controlled_update(
            project_path=state.project_path,
            project_name=state.active_project,
            architect_plan=state.architect_plan,
            target_relative_path="src/ai_generated_module.py"
        )
        report_path = write_file_modification_report(
            state.project_path,
            state.active_project or "unknown_project",
            summary,
            run_id=state.run_id,
        )
        state.file_modification_summary = summary
        state.file_modification_report_path = report_path
        state.notes = f"File modification report created at: {report_path}"
    except Exception as e:
        state.notes = f"File modification agent failed: {e}"

    return state


def diff_patch_agent(state: StudioState):
    print("[Diff Patch] Evaluating approved patch request...")

    if not state.project_path or not state.active_project:
        state.notes = "Diff patch agent could not run: missing project info."
        return state

    try:
        patch_request = build_patch_request_from_architect_plan(state.architect_plan)
        summary = apply_safe_patch(
            project_path=state.project_path,
            project_name=state.active_project,
            patch_request=patch_request,
        )
        report_path = write_patch_report(
            state.project_path,
            state.active_project,
            summary,
            run_id=state.run_id,
        )
        state.diff_patch_summary = summary
        state.diff_patch_report_path = report_path
        state.notes = f"Diff patch report created at: {report_path}"
    except Exception as e:
        state.notes = f"Diff patch agent failed: {e}"

    return state


def full_automation_agent(state: StudioState):
    print("[Full Automation] Building combined automation summary...")

    if not state.project_path or not state.active_project:
        state.notes = "Full automation agent could not run: missing project info."
        return state

    try:
        summary = build_full_automation_summary(
            computer_use_summary=state.computer_use_summary,
            terminal_summary=state.terminal_summary,
            browser_research_summary=state.browser_research_summary,
            tool_execution_summary=state.tool_execution_summary,
            file_modification_summary=state.file_modification_summary,
            diff_patch_summary=state.diff_patch_summary,
        )
        report_path = write_full_automation_report(
            project_path=state.project_path,
            project_name=state.active_project,
            summary=summary
        )
        state.full_automation_summary = summary
        state.full_automation_report_path = report_path
        state.notes = f"Full automation report created at: {report_path}"
    except Exception as e:
        state.notes = f"Full automation agent failed: {e}"

    return state


def system_health_node(state: StudioState):
    """Evaluate system health and optionally write a small report."""
    summary = evaluate_health(
        project_path=state.project_path,
        run_id=state.run_id,
        execution_session_summary=state.execution_session_summary,
        execution_policy_summary=state.execution_policy_summary,
        notes=state.notes,
        agent_routing_report_path=state.agent_routing_report_path,
    )
    state.system_health_summary = summary
    if state.project_path and state.active_project:
        try:
            report_path = write_system_health_report(
                state.project_path,
                state.active_project,
                summary,
            )
            state.system_health_report_path = report_path
        except Exception:
            pass
    return state


def save_persistent_project_state_node(state: StudioState):
    print("[State] Saving persistent project state...")

    if not state.project_path:
        state.notes = "No project path found for persistent state save."
        return state

    try:
        state.execution_ledger_path = get_ledger_path(state.project_path)
        state.execution_session_summary = finalize_run_context(
            state.execution_session_summary or {},
            status="completed",
        )
        ledger_append(
            state.project_path,
            "workflow_run_completed",
            "completed",
            f"Workflow run completed for project {state.active_project or 'unknown'}.",
            project_name=state.active_project,
            run_id=state.run_id,
            payload={"run_id": state.run_id, "notes": (state.notes or "")[:200]},
        )

        # Persist last_aegis_decision using the stable contract shape.
        from AEGIS.aegis_contract import normalize_aegis_result

        last_aegis_decision_normalized = normalize_aegis_result(
            (state.dispatch_result or {}).get("aegis") if isinstance(state.dispatch_result, dict) else None
        )
        saved_path = save_project_state(
            project_path=state.project_path,
            active_project=state.active_project,
            notes=state.notes,
            architect_plan=state.architect_plan,
            task_queue=state.task_queue,
            coder_output_path=state.coder_output_path,
            implementation_file_path=state.implementation_file_path,
            test_report_path=state.test_report_path,
            docs_output_path=state.docs_output_path,
            execution_report_path=state.execution_report_path,
            workspace_report_path=state.workspace_report_path,
            operator_log_path=state.operator_log_path,
            supervisor_report_path=state.supervisor_report_path,
            supervisor_decision=state.supervisor_decision,
            autonomous_cycle_report_path=state.autonomous_cycle_report_path,
            autonomous_cycle_summary=state.autonomous_cycle_summary,
            computer_use_report_path=state.computer_use_report_path,
            computer_use_summary=state.computer_use_summary,
            tool_execution_report_path=state.tool_execution_report_path,
            tool_execution_summary=state.tool_execution_summary,
            file_modification_report_path=state.file_modification_report_path,
            file_modification_summary=state.file_modification_summary,
            diff_patch_report_path=state.diff_patch_report_path,
            diff_patch_summary=state.diff_patch_summary,
            agent_routing_report_path=state.agent_routing_report_path,
            agent_routing_summary=state.agent_routing_summary,
            execution_bridge_report_path=state.execution_bridge_report_path,
            execution_bridge_summary=state.execution_bridge_summary,
            engine_registry_report_path=state.engine_registry_report_path,
            engine_registry_summary=state.engine_registry_summary,
            capability_registry_report_path=state.capability_registry_report_path,
            capability_registry_summary=state.capability_registry_summary,
            tool_registry_report_path=state.tool_registry_report_path,
            tool_registry_summary=state.tool_registry_summary,
            tool_routing_summary=state.tool_routing_summary,
            workspace_boundary_report_path=state.workspace_boundary_report_path,
            workspace_boundary_summary=state.workspace_boundary_summary,
            path_migration_report_path=state.path_migration_report_path,
            path_migration_summary=state.path_migration_summary,
            execution_policy_summary=state.execution_policy_summary,
            execution_ledger_path=state.execution_ledger_path,
            terminal_report_path=state.terminal_report_path,
            terminal_summary=state.terminal_summary,
            browser_research_report_path=state.browser_research_report_path,
            browser_research_summary=state.browser_research_summary,
            full_automation_report_path=state.full_automation_report_path,
            full_automation_summary=state.full_automation_summary,
            task_queue_snapshot=state.task_queue_snapshot,
            run_id=state.run_id,
            execution_session_summary=state.execution_session_summary,
            system_health_summary=state.system_health_summary,
            system_health_report_path=state.system_health_report_path,
            dispatch_plan_summary=state.dispatch_plan_summary,
            dispatch_status=state.dispatch_status,
            dispatch_result=state.dispatch_result,
            execution_package_id=state.execution_package_id,
            execution_package_path=state.execution_package_path,
            runtime_execution_status=state.runtime_execution_status,
            automation_status=state.automation_status,
            automation_result=state.automation_result,
            agent_selection_summary=state.agent_selection_summary,
            governance_status=state.governance_status,
            governance_result=state.governance_result,
            project_lifecycle_status=state.project_lifecycle_status,
            project_lifecycle_result=state.project_lifecycle_result,
            enforcement_status=state.enforcement_status,
            enforcement_result=state.enforcement_result,
            workflow_route_status=state.workflow_route_status,
            workflow_route_reason=state.workflow_route_reason,
            review_queue_entry=state.review_queue_entry,
            resume_status=state.resume_status,
            resume_result=state.resume_result,
            heartbeat_status=state.heartbeat_status,
            heartbeat_result=state.heartbeat_result,
            scheduler_status=state.scheduler_status,
            scheduler_result=state.scheduler_result,
            completion_result=state.completion_result,
            recovery_status=state.recovery_status,
            recovery_result=state.recovery_result,
            reexecution_status=state.reexecution_status,
            reexecution_result=state.reexecution_result,
            launch_status=state.launch_status,
            launch_result=state.launch_result,
            autonomy_status=state.autonomy_status,
            autonomy_result=state.autonomy_result,
            guardrail_status=state.guardrail_status,
            guardrail_result=state.guardrail_result,
            last_aegis_decision=last_aegis_decision_normalized,
        )
        state.persistent_state_path = saved_path
        state.notes = f"Persistent project state saved at: {saved_path}"

        # Phase 15: outcome-learning at final save stage (passive observer).
        try:
            from NEXUS.learning_engine import build_outcome_learning_record_safe
            from NEXUS.learning_writer import append_learning_record_safe

            sh = state.system_health_summary if isinstance(state.system_health_summary, dict) else {}
            overall = sh.get("overall_status") or state.workflow_route_status or ""
            record = build_outcome_learning_record_safe(
                state=state,
                workflow_stage="workflow_completed",
                decision_source="save_persistent_project_state_node",
                decision_type="workflow_completed",
                decision_summary=str(overall),
            )
            append_learning_record_safe(project_path=state.project_path, record=record)
            # Best-effort summary write; does not affect core workflow outputs.
            try:
                from NEXUS.learning_writer import write_learning_summary_safe

                write_learning_summary_safe(project_path=state.project_path, last_n=50)
            except Exception:
                pass
        except Exception:
            pass
    except Exception as e:
        state.notes = f"Persistent state save failed: {e}"
        state.execution_session_summary = finalize_run_context(
            state.execution_session_summary or {},
            status="failed",
            error_summary=str(e),
        )
        # Reflect save failure in health summary
        health = state.system_health_summary or {}
        flags = list(health.get("safety_flags", []))
        if "workflow_failed" not in flags:
            flags.append("workflow_failed")
        state.system_health_summary = {
            **health,
            "overall_status": "critical",
            "safety_flags": flags,
            "human_review_recommended": True,
            "alerts": list(health.get("alerts", [])) + [f"Persistent state save failed: {e}"],
        }
        try:
            ledger_append(
                state.project_path,
                "workflow_run_failed",
                "failed",
                f"Workflow run failed: {str(e)[:200]}.",
                project_name=state.active_project,
                run_id=state.run_id,
                payload={"run_id": state.run_id, "error": str(e)[:200]},
            )
        except Exception:
            pass

        # Phase 15: record failure outcome (best-effort; never breaks workflow).
        try:
            from NEXUS.learning_engine import build_outcome_learning_record_safe
            from NEXUS.learning_writer import append_learning_record_safe

            record = build_outcome_learning_record_safe(
                state=state,
                workflow_stage="workflow_save_failed",
                decision_source="save_persistent_project_state_node",
                decision_type="workflow_save_failed",
                decision_summary=str(e)[:2000],
            )
            append_learning_record_safe(project_path=state.project_path, record=record)
        except Exception:
            pass

    return state


def build_workflow():
    graph = StateGraph(StudioState)

    graph.add_node("router", route_project)
    graph.add_node("persistent_state_load", load_persistent_project_state)
    graph.add_node("memory", load_memory)
    graph.add_node("architect", architect_agent)
    graph.add_node("task_queue", task_queue_builder)
    graph.add_node("agent_router", agent_router_node)
    graph.add_node("execution_bridge", execution_bridge_node)
    graph.add_node("dispatch_planning", dispatch_planning_node)
    graph.add_node("runtime_dispatch", runtime_dispatch_node)
    graph.add_node("automation_layer", automation_layer_node)
    graph.add_node("governance_layer", governance_layer_node)
    graph.add_node("project_lifecycle", project_lifecycle_node)
    graph.add_node("enforcement_layer", enforcement_layer_node)
    graph.add_node("manual_review_hold", manual_review_hold_node)
    graph.add_node("approval_hold", approval_hold_node)
    graph.add_node("hold_state", hold_state_node)
    graph.add_node("blocked_stop", blocked_stop_node)
    graph.add_node("resume_evaluation", resume_evaluation_node)
    graph.add_node("heartbeat_evaluation", heartbeat_evaluation_node)
    graph.add_node("scheduler_evaluation", scheduler_evaluation_node)
    graph.add_node("recovery_evaluation", recovery_evaluation_node)
    graph.add_node("reexecution_evaluation", reexecution_evaluation_node)
    graph.add_node("engine_registry", engine_registry_node)
    graph.add_node("capability_registry", capability_registry_node)
    graph.add_node("tool_registry", tool_registry_node)
    graph.add_node("workspace_boundary", workspace_boundary_node)
    graph.add_node("path_migration", path_migration_node)
    graph.add_node("coder", coder_agent)
    graph.add_node("tester", tester_agent)
    graph.add_node("docs", docs_agent)
    graph.add_node("executor", executor_agent)
    graph.add_node("workspace", workspace_agent)
    graph.add_node("operator", operator_agent)
    graph.add_node("supervisor", supervisor_agent)
    graph.add_node("studio_supervisor", studio_supervisor_agent)
    graph.add_node("autonomous_cycle", autonomous_cycle_agent)
    graph.add_node("computer_use", computer_use_agent)
    graph.add_node("tool_execution", tool_execution_agent)
    graph.add_node("terminal", terminal_agent)
    graph.add_node("browser_research", browser_research_agent)
    graph.add_node("file_modification", file_modification_agent)
    graph.add_node("diff_patch", diff_patch_agent)
    graph.add_node("full_automation", full_automation_agent)
    graph.add_node("system_health", system_health_node)
    graph.add_node("persistent_state_save", save_persistent_project_state_node)

    graph.set_entry_point("router")

    graph.add_edge("router", "persistent_state_load")
    graph.add_edge("persistent_state_load", "memory")
    graph.add_edge("memory", "architect")
    graph.add_edge("architect", "task_queue")
    graph.add_edge("task_queue", "agent_router")
    graph.add_edge("agent_router", "execution_bridge")
    graph.add_edge("execution_bridge", "dispatch_planning")
    graph.add_edge("dispatch_planning", "runtime_dispatch")
    graph.add_edge("runtime_dispatch", "automation_layer")
    graph.add_edge("automation_layer", "governance_layer")
    graph.add_edge("governance_layer", "project_lifecycle")
    graph.add_edge("project_lifecycle", "enforcement_layer")
    graph.add_conditional_edges(
        "enforcement_layer",
        determine_post_enforcement_route,
        {
            "engine_registry": "engine_registry",
            "manual_review_hold": "manual_review_hold",
            "approval_hold": "approval_hold",
            "hold_state": "hold_state",
            "blocked_stop": "blocked_stop",
        },
    )
    graph.add_edge("manual_review_hold", "resume_evaluation")
    graph.add_edge("approval_hold", "resume_evaluation")
    graph.add_edge("hold_state", "resume_evaluation")
    graph.add_edge("blocked_stop", "resume_evaluation")
    graph.add_edge("resume_evaluation", "heartbeat_evaluation")
    graph.add_edge("heartbeat_evaluation", "scheduler_evaluation")
    graph.add_edge("scheduler_evaluation", "recovery_evaluation")
    graph.add_edge("recovery_evaluation", "reexecution_evaluation")
    graph.add_edge("reexecution_evaluation", "persistent_state_save")
    graph.add_edge("engine_registry", "capability_registry")
    graph.add_edge("capability_registry", "tool_registry")
    graph.add_edge("tool_registry", "workspace_boundary")
    graph.add_edge("workspace_boundary", "path_migration")
    graph.add_edge("path_migration", "coder")
    graph.add_edge("coder", "tester")
    graph.add_edge("tester", "docs")
    graph.add_edge("docs", "executor")
    graph.add_edge("executor", "workspace")
    graph.add_edge("workspace", "operator")
    graph.add_edge("operator", "supervisor")
    graph.add_edge("supervisor", "studio_supervisor")
    graph.add_edge("studio_supervisor", "autonomous_cycle")
    graph.add_edge("autonomous_cycle", "computer_use")
    graph.add_edge("computer_use", "tool_execution")
    graph.add_edge("tool_execution", "terminal")
    graph.add_edge("terminal", "browser_research")
    graph.add_edge("browser_research", "file_modification")
    graph.add_edge("file_modification", "diff_patch")
    graph.add_edge("diff_patch", "full_automation")
    graph.add_edge("full_automation", "system_health")
    graph.add_edge("system_health", "resume_evaluation")
    graph.add_edge("persistent_state_save", END)

    return graph.compile()
