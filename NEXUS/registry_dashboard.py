"""
NEXUS registry dashboard summary layer.

Aggregates project, agent, policy, tool, engine, and capability registry
status into one normalized studio snapshot. Read-only; no UI, no async.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from NEXUS.registry import PROJECTS
from NEXUS.agent_identity_registry import (
    get_active_agent_canonical_names,
    get_planned_agent_canonical_names,
)
from NEXUS.agent_policy_registry import AGENT_POLICY_REGISTRY
from NEXUS.agent_registry import get_runtime_routable_agents
from NEXUS.tool_registry import list_active_tools, list_planned_tools
from NEXUS.engine_registry import list_active_engines, list_planned_engines
from NEXUS.capability_registry import list_active_capabilities, list_planned_capabilities
from NEXUS.runtime_target_registry import get_runtime_target_summary
from NEXUS.runtime_target_selector import get_selection_defaults_summary
from NEXUS.project_state import load_project_state
from NEXUS.studio_coordinator import build_studio_coordination_summary_safe
from NEXUS.studio_driver import build_studio_driver_result_safe


STUDIO_NAME = "NEXUS"


def build_registry_dashboard_summary() -> dict[str, Any]:
    """
    Build a unified registry summary for the studio.

    Returns a normalized snapshot with summary_generated_at, studio_name,
    project_summary, agent_summary, tool_summary, engine_summary,
    capability_summary, policy_summary. Each section has counts and name lists.
    """
    now = datetime.now().isoformat()

    # Projects: registry has no active/planned; use total and names
    project_keys = list(PROJECTS.keys())
    project_names = [PROJECTS[k].get("name") or k for k in project_keys]
    project_summary: dict[str, Any] = {
        "total": len(project_keys),
        "names": project_keys,
        "display_names": project_names,
    }

    # Agents: active / planned from identity registry; routable from agent_registry
    active_agents = get_active_agent_canonical_names()
    planned_agents = get_planned_agent_canonical_names()
    routable_agents = get_runtime_routable_agents()
    agent_summary: dict[str, Any] = {
        "active_count": len(active_agents),
        "planned_count": len(planned_agents),
        "active_names": active_agents,
        "planned_names": planned_agents,
        "routable_names": routable_agents,
        "routable_count": len(routable_agents),
    }

    # Policy: agents with policy entries; optional active/planned from policy_status
    policy_agents = list(AGENT_POLICY_REGISTRY.keys())
    policy_active = [a for a in policy_agents if AGENT_POLICY_REGISTRY.get(a, {}).get("policy_status") == "active"]
    policy_planned = [a for a in policy_agents if AGENT_POLICY_REGISTRY.get(a, {}).get("policy_status") == "planned"]
    policy_summary: dict[str, Any] = {
        "agents_with_policy_count": len(policy_agents),
        "agents_with_policy": policy_agents,
        "policy_active_count": len(policy_active),
        "policy_planned_count": len(policy_planned),
        "policy_active_names": policy_active,
        "policy_planned_names": policy_planned,
    }

    # Tools
    tools_active = list_active_tools()
    tools_planned = list_planned_tools()
    tool_summary: dict[str, Any] = {
        "active_count": len(tools_active),
        "planned_count": len(tools_planned),
        "active_names": tools_active,
        "planned_names": tools_planned,
    }

    # Engines
    engines_active = list_active_engines()
    engines_planned = list_planned_engines()
    engine_summary: dict[str, Any] = {
        "active_count": len(engines_active),
        "planned_count": len(engines_planned),
        "active_names": engines_active,
        "planned_names": engines_planned,
    }

    # Capabilities
    caps_active = list_active_capabilities()
    caps_planned = list_planned_capabilities()
    capability_summary: dict[str, Any] = {
        "active_count": len(caps_active),
        "planned_count": len(caps_planned),
        "active_names": caps_active,
        "planned_names": caps_planned,
    }

    # Runtime targets: active / planned
    runtime_target_summary = get_runtime_target_summary()
    # Selection defaults (target mappings)
    runtime_selection_defaults = get_selection_defaults_summary()

    # Dispatch planning: per-project from persisted state
    dispatch_by_project: dict[str, dict[str, Any]] = {}
    ready_count = 0
    dispatch_status_by_project: dict[str, str] = {}
    dispatch_status_count: dict[str, int] = {}
    automation_status_by_project: dict[str, str] = {}
    automation_status_count: dict[str, int] = {}
    recommended_action_by_project: dict[str, str] = {}
    agent_selection_by_project: dict[str, str] = {}
    agent_role_count: dict[str, int] = {}
    governance_status_by_project: dict[str, str] = {}
    governance_status_count: dict[str, int] = {}
    risk_level_count: dict[str, int] = {}
    project_lifecycle_by_project: dict[str, str] = {}
    project_lifecycle_status_count: dict[str, int] = {}
    lifecycle_stage_count: dict[str, int] = {}
    enforcement_status_by_project: dict[str, str] = {}
    enforcement_status_count: dict[str, int] = {}
    workflow_action_count: dict[str, int] = {}
    queue_status_by_project: dict[str, str] = {}
    review_queue_count_by_type: dict[str, int] = {}
    queued_projects: list[str] = []
    resume_status_by_project: dict[str, str] = {}
    resume_status_count: dict[str, int] = {}
    heartbeat_status_by_project: dict[str, str] = {}
    heartbeat_status_count: dict[str, int] = {}
    heartbeat_action_count: dict[str, int] = {}
    scheduler_status_by_project: dict[str, str] = {}
    scheduler_status_count: dict[str, int] = {}
    next_cycle_permitted_count: int = 0
    scheduler_action_count: dict[str, int] = {}
    states_by_project: dict[str, dict[str, Any]] = {}
    recovery_status_by_project: dict[str, str] = {}
    recovery_status_count: dict[str, int] = {}
    retry_ready_count: int = 0
    repair_required_count: int = 0
    reexecution_status_by_project: dict[str, str] = {}
    reexecution_status_count: dict[str, int] = {}
    run_permitted_count: int = 0
    reexecution_action_count: dict[str, int] = {}
    launch_status_by_project: dict[str, str] = {}
    launch_status_count: dict[str, int] = {}
    execution_started_count: int = 0
    launch_action_count: dict[str, int] = {}
    launch_source_count: dict[str, int] = {}
    autonomy_status_by_project: dict[str, str] = {}
    autonomy_status_count: dict[str, int] = {}
    autonomous_run_started_count: int = 0
    guardrail_status_by_project: dict[str, str] = {}
    guardrail_status_count: dict[str, int] = {}
    recursion_blocked_count: int = 0
    state_repair_recommended_count: int = 0
    for key in project_keys:
        path = PROJECTS[key].get("path")
        if not path:
            continue
        try:
            loaded = load_project_state(path)
            if "load_error" in loaded:
                continue
            states_by_project[key] = loaded
            dps = loaded.get("dispatch_plan_summary") or {}
            dispatch_by_project[key] = {
                "dispatch_planning_status": dps.get("dispatch_planning_status"),
                "ready_for_dispatch": dps.get("ready_for_dispatch", False),
                "runtime_target_id": dps.get("runtime_target_id"),
                "runtime_node": dps.get("runtime_node"),
                "task_type": dps.get("task_type"),
            }
            if dps.get("ready_for_dispatch"):
                ready_count += 1
            ds = loaded.get("dispatch_status") or "none"
            dispatch_status_by_project[key] = ds
            dispatch_status_count[ds] = dispatch_status_count.get(ds, 0) + 1
            a_status = loaded.get("automation_status") or "none"
            automation_status_by_project[key] = a_status
            automation_status_count[a_status] = automation_status_count.get(a_status, 0) + 1
            a_result = loaded.get("automation_result") or {}
            if a_result.get("recommended_action"):
                recommended_action_by_project[key] = str(a_result.get("recommended_action"))
            agent_sel = loaded.get("agent_selection_summary") or {}
            sel_agent = agent_sel.get("selected_agent") or agent_sel.get("agent_role") or "none"
            agent_selection_by_project[key] = str(sel_agent)
            role = agent_sel.get("agent_role")
            if role:
                agent_role_count[role] = agent_role_count.get(role, 0) + 1
            g_status = loaded.get("governance_status") or (loaded.get("governance_result") or {}).get("governance_status") or "none"
            governance_status_by_project[key] = str(g_status)
            governance_status_count[g_status] = governance_status_count.get(g_status, 0) + 1
            g_result = loaded.get("governance_result") or {}
            r_level = g_result.get("risk_level")
            if r_level:
                risk_level_count[r_level] = risk_level_count.get(r_level, 0) + 1
            pl_status = loaded.get("project_lifecycle_status") or (loaded.get("project_lifecycle_result") or {}).get("lifecycle_status") or "none"
            project_lifecycle_by_project[key] = str(pl_status)
            project_lifecycle_status_count[pl_status] = project_lifecycle_status_count.get(pl_status, 0) + 1
            pl_result = loaded.get("project_lifecycle_result") or {}
            pl_stage = pl_result.get("lifecycle_stage")
            if pl_stage:
                lifecycle_stage_count[pl_stage] = lifecycle_stage_count.get(pl_stage, 0) + 1
            e_status = loaded.get("enforcement_status") or (loaded.get("enforcement_result") or {}).get("enforcement_status") or "none"
            enforcement_status_by_project[key] = str(e_status)
            enforcement_status_count[e_status] = enforcement_status_count.get(e_status, 0) + 1
            wf_action = (loaded.get("enforcement_result") or {}).get("workflow_action")
            if wf_action:
                workflow_action_count[str(wf_action)] = workflow_action_count.get(str(wf_action), 0) + 1
            qe = loaded.get("review_queue_entry") or {}
            q_status = qe.get("queue_status") or "none"
            q_type = qe.get("queue_type") or "none"
            queue_status_by_project[key] = str(q_status)
            review_queue_count_by_type[q_type] = review_queue_count_by_type.get(q_type, 0) + 1
            if q_status == "queued":
                queued_projects.append(key)
            r_status = loaded.get("resume_status") or (loaded.get("resume_result") or {}).get("resume_status") or "none"
            resume_status_by_project[key] = str(r_status)
            resume_status_count[r_status] = resume_status_count.get(r_status, 0) + 1
            h_status = loaded.get("heartbeat_status") or (loaded.get("heartbeat_result") or {}).get("heartbeat_status") or "none"
            heartbeat_status_by_project[key] = str(h_status)
            heartbeat_status_count[h_status] = heartbeat_status_count.get(h_status, 0) + 1
            h_action = (loaded.get("heartbeat_result") or {}).get("heartbeat_action")
            if h_action:
                heartbeat_action_count[str(h_action)] = heartbeat_action_count.get(str(h_action), 0) + 1
            sr = loaded.get("scheduler_result") or {}
            sched_status = loaded.get("scheduler_status") or sr.get("scheduler_status") or "none"
            scheduler_status_by_project[key] = str(sched_status)
            scheduler_status_count[sched_status] = scheduler_status_count.get(sched_status, 0) + 1
            if sr.get("next_cycle_permitted"):
                next_cycle_permitted_count += 1
            sched_action = sr.get("scheduler_action")
            if sched_action:
                scheduler_action_count[str(sched_action)] = scheduler_action_count.get(str(sched_action), 0) + 1
            rec = loaded.get("recovery_result") or {}
            rec_status = loaded.get("recovery_status") or rec.get("recovery_status") or "none"
            recovery_status_by_project[key] = str(rec_status)
            recovery_status_count[rec_status] = recovery_status_count.get(rec_status, 0) + 1
            if rec.get("retry_permitted"):
                retry_ready_count += 1
            if rec.get("repair_required"):
                repair_required_count += 1
            rex = loaded.get("reexecution_result") or {}
            rex_status = loaded.get("reexecution_status") or rex.get("reexecution_status") or "none"
            reexecution_status_by_project[key] = str(rex_status)
            reexecution_status_count[rex_status] = reexecution_status_count.get(rex_status, 0) + 1
            if rex.get("run_permitted"):
                run_permitted_count += 1
            rex_action = rex.get("reexecution_action")
            if rex_action:
                reexecution_action_count[str(rex_action)] = reexecution_action_count.get(str(rex_action), 0) + 1
            lr = loaded.get("launch_result") or {}
            launch_s = loaded.get("launch_status") or lr.get("launch_status") or "none"
            launch_status_by_project[key] = str(launch_s)
            launch_status_count[launch_s] = launch_status_count.get(launch_s, 0) + 1
            if lr.get("execution_started"):
                execution_started_count += 1
            la_action = lr.get("launch_action")
            if la_action:
                launch_action_count[str(la_action)] = launch_action_count.get(str(la_action), 0) + 1
            la_src = lr.get("source")
            if la_src:
                launch_source_count[str(la_src)] = launch_source_count.get(str(la_src), 0) + 1
            ar = loaded.get("autonomy_result") or {}
            a_status = loaded.get("autonomy_status") or ar.get("autonomy_status") or "none"
            autonomy_status_by_project[key] = str(a_status)
            autonomy_status_count[a_status] = autonomy_status_count.get(a_status, 0) + 1
            if ar.get("autonomous_run_started"):
                autonomous_run_started_count += 1
            gr = loaded.get("guardrail_result") or {}
            g_status = loaded.get("guardrail_status") or gr.get("guardrail_status") or "none"
            guardrail_status_by_project[key] = str(g_status)
            guardrail_status_count[g_status] = guardrail_status_count.get(g_status, 0) + 1
            if gr.get("recursion_blocked"):
                recursion_blocked_count += 1
            if gr.get("state_repair_recommended"):
                state_repair_recommended_count += 1
        except Exception:
            continue

    studio_coordination_summary = build_studio_coordination_summary_safe(states_by_project)
    studio_driver_summary = build_studio_driver_result_safe(
        studio_coordination_summary=studio_coordination_summary,
        states_by_project=states_by_project,
    )

    dispatch_planning_summary: dict[str, Any] = {
        "dispatch_planning_status": "planned" if dispatch_by_project else "no_data",
        "ready_for_dispatch_count": ready_count,
        "by_project": dispatch_by_project,
    }

    execution_status_by_project: dict[str, str] = {}
    execution_status_count: dict[str, int] = {}
    for k, ds in dispatch_status_by_project.items():
        # Read from already-loaded state where available (by reloading would be overkill here)
        # Use persisted runtime_execution_status if present; otherwise leave as unknown.
        try:
            path = PROJECTS[k].get("path")
            loaded = load_project_state(path) if path else {}
            exec_status = loaded.get("runtime_execution_status") or (loaded.get("dispatch_result") or {}).get("execution_status") or "unknown"
        except Exception:
            exec_status = "unknown"
        execution_status_by_project[k] = exec_status
        execution_status_count[exec_status] = execution_status_count.get(exec_status, 0) + 1

    return {
        "summary_generated_at": now,
        "studio_name": STUDIO_NAME,
        "project_summary": project_summary,
        "agent_summary": agent_summary,
        "policy_summary": policy_summary,
        "tool_summary": tool_summary,
        "engine_summary": engine_summary,
        "capability_summary": capability_summary,
        "runtime_target_summary": runtime_target_summary,
        "runtime_selection_defaults": runtime_selection_defaults,
        "dispatch_planning_summary": dispatch_planning_summary,
        "dispatch_status_count": dispatch_status_count,
        "dispatch_status_by_project": dispatch_status_by_project,
        "execution_status_by_project": execution_status_by_project,
        "execution_status_count": execution_status_count,
        "automation_status_count": automation_status_count,
        "automation_status_by_project": automation_status_by_project,
        "recommended_action_by_project": recommended_action_by_project,
        "agent_selection_by_project": agent_selection_by_project,
        "agent_role_count": agent_role_count,
        "governance_status_by_project": governance_status_by_project,
        "governance_status_count": governance_status_count,
        "risk_level_count": risk_level_count,
        "project_lifecycle_by_project": project_lifecycle_by_project,
        "project_lifecycle_status_count": project_lifecycle_status_count,
        "lifecycle_stage_count": lifecycle_stage_count,
        "enforcement_status_by_project": enforcement_status_by_project,
        "enforcement_status_count": enforcement_status_count,
        "workflow_action_count": workflow_action_count,
        "queue_status_by_project": queue_status_by_project,
        "review_queue_count_by_type": review_queue_count_by_type,
        "queued_projects": queued_projects,
        "resume_status_by_project": resume_status_by_project,
        "resume_status_count": resume_status_count,
        "heartbeat_status_by_project": heartbeat_status_by_project,
        "heartbeat_status_count": heartbeat_status_count,
        "heartbeat_action_count": heartbeat_action_count,
        "scheduler_status_by_project": scheduler_status_by_project,
        "scheduler_status_count": scheduler_status_count,
        "next_cycle_permitted_count": next_cycle_permitted_count,
        "scheduler_action_count": scheduler_action_count,
        "studio_coordination_summary": studio_coordination_summary,
        "recovery_status_by_project": recovery_status_by_project,
        "recovery_status_count": recovery_status_count,
        "retry_ready_count": retry_ready_count,
        "repair_required_count": repair_required_count,
        "reexecution_status_by_project": reexecution_status_by_project,
        "reexecution_status_count": reexecution_status_count,
        "run_permitted_count": run_permitted_count,
        "reexecution_action_count": reexecution_action_count,
        "studio_driver_summary": studio_driver_summary,
        "launch_status_by_project": launch_status_by_project,
        "launch_status_count": launch_status_count,
        "execution_started_count": execution_started_count,
        "launch_action_count": launch_action_count,
        "launch_source_count": launch_source_count,
        "autonomy_status_by_project": autonomy_status_by_project,
        "autonomy_status_count": autonomy_status_count,
        "autonomous_run_started_count": autonomous_run_started_count,
        "guardrail_status_by_project": guardrail_status_by_project,
        "guardrail_status_count": guardrail_status_count,
        "recursion_blocked_count": recursion_blocked_count,
        "state_repair_recommended_count": state_repair_recommended_count,
    }
