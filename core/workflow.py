from langgraph.graph import StateGraph, END
from core.state import StudioState
from core.router import detect_project
from core.registry import PROJECTS
from core.memory import load_project_context
from core.llm import generate_architect_plan
from core.tasks import build_task_queue
from core.coder import write_coder_output, mark_first_pending_task_complete
from core.implementer import write_controlled_implementation_file
from core.tester import write_test_report
from core.docs_writer import write_docs_update
from core.project_state import load_project_state, save_project_state
from core.executor import run_safe_commands, write_execution_report
from core.workspace import scan_workspace, write_workspace_report
from core.operator_agent import run_operator_sequence
from core.supervisor import build_supervisor_decision, write_supervisor_report
from core.studio_supervisor import summarize_all_projects, write_studio_supervisor_report
from core.autonomous_cycle import build_autonomous_cycle_summary, write_autonomous_cycle_report
from core.computer_use import build_computer_use_summary, write_computer_use_report
from core.tool_runner import run_tool_sequence, write_tool_execution_report
from core.file_modifier import append_controlled_update, write_file_modification_report
from core.diff_patch import (
    build_patch_request_from_architect_plan,
    apply_safe_patch,
    write_patch_report,
)
from core.agent_router import build_agent_route, write_agent_router_report
from core.execution_bridge import build_execution_bridge_packet, write_execution_bridge_report
from core.engine_inspector import build_engine_summary, write_engine_report
from core.terminal_controller import run_allowed_commands, write_terminal_report
from core.browser_agent import open_safe_research_urls, write_browser_research_report
from core.full_automation import build_full_automation_summary, write_full_automation_report


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

    return state


def load_memory(state: StudioState):
    print("[Memory] Loading project docs, memory, and tasks...")

    if not state.project_path:
        state.notes = "No project path found."
        return state

    state.loaded_context = load_project_context(state.project_path)
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
    return state


def task_queue_builder(state: StudioState):
    print("[Task Manager] Building task queue...")

    queue = build_task_queue(state.architect_plan)
    state.task_queue = queue

    for i, task in enumerate(queue):
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
        )
        state.agent_routing_summary = summary
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
            project_path=state.project_path,
            project_name=state.active_project,
            results=results
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
            project_path=state.project_path,
            project_name=state.active_project or "unknown_project",
            summary=summary
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
            project_path=state.project_path,
            project_name=state.active_project,
            summary=summary
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


def save_persistent_project_state_node(state: StudioState):
    print("[State] Saving persistent project state...")

    if not state.project_path:
        state.notes = "No project path found for persistent state save."
        return state

    try:
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
            terminal_report_path=state.terminal_report_path,
            terminal_summary=state.terminal_summary,
            browser_research_report_path=state.browser_research_report_path,
            browser_research_summary=state.browser_research_summary,
            full_automation_report_path=state.full_automation_report_path,
            full_automation_summary=state.full_automation_summary,
        )
        state.persistent_state_path = saved_path
        state.notes = f"Persistent project state saved at: {saved_path}"
    except Exception as e:
        state.notes = f"Persistent state save failed: {e}"

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
    graph.add_node("engine_registry", engine_registry_node)
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
    graph.add_node("persistent_state_save", save_persistent_project_state_node)

    graph.set_entry_point("router")

    graph.add_edge("router", "persistent_state_load")
    graph.add_edge("persistent_state_load", "memory")
    graph.add_edge("memory", "architect")
    graph.add_edge("architect", "task_queue")
    graph.add_edge("task_queue", "agent_router")
    graph.add_edge("agent_router", "execution_bridge")
    graph.add_edge("execution_bridge", "engine_registry")
    graph.add_edge("engine_registry", "coder")
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
    graph.add_edge("full_automation", "persistent_state_save")
    graph.add_edge("persistent_state_save", END)

    return graph.compile()