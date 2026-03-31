"""
NEXUS registry dashboard summary layer.

Aggregates project, agent, policy, tool, engine, and capability registry
status into one normalized studio snapshot. Read-only; no UI, no async.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from NEXUS.registry import PROJECTS
from NEXUS.agent_identity_registry import (
    get_active_agent_canonical_names,
    get_planned_agent_canonical_names,
)
from NEXUS.agent_policy_registry import AGENT_POLICY_REGISTRY
from NEXUS.agent_registry import get_runtime_routable_agents
from NEXUS.tool_registry import TOOL_REGISTRY, TOOL_CONTRACT_VERSION, list_active_tools, list_planned_tools
from NEXUS.engine_registry import list_active_engines, list_planned_engines
from NEXUS.capability_registry import list_active_capabilities, list_planned_capabilities
from NEXUS.runtime_target_registry import get_runtime_target_summary
from NEXUS.runtime_target_selector import get_selection_defaults_summary
from NEXUS.project_state import load_project_state
from NEXUS.portfolio_autonomy_controls import read_portfolio_kill_switch
from NEXUS.portfolio_autonomy_trace import read_portfolio_trace_tail
from NEXUS.project_routing import evaluate_project_selection
from NEXUS.studio_coordinator import build_studio_coordination_summary_safe
from NEXUS.studio_driver import build_studio_driver_result_safe


STUDIO_NAME = "NEXUS"


def _build_release_readiness_from_dashboard(
    *,
    product_summary: dict[str, Any],
    approval_summary: dict[str, Any],
    patch_proposal_summary: dict[str, Any],
    execution_environment_summary: dict[str, Any],
    autonomy_summary: dict[str, Any],
    helix_summary: dict[str, Any],
) -> dict[str, Any]:
    """Build release readiness from dashboard summaries (Phase 26). Read-only."""
    try:
        from NEXUS.release_readiness import build_release_readiness_safe
        minimal = {
            "product_summary": product_summary,
            "approval_summary": approval_summary,
            "patch_proposal_summary": patch_proposal_summary,
            "execution_environment_summary": execution_environment_summary,
            "autonomy_summary": autonomy_summary,
            "helix_summary": helix_summary,
        }
        return build_release_readiness_safe(dashboard_summary=minimal)
    except Exception:
        return {
            "release_readiness_status": "error_fallback",
            "project_name": None,
            "product_status": "unknown",
            "approval_status": "unknown",
            "execution_environment_status": "unknown",
            "patch_status": "unknown",
            "autonomy_status": "unknown",
            "helix_status": "unknown",
            "critical_blockers": ["Release readiness unavailable."],
            "review_items": [],
            "readiness_reason": "Release readiness unavailable.",
            "ready_for_operator_release": False,
            "trace_links_present": {
                "approval_linked": False,
                "patch_linked": False,
                "autonomy_linked": False,
                "product_linked": False,
                "helix_linked": False,
                "review_linked": False,
            },
            "generated_at": datetime.now().isoformat(),
            "review_status_summary": "",
            "review_blocker_count": 0,
            "review_required_count": 0,
            "changes_requested_count": 0,
            "approved_for_approval_count": 0,
            "candidates_pending_review": 0,
            "candidates_not_ready_for_review": 0,
            "review_linkage_present": False,
            "review_reasoning": [],
        }


def _build_cross_artifact_trace_for_dashboard() -> dict[str, Any]:
    """Build cross-artifact trace for dashboard (Phase 27). Read-only; studio-wide."""
    try:
        from NEXUS.cross_artifact_trace import build_cross_artifact_trace_safe
        return build_cross_artifact_trace_safe(n_recent=30)
    except Exception:
        return {
            "trace_status": "error_fallback",
            "project_name": None,
            "approval_ids": [],
            "patch_ids": [],
            "helix_ids": [],
            "autonomy_ids": [],
            "product_ids": [],
            "learning_record_refs": [],
            "link_completeness": {
                "approval_to_patch": False,
                "patch_to_helix": False,
                "patch_to_product": False,
                "autonomy_to_product": False,
                "helix_to_autonomy": False,
            },
            "missing_links": ["Cross-artifact trace unavailable."],
            "trace_reason": "Cross-artifact trace unavailable.",
            "generated_at": datetime.now().isoformat(),
            "artifact_counts": {
                "approvals": 0,
                "patches": 0,
                "helix_runs": 0,
                "autonomy_runs": 0,
                "products": 0,
                "learning_records": 0,
            },
        }


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
    sensitivity_counts: dict[str, int] = {}
    for _name, meta in TOOL_REGISTRY.items():
        s = meta.get("sensitivity") or "unknown"
        sensitivity_counts[s] = sensitivity_counts.get(s, 0) + 1
    tool_summary: dict[str, Any] = {
        "active_count": len(tools_active),
        "planned_count": len(tools_planned),
        "active_names": tools_active,
        "planned_names": tools_planned,
        "tool_contract_version": TOOL_CONTRACT_VERSION,
        "sensitivity_counts": sensitivity_counts,
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
    governance_resolution_state_by_project: dict[str, str] = {}
    governance_resolution_state_count: dict[str, int] = {}
    governance_routing_outcome_by_project: dict[str, str] = {}
    governance_routing_outcome_count: dict[str, int] = {}
    governance_conflict_status_by_project: dict[str, str] = {}
    governance_conflict_status_count: dict[str, int] = {}
    governance_conflict_type_by_project: dict[str, str] = {}
    governance_conflict_type_count: dict[str, int] = {}
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
    execution_package_counts_by_project: dict[str, int] = {}
    execution_package_pending_by_project: dict[str, int] = {}
    latest_execution_package_id_by_project: dict[str, str] = {}
    latest_execution_package_path_by_project: dict[str, str] = {}
    execution_package_review_required_projects: list[str] = []
    execution_package_sealed_count_total = 0
    execution_package_recent_by_project: dict[str, list[dict[str, Any]]] = {}
    execution_package_decision_counts_by_project: dict[str, dict[str, int]] = {}
    latest_execution_package_decision_status_by_project: dict[str, str] = {}
    execution_package_decision_required_projects: list[str] = []
    execution_package_eligibility_counts_by_project: dict[str, dict[str, int]] = {}
    latest_execution_package_eligibility_status_by_project: dict[str, str] = {}
    execution_package_eligible_projects: list[str] = []
    execution_package_ineligible_projects: list[str] = []
    execution_package_release_counts_by_project: dict[str, dict[str, int]] = {}
    latest_execution_package_release_status_by_project: dict[str, str] = {}
    execution_package_released_projects: list[str] = []
    execution_package_release_blocked_projects: list[str] = []
    execution_package_handoff_counts_by_project: dict[str, dict[str, int]] = {}
    latest_execution_package_handoff_status_by_project: dict[str, str] = {}
    latest_execution_package_handoff_target_by_project: dict[str, str] = {}
    execution_package_handoff_authorized_projects: list[str] = []
    execution_package_handoff_blocked_projects: list[str] = []
    execution_package_cursor_bridge_counts_by_project: dict[str, dict[str, int]] = {}
    latest_execution_package_cursor_bridge_status_by_project: dict[str, str] = {}
    latest_execution_package_bridge_task_id_by_project: dict[str, str] = {}
    execution_package_cursor_bridge_artifact_count_by_project: dict[str, int] = {}
    cursor_bridge_prepared_projects: list[str] = []
    cursor_bridge_artifact_return_projects: list[str] = []
    execution_package_execution_counts_by_project: dict[str, dict[str, int]] = {}
    latest_execution_package_execution_status_by_project: dict[str, str] = {}
    latest_execution_package_execution_target_by_project: dict[str, str] = {}
    execution_package_execution_succeeded_projects: list[str] = []
    execution_package_execution_failed_projects: list[str] = []
    execution_package_execution_blocked_projects: list[str] = []
    execution_package_execution_rolled_back_projects: list[str] = []
    execution_package_duplicate_success_block_count_by_project: dict[str, int] = {}
    execution_package_retry_ready_count_by_project: dict[str, int] = {}
    execution_package_repair_required_count_by_project: dict[str, int] = {}
    execution_package_rollback_repair_failed_count_by_project: dict[str, int] = {}
    execution_package_integrity_verified_count_by_project: dict[str, int] = {}
    execution_package_integrity_issues_count_by_project: dict[str, int] = {}
    execution_package_evaluation_counts_by_project: dict[str, dict[str, int]] = {}
    latest_execution_package_evaluation_status_by_project: dict[str, str] = {}
    execution_quality_band_count_total: dict[str, int] = {"critical": 0, "weak": 0, "mixed": 0, "strong": 0, "excellent": 0}
    integrity_band_count_total: dict[str, int] = {"critical": 0, "weak": 0, "mixed": 0, "strong": 0, "excellent": 0}
    rollback_quality_band_count_total: dict[str, int] = {"critical": 0, "weak": 0, "mixed": 0, "strong": 0, "excellent": 0}
    failure_risk_band_count_total: dict[str, int] = {"low": 0, "guarded": 0, "elevated": 0, "high": 0, "critical": 0}
    execution_package_local_analysis_counts_by_project: dict[str, dict[str, int]] = {}
    latest_execution_package_local_analysis_status_by_project: dict[str, str] = {}
    local_analysis_confidence_band_count_total: dict[str, int] = {"low": 0, "guarded": 0, "moderate": 0, "high": 0}
    local_analysis_suggested_next_action_count_total: dict[str, int] = {}
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
    runtime_route_by_project: dict[str, str] = {}
    runtime_route_count: dict[str, int] = {}
    model_route_by_project: dict[str, str] = {}
    model_route_count: dict[str, int] = {}
    selected_target_by_project: dict[str, str] = {}
    target_selection_status_by_project: dict[str, str] = {}
    target_readiness_by_project: dict[str, str] = {}
    target_availability_by_project: dict[str, str] = {}
    target_denial_reason_by_project: dict[str, str] = {}
    last_target_selection_reason_by_project: dict[str, str] = {}
    target_selection_status_count: dict[str, int] = {}
    deployment_preflight_count: dict[str, int] = {}
    change_gate_status_count: dict[str, int] = {}
    regression_status_count: dict[str, int] = {}
    prism_status_by_project: dict[str, str] = {}
    prism_recommendation_count: dict[str, int] = {"go": 0, "revise": 0, "hold": 0}
    autopilot_status_by_project: dict[str, str] = {}
    iteration_counts_by_project: dict[str, dict[str, int]] = {}
    latest_autopilot_action_by_project: dict[str, str] = {}
    stop_rail_status_by_project: dict[str, str] = {}
    stop_rail_type_by_project: dict[str, str] = {}
    stop_reason_by_project: dict[str, str] = {}
    stop_rail_routing_outcome_by_project: dict[str, str] = {}
    rail_pause_count_total = 0
    rail_escalate_count_total = 0
    rail_stop_count_total = 0
    autonomy_mode_by_project: dict[str, str] = {}
    routing_status_by_project: dict[str, str] = {}
    routed_action_by_project: dict[str, str] = {}
    project_selection_status_by_project: dict[str, str] = {}
    last_project_selection_reason_by_project: dict[str, str] = {}
    supervised_mode_count_total = 0
    assisted_mode_count_total = 0
    low_risk_mode_count_total = 0
    active_autopilot_projects: list[str] = []
    escalation_count_total = 0
    paused_count_total = 0
    completed_count_total = 0
    blocked_count_total = 0
    from NEXUS.execution_package_registry import list_execution_package_journal_entries
    for key in project_keys:
        path = PROJECTS[key].get("path")
        if not path:
            continue
        try:
            loaded = load_project_state(path)
            if "load_error" in loaded:
                continue
            states_by_project[key] = loaded
            autopilot_status = str(loaded.get("autopilot_status") or "idle")
            autopilot_status_by_project[key] = autopilot_status
            iteration_counts_by_project[key] = {
                "iteration_count": max(0, int(loaded.get("autopilot_iteration_count") or 0)),
                "iteration_limit": max(0, int(loaded.get("autopilot_iteration_limit") or 0)),
            }
            latest_autopilot_action_by_project[key] = str(loaded.get("autopilot_next_action") or "")
            stop_rail_result = loaded.get("autonomy_stop_rail_result") if isinstance(loaded.get("autonomy_stop_rail_result"), dict) else {}
            stop_rail_status = str(loaded.get("autonomy_stop_rail_status") or stop_rail_result.get("status") or "ok")
            stop_rail_status_by_project[key] = stop_rail_status
            stop_rail_type_by_project[key] = str(stop_rail_result.get("rail_type") or "")
            stop_reason_by_project[key] = str(stop_rail_result.get("stop_reason") or "")
            stop_rail_outcome = str(stop_rail_result.get("routing_outcome") or "")
            stop_rail_routing_outcome_by_project[key] = stop_rail_outcome
            if stop_rail_outcome == "pause":
                rail_pause_count_total += 1
            elif stop_rail_outcome == "escalate":
                rail_escalate_count_total += 1
            elif stop_rail_outcome == "stop":
                rail_stop_count_total += 1
            autonomy_mode = str(loaded.get("autonomy_mode") or "supervised_build")
            autonomy_mode_by_project[key] = autonomy_mode
            if autonomy_mode == "supervised_build":
                supervised_mode_count_total += 1
            elif autonomy_mode == "assisted_autopilot":
                assisted_mode_count_total += 1
            elif autonomy_mode == "low_risk_autonomous_development":
                low_risk_mode_count_total += 1
            routing_status_by_project[key] = str(loaded.get("project_routing_status") or "idle")
            routing_result = loaded.get("project_routing_result") if isinstance(loaded.get("project_routing_result"), dict) else {}
            routed_action_by_project[key] = str(routing_result.get("selected_action") or "")
            project_selection_status_by_project[key] = str(loaded.get("project_selection_status") or "idle")
            project_selection_result = loaded.get("project_selection_result") if isinstance(loaded.get("project_selection_result"), dict) else {}
            last_project_selection_reason_by_project[key] = str(project_selection_result.get("selection_reason") or "")
            if autopilot_status in ("ready", "running", "paused", "escalated", "blocked"):
                active_autopilot_projects.append(key)
            if autopilot_status == "escalated":
                escalation_count_total += 1
            if autopilot_status == "paused":
                paused_count_total += 1
            if autopilot_status == "completed":
                completed_count_total += 1
            if autopilot_status == "blocked":
                blocked_count_total += 1
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
            dispatch_result = loaded.get("dispatch_result") if isinstance(loaded.get("dispatch_result"), dict) else {}
            runtime_target_selection = dispatch_result.get("runtime_target_selection") if isinstance(dispatch_result.get("runtime_target_selection"), dict) else {}
            selected_target_by_project[key] = str(
                runtime_target_selection.get("selected_target_id")
                or dispatch_result.get("runtime")
                or dps.get("runtime_target_id")
                or ""
            )
            selection_status = str(runtime_target_selection.get("status") or "none")
            target_selection_status_by_project[key] = selection_status
            target_selection_status_count[selection_status] = target_selection_status_count.get(selection_status, 0) + 1
            target_readiness_by_project[key] = str(runtime_target_selection.get("readiness_status") or "")
            target_availability_by_project[key] = str(runtime_target_selection.get("availability_status") or "")
            target_denial_reason_by_project[key] = str(runtime_target_selection.get("denial_reason") or "")
            last_target_selection_reason_by_project[key] = str(runtime_target_selection.get("selection_reason") or "")
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
            resolution_state = str(g_result.get("resolution_state") or "resolved")
            governance_resolution_state_by_project[key] = resolution_state
            governance_resolution_state_count[resolution_state] = governance_resolution_state_count.get(resolution_state, 0) + 1
            routing_outcome = str(g_result.get("routing_outcome") or "continue")
            governance_routing_outcome_by_project[key] = routing_outcome
            governance_routing_outcome_count[routing_outcome] = governance_routing_outcome_count.get(routing_outcome, 0) + 1
            conflict_status = str(((g_result.get("governance_conflict") or {}).get("status")) or "none")
            governance_conflict_status_by_project[key] = conflict_status
            governance_conflict_status_count[conflict_status] = governance_conflict_status_count.get(conflict_status, 0) + 1
            conflict_type = str(g_result.get("conflict_type") or ((g_result.get("governance_conflict") or {}).get("conflict_type")) or "none")
            governance_conflict_type_by_project[key] = conflict_type
            governance_conflict_type_count[conflict_type] = governance_conflict_type_count.get(conflict_type, 0) + 1
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
            execution_package_rows = list_execution_package_journal_entries(project_path=path, n=10)
            execution_package_recent_by_project[key] = execution_package_rows
            execution_package_counts_by_project[key] = len(execution_package_rows)
            pending_count = sum(
                1
                for row in execution_package_rows
                if str(row.get("review_status") or "") in ("pending", "review_pending")
                or str(row.get("package_status") or "") in ("pending", "review_pending")
            )
            execution_package_pending_by_project[key] = pending_count
            execution_package_sealed_count_total += sum(1 for row in execution_package_rows if bool(row.get("sealed")))
            if pending_count > 0:
                execution_package_review_required_projects.append(key)
                execution_package_decision_required_projects.append(key)
            decision_counts = {"pending": 0, "approved": 0, "rejected": 0}
            eligibility_counts = {"pending": 0, "eligible": 0, "ineligible": 0}
            release_counts = {"pending": 0, "released": 0, "blocked": 0}
            handoff_counts = {"pending": 0, "authorized": 0, "blocked": 0}
            cursor_bridge_counts = {"none": 0, "prepared": 0, "artifact_recorded": 0, "denied": 0}
            execution_counts = {"pending": 0, "succeeded": 0, "failed": 0, "blocked": 0, "rolled_back": 0}
            evaluation_counts = {"pending": 0, "completed": 0, "blocked": 0, "error_fallback": 0}
            local_analysis_counts = {"pending": 0, "completed": 0, "blocked": 0, "error_fallback": 0}
            duplicate_success_block_count = 0
            retry_ready_count_project = 0
            repair_required_count_project = 0
            rollback_repair_failed_count = 0
            integrity_verified_count = 0
            integrity_issues_count = 0
            for row in execution_package_rows:
                ds = str(row.get("decision_status") or "pending").strip().lower()
                if ds not in decision_counts:
                    ds = "pending"
                decision_counts[ds] += 1
                es = str(row.get("eligibility_status") or "pending").strip().lower()
                if es not in eligibility_counts:
                    es = "pending"
                eligibility_counts[es] += 1
                rs = str(row.get("release_status") or "pending").strip().lower()
                if rs not in release_counts:
                    rs = "pending"
                release_counts[rs] += 1
                hs = str(row.get("handoff_status") or "pending").strip().lower()
                if hs not in handoff_counts:
                    hs = "pending"
                handoff_counts[hs] += 1
                cursor_status = str(row.get("cursor_bridge_status") or "none").strip().lower()
                if cursor_status not in cursor_bridge_counts:
                    cursor_status = "none"
                cursor_bridge_counts[cursor_status] += 1
                xs = str(row.get("execution_status") or "pending").strip().lower()
                if xs not in execution_counts:
                    xs = "pending"
                execution_counts[xs] += 1
                eval_status = str(row.get("evaluation_status") or "pending").strip().lower()
                if eval_status not in evaluation_counts:
                    eval_status = "pending"
                evaluation_counts[eval_status] += 1
                local_analysis_status = str(row.get("local_analysis_status") or "pending").strip().lower()
                if local_analysis_status not in local_analysis_counts:
                    local_analysis_status = "pending"
                local_analysis_counts[local_analysis_status] += 1
                if str((row.get("failure_summary") or {}).get("failure_class") or "") == "duplicate_success_block":
                    duplicate_success_block_count += 1
                if str((row.get("recovery_summary") or {}).get("recovery_status") or "") == "retry_ready":
                    retry_ready_count_project += 1
                if str((row.get("recovery_summary") or {}).get("recovery_status") or "") == "repair_required":
                    repair_required_count_project += 1
                if str((row.get("rollback_repair") or {}).get("rollback_repair_status") or "") == "failed":
                    rollback_repair_failed_count += 1
                integrity_status = str((row.get("integrity_verification") or {}).get("integrity_status") or "")
                if integrity_status == "verified":
                    integrity_verified_count += 1
                if integrity_status in ("issues_detected", "verification_failed"):
                    integrity_issues_count += 1
                evaluation_summary = row.get("evaluation_summary") or {}
                execution_band = str(evaluation_summary.get("execution_quality_band") or "").strip().lower()
                if execution_band in execution_quality_band_count_total:
                    execution_quality_band_count_total[execution_band] += 1
                integrity_band = str(evaluation_summary.get("integrity_band") or "").strip().lower()
                if integrity_band in integrity_band_count_total:
                    integrity_band_count_total[integrity_band] += 1
                rollback_band = str(evaluation_summary.get("rollback_quality_band") or "").strip().lower()
                if rollback_band in rollback_quality_band_count_total:
                    rollback_quality_band_count_total[rollback_band] += 1
                risk_band = str(evaluation_summary.get("failure_risk_band") or "").strip().lower()
                if risk_band in failure_risk_band_count_total:
                    failure_risk_band_count_total[risk_band] += 1
                local_analysis_summary = row.get("local_analysis_summary") or {}
                confidence_band = str(local_analysis_summary.get("confidence_band") or "").strip().lower()
                if confidence_band in local_analysis_confidence_band_count_total:
                    local_analysis_confidence_band_count_total[confidence_band] += 1
                suggested_next_action = str(local_analysis_summary.get("suggested_next_action") or "").strip().lower()
                if suggested_next_action:
                    local_analysis_suggested_next_action_count_total[suggested_next_action] = (
                        local_analysis_suggested_next_action_count_total.get(suggested_next_action, 0) + 1
                    )
            execution_package_decision_counts_by_project[key] = decision_counts
            execution_package_eligibility_counts_by_project[key] = eligibility_counts
            execution_package_release_counts_by_project[key] = release_counts
            execution_package_handoff_counts_by_project[key] = handoff_counts
            execution_package_cursor_bridge_counts_by_project[key] = cursor_bridge_counts
            execution_package_execution_counts_by_project[key] = execution_counts
            execution_package_evaluation_counts_by_project[key] = evaluation_counts
            execution_package_local_analysis_counts_by_project[key] = local_analysis_counts
            execution_package_duplicate_success_block_count_by_project[key] = duplicate_success_block_count
            execution_package_retry_ready_count_by_project[key] = retry_ready_count_project
            execution_package_repair_required_count_by_project[key] = repair_required_count_project
            execution_package_rollback_repair_failed_count_by_project[key] = rollback_repair_failed_count
            execution_package_integrity_verified_count_by_project[key] = integrity_verified_count
            execution_package_integrity_issues_count_by_project[key] = integrity_issues_count
            latest_id = loaded.get("execution_package_id")
            latest_path = loaded.get("execution_package_path")
            latest_row = execution_package_rows[0] if execution_package_rows else {}
            if latest_row.get("decision_status"):
                latest_execution_package_decision_status_by_project[key] = str(latest_row.get("decision_status"))
            if latest_row.get("eligibility_status"):
                latest_execution_package_eligibility_status_by_project[key] = str(latest_row.get("eligibility_status"))
            if latest_row.get("release_status"):
                latest_execution_package_release_status_by_project[key] = str(latest_row.get("release_status"))
            if latest_row.get("handoff_status"):
                latest_execution_package_handoff_status_by_project[key] = str(latest_row.get("handoff_status"))
            if latest_row.get("handoff_executor_target_id"):
                latest_execution_package_handoff_target_by_project[key] = str(latest_row.get("handoff_executor_target_id"))
            if latest_row.get("cursor_bridge_status"):
                latest_execution_package_cursor_bridge_status_by_project[key] = str(latest_row.get("cursor_bridge_status"))
            if latest_row.get("bridge_task_id"):
                latest_execution_package_bridge_task_id_by_project[key] = str(latest_row.get("bridge_task_id"))
            execution_package_cursor_bridge_artifact_count_by_project[key] = sum(
                max(0, int(row.get("cursor_bridge_artifact_count") or 0)) for row in execution_package_rows
            )
            if latest_row.get("execution_status"):
                latest_execution_package_execution_status_by_project[key] = str(latest_row.get("execution_status"))
            if latest_row.get("execution_executor_target_id"):
                latest_execution_package_execution_target_by_project[key] = str(latest_row.get("execution_executor_target_id"))
            if latest_row.get("evaluation_status"):
                latest_execution_package_evaluation_status_by_project[key] = str(latest_row.get("evaluation_status"))
            if latest_row.get("local_analysis_status"):
                latest_execution_package_local_analysis_status_by_project[key] = str(latest_row.get("local_analysis_status"))
            if eligibility_counts.get("eligible", 0) > 0:
                execution_package_eligible_projects.append(key)
            if eligibility_counts.get("ineligible", 0) > 0:
                execution_package_ineligible_projects.append(key)
            if release_counts.get("released", 0) > 0:
                execution_package_released_projects.append(key)
            if release_counts.get("blocked", 0) > 0:
                execution_package_release_blocked_projects.append(key)
            if handoff_counts.get("authorized", 0) > 0:
                execution_package_handoff_authorized_projects.append(key)
            if handoff_counts.get("blocked", 0) > 0:
                execution_package_handoff_blocked_projects.append(key)
            if cursor_bridge_counts.get("prepared", 0) > 0:
                cursor_bridge_prepared_projects.append(key)
            if cursor_bridge_counts.get("artifact_recorded", 0) > 0:
                cursor_bridge_artifact_return_projects.append(key)
            if execution_counts.get("succeeded", 0) > 0:
                execution_package_execution_succeeded_projects.append(key)
            if execution_counts.get("failed", 0) > 0:
                execution_package_execution_failed_projects.append(key)
            if execution_counts.get("blocked", 0) > 0:
                execution_package_execution_blocked_projects.append(key)
            if execution_counts.get("rolled_back", 0) > 0:
                execution_package_execution_rolled_back_projects.append(key)
            if latest_id or latest_row.get("package_id"):
                latest_execution_package_id_by_project[key] = str(latest_id or latest_row.get("package_id") or "")
            if latest_path or latest_row.get("package_file"):
                latest_execution_package_path_by_project[key] = str(latest_path or latest_row.get("package_file") or "")
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
            rr = loaded.get("runtime_router_result") or {}
            runtime_sel = rr.get("selected_runtime") or "none"
            runtime_route_by_project[key] = str(runtime_sel)
            runtime_route_count[runtime_sel] = runtime_route_count.get(runtime_sel, 0) + 1
            mr = loaded.get("model_router_result") or {}
            model_sel = mr.get("selected_model") or "none"
            model_route_by_project[key] = str(model_sel)
            model_route_count[model_sel] = model_route_count.get(model_sel, 0) + 1
            dp = loaded.get("deployment_preflight_result") or {}
            dp_status = dp.get("deployment_preflight_status") or "none"
            deployment_preflight_count[dp_status] = deployment_preflight_count.get(dp_status, 0) + 1

            cgs = loaded.get("change_gate_status") or "none"
            change_gate_status_count[cgs] = change_gate_status_count.get(cgs, 0) + 1

            rs = loaded.get("regression_status") or "none"
            regression_status_count[rs] = regression_status_count.get(rs, 0) + 1

            # PRISM v1 (read-only persisted outputs).
            prism_status_val = loaded.get("prism_status") or (loaded.get("prism_result") or {}).get("prism_status") if isinstance(loaded.get("prism_result"), dict) else None
            prism_status_by_project[key] = str(prism_status_val or "none")
            prism_rec = (loaded.get("prism_result") or {}).get("recommendation") if isinstance(loaded.get("prism_result"), dict) else None
            if prism_rec in prism_recommendation_count:
                prism_recommendation_count[prism_rec] += 1
        except Exception:
            continue

    studio_coordination_summary = build_studio_coordination_summary_safe(states_by_project)
    studio_driver_summary = build_studio_driver_result_safe(
        studio_coordination_summary=studio_coordination_summary,
        states_by_project=states_by_project,
    )

    # Self-improvement backlog visibility signals (planning-only).
    try:
        from NEXUS.self_improvement_engine import build_self_improvement_backlog_safe, select_next_improvement_safe

        dashboard_stub = {
            "guardrail_status_count": guardrail_status_count,
        }
        backlog_items = build_self_improvement_backlog_safe(
            dashboard_summary=dashboard_stub,
            studio_coordination_summary=studio_coordination_summary,
            driver_summary=studio_driver_summary,
        )
        selected = select_next_improvement_safe(backlog_items=backlog_items)
        backlog_count = len(backlog_items)
        selected_item = next((i for i in backlog_items if i.get("item_id") == selected.get("selected_item_id")), {})  # type: ignore[arg-type]
        selected_improvement_summary = {
            "selected_item_id": selected.get("selected_item_id"),
            "selected_title": selected.get("selected_title"),
            "selected_category": selected.get("selected_category"),
            "selected_priority": selected_item.get("priority"),
        }
    except Exception:
        backlog_count = 0
        selected_improvement_summary = {}

    try:
        from NEXUS.execution_package_registry import list_self_change_audit_entries

        forge_root = str(Path(__file__).resolve().parent.parent)
        self_change_entries = list_self_change_audit_entries(forge_root, n=20)
    except Exception:
        self_change_entries = []

    self_change_risk_count_total: dict[str, int] = {"low_risk": 0, "medium_risk": 0, "high_risk": 0}
    self_change_outcome_count_total: dict[str, int] = {}
    self_change_approval_requirement_count_total: dict[str, int] = {"optional": 0, "recommended": 0, "mandatory": 0}
    self_change_gate_outcome_count_total: dict[str, int] = {}
    self_change_release_lane_count_total: dict[str, int] = {"stable": 0, "experimental": 0}
    self_change_validation_outcome_count_total: dict[str, int] = {}
    self_change_sandbox_required_count_total: dict[str, int] = {"required": 0, "not_required": 0}
    self_change_sandbox_status_count_total: dict[str, int] = {}
    self_change_sandbox_result_count_total: dict[str, int] = {}
    self_change_promotion_status_count_total: dict[str, int] = {}
    self_change_comparison_status_count_total: dict[str, int] = {}
    self_change_confidence_band_count_total: dict[str, int] = {}
    self_change_promotion_confidence_count_total: dict[str, int] = {}
    self_change_recommendation_count_total: dict[str, int] = {}
    self_change_monitoring_status_count_total: dict[str, int] = {}
    self_change_rollback_trigger_outcome_count_total: dict[str, int] = {}
    self_change_stable_status_count_total: dict[str, int] = {}
    self_change_rollback_scope_count_total: dict[str, int] = {}
    self_change_blast_radius_count_total: dict[str, int] = {"low": 0, "medium": 0, "high": 0}
    self_change_rollback_status_count_total: dict[str, int] = {}
    self_change_rollback_follow_up_validation_required_count_total: dict[str, int] = {"required": 0, "not_required": 0}
    self_change_mutation_rate_status_count_total: dict[str, int] = {}
    self_change_control_outcome_count_total: dict[str, int] = {}
    self_change_cool_down_required_count_total: dict[str, int] = {"required": 0, "not_required": 0}
    self_change_stability_state_count_total: dict[str, int] = {}
    self_change_turbulence_level_count_total: dict[str, int] = {}
    self_change_freeze_scope_count_total: dict[str, int] = {}
    self_change_recovery_only_mode_count_total: dict[str, int] = {"enabled": 0, "disabled": 0}
    self_change_escalation_required_count_total: dict[str, int] = {"required": 0, "not_required": 0}
    self_change_checkpoint_required_count_total: dict[str, int] = {"required": 0, "not_required": 0}
    self_change_checkpoint_scope_count_total: dict[str, int] = {}
    self_change_checkpoint_status_count_total: dict[str, int] = {}
    self_change_executive_approval_required_count_total: dict[str, int] = {"required": 0, "not_required": 0}
    self_change_manual_hold_active_count_total: dict[str, int] = {"active": 0, "inactive": 0}
    self_change_manual_hold_scope_count_total: dict[str, int] = {}
    self_change_override_status_count_total: dict[str, int] = {}
    self_change_rollout_stage_count_total: dict[str, int] = {}
    self_change_rollout_scope_count_total: dict[str, int] = {}
    self_change_rollout_status_count_total: dict[str, int] = {}
    self_change_cohort_type_count_total: dict[str, int] = {}
    self_change_stage_promotion_required_count_total: dict[str, int] = {"required": 0, "not_required": 0}
    self_change_broader_rollout_blocked_count_total: dict[str, int] = {"blocked": 0, "not_blocked": 0}
    self_change_trust_status_count_total: dict[str, int] = {}
    self_change_decay_state_count_total: dict[str, int] = {}
    self_change_revalidation_required_count_total: dict[str, int] = {"required": 0, "not_required": 0}
    self_change_trust_outcome_count_total: dict[str, int] = {}
    self_change_drift_detected_count_total: dict[str, int] = {"detected": 0, "not_detected": 0}
    self_change_strategic_intent_category_count_total: dict[str, int] = {}
    self_change_alignment_status_count_total: dict[str, int] = {}
    self_change_prohibited_goal_hit_count_total: dict[str, int] = {"hit": 0, "not_hit": 0}
    self_change_executive_priority_match_count_total: dict[str, int] = {"matched": 0, "not_matched": 0}
    self_change_mission_scope_count_total: dict[str, int] = {}
    self_change_strategic_outcome_count_total: dict[str, int] = {}
    self_change_roi_band_count_total: dict[str, int] = {
        "high_value": 0,
        "medium_value": 0,
        "low_value": 0,
        "negative_value": 0,
    }
    self_change_value_status_count_total: dict[str, int] = {}
    self_change_priority_value_count_total: dict[str, int] = {"low": 0, "medium": 0, "high": 0, "urgent": 0}
    self_change_recommended_action_count_total: dict[str, int] = {}
    self_change_value_outcome_count_total: dict[str, int] = {
        "worth_pursuing": 0,
        "defer_for_later": 0,
        "not_worth_it": 0,
        "executive_value_review_required": 0,
    }
    self_change_protected_zone_hits: dict[str, int] = {}
    self_change_pending_approval_count_total = 0
    self_change_success_count_total = 0
    self_change_failure_count_total = 0
    self_change_rollback_required_count_total = 0
    self_change_freeze_required_count_total = 0
    for entry in self_change_entries:
        risk_level = str(entry.get("risk_level") or "medium_risk")
        if risk_level in self_change_risk_count_total:
            self_change_risk_count_total[risk_level] += 1
        approval_requirement = str(entry.get("approval_requirement") or "")
        if approval_requirement in self_change_approval_requirement_count_total:
            self_change_approval_requirement_count_total[approval_requirement] += 1
        outcome_status = str(entry.get("outcome_status") or "proposed")
        self_change_outcome_count_total[outcome_status] = self_change_outcome_count_total.get(outcome_status, 0) + 1
        gate_outcome = str(entry.get("gate_outcome") or "allow_for_review")
        self_change_gate_outcome_count_total[gate_outcome] = self_change_gate_outcome_count_total.get(gate_outcome, 0) + 1
        release_lane = str(entry.get("release_lane") or "")
        if release_lane in self_change_release_lane_count_total:
            self_change_release_lane_count_total[release_lane] += 1
        validation_outcome = str(entry.get("validation_status") or "pending")
        self_change_validation_outcome_count_total[validation_outcome] = self_change_validation_outcome_count_total.get(validation_outcome, 0) + 1
        sandbox_requirement_key = "required" if bool(entry.get("sandbox_required")) else "not_required"
        self_change_sandbox_required_count_total[sandbox_requirement_key] = (
            self_change_sandbox_required_count_total.get(sandbox_requirement_key, 0) + 1
        )
        sandbox_status = str(entry.get("sandbox_status") or "sandbox_pending")
        self_change_sandbox_status_count_total[sandbox_status] = self_change_sandbox_status_count_total.get(sandbox_status, 0) + 1
        sandbox_result = str(entry.get("sandbox_result") or sandbox_status)
        self_change_sandbox_result_count_total[sandbox_result] = self_change_sandbox_result_count_total.get(sandbox_result, 0) + 1
        promotion_status = str(entry.get("promotion_status") or "promotion_pending")
        self_change_promotion_status_count_total[promotion_status] = (
            self_change_promotion_status_count_total.get(promotion_status, 0) + 1
        )
        comparison_status = str(entry.get("comparison_status") or "insufficient_evidence")
        self_change_comparison_status_count_total[comparison_status] = (
            self_change_comparison_status_count_total.get(comparison_status, 0) + 1
        )
        confidence_band = str(entry.get("confidence_band") or "weak")
        self_change_confidence_band_count_total[confidence_band] = (
            self_change_confidence_band_count_total.get(confidence_band, 0) + 1
        )
        promotion_confidence = str(entry.get("promotion_confidence") or "insufficient_evidence")
        self_change_promotion_confidence_count_total[promotion_confidence] = (
            self_change_promotion_confidence_count_total.get(promotion_confidence, 0) + 1
        )
        recommendation = str(entry.get("recommendation") or "hold_experimental")
        self_change_recommendation_count_total[recommendation] = (
            self_change_recommendation_count_total.get(recommendation, 0) + 1
        )
        monitoring_status = str(entry.get("monitoring_status") or "pending_monitoring")
        self_change_monitoring_status_count_total[monitoring_status] = (
            self_change_monitoring_status_count_total.get(monitoring_status, 0) + 1
        )
        rollback_trigger_outcome = str(entry.get("rollback_trigger_outcome") or "monitor_more")
        self_change_rollback_trigger_outcome_count_total[rollback_trigger_outcome] = (
            self_change_rollback_trigger_outcome_count_total.get(rollback_trigger_outcome, 0) + 1
        )
        stable_status = str(entry.get("stable_status") or "provisionally_stable")
        self_change_stable_status_count_total[stable_status] = (
            self_change_stable_status_count_total.get(stable_status, 0) + 1
        )
        rollback_scope = str(entry.get("rollback_scope") or "file_only")
        self_change_rollback_scope_count_total[rollback_scope] = (
            self_change_rollback_scope_count_total.get(rollback_scope, 0) + 1
        )
        blast_radius_level = str(entry.get("blast_radius_level") or "low")
        if blast_radius_level in self_change_blast_radius_count_total:
            self_change_blast_radius_count_total[blast_radius_level] += 1
        rollback_status = str(entry.get("rollback_status") or "rollback_pending")
        self_change_rollback_status_count_total[rollback_status] = (
            self_change_rollback_status_count_total.get(rollback_status, 0) + 1
        )
        rollback_follow_up_key = "required" if bool(entry.get("rollback_follow_up_validation_required")) else "not_required"
        self_change_rollback_follow_up_validation_required_count_total[rollback_follow_up_key] = (
            self_change_rollback_follow_up_validation_required_count_total.get(rollback_follow_up_key, 0) + 1
        )
        mutation_rate_status = str(entry.get("mutation_rate_status") or "within_budget")
        self_change_mutation_rate_status_count_total[mutation_rate_status] = (
            self_change_mutation_rate_status_count_total.get(mutation_rate_status, 0) + 1
        )
        control_outcome = str(entry.get("control_outcome") or "budget_available")
        self_change_control_outcome_count_total[control_outcome] = (
            self_change_control_outcome_count_total.get(control_outcome, 0) + 1
        )
        cool_down_key = "required" if bool(entry.get("cool_down_required")) else "not_required"
        self_change_cool_down_required_count_total[cool_down_key] = (
            self_change_cool_down_required_count_total.get(cool_down_key, 0) + 1
        )
        stability_state = str(entry.get("stability_state") or "stable")
        self_change_stability_state_count_total[stability_state] = (
            self_change_stability_state_count_total.get(stability_state, 0) + 1
        )
        turbulence_level = str(entry.get("turbulence_level") or "low")
        self_change_turbulence_level_count_total[turbulence_level] = (
            self_change_turbulence_level_count_total.get(turbulence_level, 0) + 1
        )
        freeze_scope = str(entry.get("freeze_scope") or "project_scoped")
        self_change_freeze_scope_count_total[freeze_scope] = (
            self_change_freeze_scope_count_total.get(freeze_scope, 0) + 1
        )
        recovery_only_key = "enabled" if bool(entry.get("recovery_only_mode")) else "disabled"
        self_change_recovery_only_mode_count_total[recovery_only_key] = (
            self_change_recovery_only_mode_count_total.get(recovery_only_key, 0) + 1
        )
        escalation_key = "required" if bool(entry.get("escalation_required")) else "not_required"
        self_change_escalation_required_count_total[escalation_key] = (
            self_change_escalation_required_count_total.get(escalation_key, 0) + 1
        )
        checkpoint_required_key = "required" if bool(entry.get("checkpoint_required")) else "not_required"
        self_change_checkpoint_required_count_total[checkpoint_required_key] = (
            self_change_checkpoint_required_count_total.get(checkpoint_required_key, 0) + 1
        )
        checkpoint_scope = str(entry.get("checkpoint_scope") or "project_scoped")
        self_change_checkpoint_scope_count_total[checkpoint_scope] = (
            self_change_checkpoint_scope_count_total.get(checkpoint_scope, 0) + 1
        )
        checkpoint_status = str(entry.get("checkpoint_status") or "not_required")
        self_change_checkpoint_status_count_total[checkpoint_status] = (
            self_change_checkpoint_status_count_total.get(checkpoint_status, 0) + 1
        )
        executive_key = "required" if bool(entry.get("executive_approval_required")) else "not_required"
        self_change_executive_approval_required_count_total[executive_key] = (
            self_change_executive_approval_required_count_total.get(executive_key, 0) + 1
        )
        hold_active_key = "active" if bool(entry.get("manual_hold_active")) else "inactive"
        self_change_manual_hold_active_count_total[hold_active_key] = (
            self_change_manual_hold_active_count_total.get(hold_active_key, 0) + 1
        )
        hold_scope = str(entry.get("manual_hold_scope") or "project_scoped")
        self_change_manual_hold_scope_count_total[hold_scope] = (
            self_change_manual_hold_scope_count_total.get(hold_scope, 0) + 1
        )
        override_status = str(entry.get("override_status") or "no_override")
        self_change_override_status_count_total[override_status] = (
            self_change_override_status_count_total.get(override_status, 0) + 1
        )
        rollout_stage = str(entry.get("rollout_stage") or "limited_cohort")
        self_change_rollout_stage_count_total[rollout_stage] = (
            self_change_rollout_stage_count_total.get(rollout_stage, 0) + 1
        )
        rollout_scope = str(entry.get("rollout_scope") or "")
        self_change_rollout_scope_count_total[rollout_scope] = (
            self_change_rollout_scope_count_total.get(rollout_scope, 0) + 1
        )
        rollout_status = str(entry.get("rollout_status") or "rollout_pending")
        self_change_rollout_status_count_total[rollout_status] = (
            self_change_rollout_status_count_total.get(rollout_status, 0) + 1
        )
        cohort_type = str(entry.get("cohort_type") or "low_risk_subset")
        self_change_cohort_type_count_total[cohort_type] = (
            self_change_cohort_type_count_total.get(cohort_type, 0) + 1
        )
        stage_promotion_key = "required" if bool(entry.get("stage_promotion_required")) else "not_required"
        self_change_stage_promotion_required_count_total[stage_promotion_key] = (
            self_change_stage_promotion_required_count_total.get(stage_promotion_key, 0) + 1
        )
        broader_rollout_key = "blocked" if bool(entry.get("broader_rollout_blocked")) else "not_blocked"
        self_change_broader_rollout_blocked_count_total[broader_rollout_key] = (
            self_change_broader_rollout_blocked_count_total.get(broader_rollout_key, 0) + 1
        )
        trust_status = str(entry.get("trust_status") or "trusted_current")
        self_change_trust_status_count_total[trust_status] = (
            self_change_trust_status_count_total.get(trust_status, 0) + 1
        )
        decay_state = str(entry.get("decay_state") or "fresh")
        self_change_decay_state_count_total[decay_state] = (
            self_change_decay_state_count_total.get(decay_state, 0) + 1
        )
        revalidation_key = "required" if bool(entry.get("revalidation_required")) else "not_required"
        self_change_revalidation_required_count_total[revalidation_key] = (
            self_change_revalidation_required_count_total.get(revalidation_key, 0) + 1
        )
        trust_outcome = str(entry.get("trust_outcome") or "trust_retained")
        self_change_trust_outcome_count_total[trust_outcome] = (
            self_change_trust_outcome_count_total.get(trust_outcome, 0) + 1
        )
        drift_key = "detected" if bool(entry.get("drift_detected")) else "not_detected"
        self_change_drift_detected_count_total[drift_key] = (
            self_change_drift_detected_count_total.get(drift_key, 0) + 1
        )
        strategic_intent_category = str(entry.get("strategic_intent_category") or "mission_out_of_scope")
        self_change_strategic_intent_category_count_total[strategic_intent_category] = (
            self_change_strategic_intent_category_count_total.get(strategic_intent_category, 0) + 1
        )
        alignment_status = str(entry.get("alignment_status") or "aligned_low_priority")
        self_change_alignment_status_count_total[alignment_status] = (
            self_change_alignment_status_count_total.get(alignment_status, 0) + 1
        )
        prohibited_key = "hit" if bool(entry.get("prohibited_goal_hit")) else "not_hit"
        self_change_prohibited_goal_hit_count_total[prohibited_key] = (
            self_change_prohibited_goal_hit_count_total.get(prohibited_key, 0) + 1
        )
        priority_key = "matched" if bool(entry.get("executive_priority_match")) else "not_matched"
        self_change_executive_priority_match_count_total[priority_key] = (
            self_change_executive_priority_match_count_total.get(priority_key, 0) + 1
        )
        mission_scope = str(entry.get("mission_scope") or "core_mission")
        self_change_mission_scope_count_total[mission_scope] = (
            self_change_mission_scope_count_total.get(mission_scope, 0) + 1
        )
        strategic_outcome = str(entry.get("strategic_outcome") or "aligned_but_low_priority")
        self_change_strategic_outcome_count_total[strategic_outcome] = (
            self_change_strategic_outcome_count_total.get(strategic_outcome, 0) + 1
        )
        roi_band = str(entry.get("roi_band") or "medium_value")
        if roi_band in self_change_roi_band_count_total:
            self_change_roi_band_count_total[roi_band] += 1
        else:
            self_change_roi_band_count_total[roi_band] = self_change_roi_band_count_total.get(roi_band, 0) + 1
        value_status = str(entry.get("value_status") or "")
        if value_status:
            self_change_value_status_count_total[value_status] = (
                self_change_value_status_count_total.get(value_status, 0) + 1
            )
        priority_value = str(entry.get("priority_value") or "medium")
        if priority_value in self_change_priority_value_count_total:
            self_change_priority_value_count_total[priority_value] += 1
        else:
            self_change_priority_value_count_total[priority_value] = (
                self_change_priority_value_count_total.get(priority_value, 0) + 1
            )
        recommended_action = str(entry.get("recommended_action") or "")
        if recommended_action:
            self_change_recommended_action_count_total[recommended_action] = (
                self_change_recommended_action_count_total.get(recommended_action, 0) + 1
            )
        value_outcome = str(entry.get("value_outcome") or entry.get("status") or "")
        if value_outcome in self_change_value_outcome_count_total:
            self_change_value_outcome_count_total[value_outcome] += 1
        if str(entry.get("approval_status") or "") in ("required", "pending", "awaiting_approval"):
            self_change_pending_approval_count_total += 1
        if bool(entry.get("success")):
            self_change_success_count_total += 1
        elif outcome_status in ("failed", "reverted", "blocked", "error"):
            self_change_failure_count_total += 1
        if bool(entry.get("rollback_required")):
            self_change_rollback_required_count_total += 1
        if bool(entry.get("freeze_required")):
            self_change_freeze_required_count_total += 1
        for zone in entry.get("protected_zones") or []:
            zone_name = str(zone or "").strip()
            if zone_name:
                self_change_protected_zone_hits[zone_name] = self_change_protected_zone_hits.get(zone_name, 0) + 1

    # Overall regression status
    if regression_status_count.get("blocked"):
        regression_status = "blocked"
    elif regression_status_count.get("error_fallback"):
        regression_status = "error_fallback"
    elif regression_status_count.get("warning"):
        regression_status = "warning"
    elif regression_status_count and any(k in regression_status_count for k in ("passed",)):
        regression_status = "passed"
    else:
        regression_status = "none"

    prism_go_count = prism_recommendation_count.get("go", 0)
    prism_revise_count = prism_recommendation_count.get("revise", 0)
    prism_hold_count = prism_recommendation_count.get("hold", 0)

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

    # Forge OS layer (Sprint 5): lightweight, summary-only operational fields.
    try:
        from portfolio_manager import build_portfolio_summary_safe
        from runtime_infrastructure import build_runtime_infrastructure_summary_safe
        from NEXUS.execution_environment_summary import build_execution_environment_summary_safe
        from NEXUS.approval_summary import build_approval_summary_safe
        from NEXUS.product_summary import build_product_summary_safe
        from NEXUS.autonomy_summary import build_autonomy_summary_safe
        from NEXUS.helix_summary import build_helix_summary_safe
        from NEXUS.patch_proposal_summary import build_patch_proposal_summary_safe
        from meta_engines.safety_engine import evaluate_safety_engine
        from meta_engines.security_engine import evaluate_security_engine
        from meta_engines.compliance_engine import evaluate_compliance_engine
        from meta_engines.risk_engine import evaluate_risk_engine
        from meta_engines.policy_engine import evaluate_policy_engine
        from meta_engines.cost_engine import evaluate_cost_engine
        from meta_engines.audit_engine import evaluate_audit_engine
        from elite_layers.titan import build_titan_summary_safe
        from elite_layers.leviathan import build_leviathan_summary_safe
        from elite_layers.helios import build_helios_summary_safe
        from elite_layers.veritas import build_veritas_summary_safe
        from elite_layers.sentinel import build_sentinel_summary_safe

        portfolio_summary = build_portfolio_summary_safe(
            states_by_project=states_by_project,
            studio_coordination_summary=studio_coordination_summary,
            studio_driver_summary=studio_driver_summary,
        )
        runtime_infrastructure_summary = build_runtime_infrastructure_summary_safe()
        execution_environment_summary = build_execution_environment_summary_safe(
            runtime_target_summary=get_runtime_target_summary(),
        )
        approval_summary = build_approval_summary_safe(n_recent=20, n_tail=100)
        product_summary = build_product_summary_safe(use_cached=True)
        autonomy_summary = build_autonomy_summary_safe(
            n_recent=10,
            execution_environment_summary=execution_environment_summary,
        )
        helix_summary = build_helix_summary_safe(n_recent=10)
        patch_proposal_summary = build_patch_proposal_summary_safe(n_recent=20, n_tail=100)

        meta_engine_summary = {
            "safety_engine": evaluate_safety_engine(
                states_by_project=states_by_project,
                studio_coordination_summary=studio_coordination_summary,
                studio_driver_summary=studio_driver_summary,
                runtime_infrastructure_summary=runtime_infrastructure_summary,
            ),
            "security_engine": evaluate_security_engine(
                states_by_project=states_by_project,
                studio_coordination_summary=studio_coordination_summary,
                studio_driver_summary=studio_driver_summary,
                runtime_infrastructure_summary=runtime_infrastructure_summary,
            ),
            "compliance_engine": evaluate_compliance_engine(
                states_by_project=states_by_project,
                studio_coordination_summary=studio_coordination_summary,
                studio_driver_summary=studio_driver_summary,
                runtime_infrastructure_summary=runtime_infrastructure_summary,
            ),
            "risk_engine": evaluate_risk_engine(
                states_by_project=states_by_project,
                studio_coordination_summary=studio_coordination_summary,
                studio_driver_summary=studio_driver_summary,
                runtime_infrastructure_summary=runtime_infrastructure_summary,
            ),
            "policy_engine": evaluate_policy_engine(
                states_by_project=states_by_project,
                studio_coordination_summary=studio_coordination_summary,
                studio_driver_summary=studio_driver_summary,
                runtime_infrastructure_summary=runtime_infrastructure_summary,
            ),
            "cost_engine": evaluate_cost_engine(
                states_by_project=states_by_project,
                studio_coordination_summary=studio_coordination_summary,
                studio_driver_summary=studio_driver_summary,
                runtime_infrastructure_summary=runtime_infrastructure_summary,
            ),
            "audit_engine": evaluate_audit_engine(
                states_by_project=states_by_project,
                studio_coordination_summary=studio_coordination_summary,
                studio_driver_summary=studio_driver_summary,
                runtime_infrastructure_summary=runtime_infrastructure_summary,
            ),
        }

        meta_engine_review_required_count = sum(
            1 for v in meta_engine_summary.values()
            if isinstance(v, dict) and bool(v.get("review_required", False))
        )

        # Elite capability layers (Phase 6): identity/visibility wrappers.
        # Keep dashboard snapshot low-cost: for HELIOS we do not run live regression checks.
        titan_summary = build_titan_summary_safe(
            states_by_project=states_by_project,
            studio_coordination_summary=studio_coordination_summary,
            studio_driver_summary=studio_driver_summary,
        )
        leviathan_summary = build_leviathan_summary_safe(
            states_by_project=states_by_project,
            studio_coordination_summary=studio_coordination_summary,
            studio_driver_summary=studio_driver_summary,
            portfolio_summary=portfolio_summary,
        )
        veritas_summary = build_veritas_summary_safe(
            states_by_project=states_by_project,
            studio_coordination_summary=studio_coordination_summary,
            studio_driver_summary=studio_driver_summary,
            meta_engine_summary=meta_engine_summary,
        )
        sentinel_summary = build_sentinel_summary_safe(
            states_by_project=states_by_project,
            studio_coordination_summary=studio_coordination_summary,
            meta_engine_summary=meta_engine_summary,
        )
        try:
            from NEXUS.memory_layer import build_memory_layer_summary_safe
            from NEXUS.meta_engine_governance import resolve_meta_engine_governance_safe

            memory_layer_summary = build_memory_layer_summary_safe()
            meta_engine_governance = resolve_meta_engine_governance_safe(
                titan_summary=titan_summary,
                leviathan_summary=leviathan_summary,
                helios_summary=helios_summary if "helios_summary" in locals() else {},
                veritas_summary=veritas_summary,
                sentinel_summary=sentinel_summary,
            )
        except Exception:
            memory_layer_summary = {
                "memory_layer_version": "2.0",
                "last_updated": "",
                "self_modification_policy": "approval_required",
                "advisory_only": True,
                "total_records": 0,
                "patterns_by_key": {},
                "records_by_project": {},
                "records_by_source": {},
                "records_by_scope": {"project": 0, "cross_project": 0},
                "records_by_category": {},
                "audit_event_count": 0,
                "denied_write_count": 0,
                "denied_read_count": 0,
                "recent_audit_events": [],
            }
            meta_engine_governance = {
                "status": "resolved",
                "conflict_type": "none",
                "involved_engines": [],
                "winning_priority": "",
                "resolution_basis": "fallback",
                "resolution_state": "resolved",
                "routing_outcome": "continue",
                "reason": "",
                "governance_trace": {},
            }

        # Phase 12: pass cross-intelligence context into HELIOS (cached mode).
        # Do not run GENESIS/HELIOS as executors; this only improves proposal explainability.
        try:
            priority_project = (studio_coordination_summary.get("priority_project") or "").strip()
            priority_state = states_by_project.get(priority_project) if priority_project else {}
            prism_result = (priority_state.get("prism_result") or {}) if isinstance(priority_state, dict) else {}
            last_aegis_decision = (priority_state.get("last_aegis_decision") or None) if isinstance(priority_state, dict) else None
        except Exception:
            prism_result = {}
            last_aegis_decision = None

        helios_summary = build_helios_summary_safe(
            dashboard_summary={
                "guardrail_status_count": guardrail_status_count,
                "veritas_summary": veritas_summary,
                "sentinel_summary": sentinel_summary,
                "prism_result": prism_result,
                "last_aegis_decision": last_aegis_decision,
                "memory_layer_summary": memory_layer_summary,
            },
            studio_coordination_summary=studio_coordination_summary,
            studio_driver_summary=studio_driver_summary,
            project_name=(portfolio_summary.get("priority_project") or "jarvis") if isinstance(portfolio_summary, dict) else "jarvis",
            live_regression=False,
            helios_evaluation_mode="dashboard_cached",
        )
        try:
            from NEXUS.meta_engine_governance import resolve_meta_engine_governance_safe

            meta_engine_governance = resolve_meta_engine_governance_safe(
                titan_summary=titan_summary,
                leviathan_summary=leviathan_summary,
                helios_summary=helios_summary,
                veritas_summary=veritas_summary,
                sentinel_summary=sentinel_summary,
            )
        except Exception:
            pass

        # Phase 11/12: compact HELIOS proposal visibility.
        try:
            cp = helios_summary.get("change_proposal") if isinstance(helios_summary, dict) else {}
            helios_proposal_summary = {
                "proposal_id": (cp or {}).get("proposal_id"),
                "target_area": (cp or {}).get("target_area"),
                "change_type": (cp or {}).get("change_type"),
                "scope_level": (cp or {}).get("scope_level"),
                "risk_level": (cp or {}).get("risk_level"),
                "requires_review": bool((cp or {}).get("requires_review", True)),
                "requires_regression_check": bool((cp or {}).get("requires_regression_check", True)),
                "recommended_path": (cp or {}).get("recommended_path"),
                "helios_evaluation_mode": (helios_summary or {}).get("helios_evaluation_mode") if isinstance(helios_summary, dict) else None,
            }
        except Exception:
            helios_proposal_summary = {"proposal_id": None}

        # Phase 12: lightweight bounded studio loop summary (selection-only).
        try:
            from studio_loop import run_studio_loop_tick_safe

            studio_loop_summary = run_studio_loop_tick_safe(
                dashboard_summary={
                    "studio_coordination_summary": studio_coordination_summary,
                    "studio_driver_summary": studio_driver_summary,
                    "portfolio_summary": portfolio_summary,
                    "helios_summary": helios_summary,
                }
            )
        except Exception:
            studio_loop_summary = {
                "studio_loop_status": "error_fallback",
                "selected_path": "idle",
                "selected_project": None,
                "loop_reason": "studio_loop_tick summary unavailable",
                "execution_started": False,
                "bounded_execution": True,
                "executed_command": None,
                "executed_result_summary": None,
                "stop_reason": "Safe fallback; no execution performed.",
            }

        # GENESIS (Phase 10): lightweight dashboard visibility.
        # Do not run GENESIS here; just expose the latest persisted signals.
        try:
            priority_project = (studio_coordination_summary.get("priority_project") or "").strip()
            priority_state = states_by_project.get(priority_project) if priority_project else {}
            prism_rec = (priority_state.get("prism_result") or {}) if isinstance(priority_state, dict) else {}
            last_aegis = (priority_state.get("last_aegis_decision") or {}) if isinstance(priority_state, dict) else {}

            genesis_summary = {
                "genesis_status": "idle",
                "signals": {
                    "prism_recommendation": prism_rec.get("recommendation"),
                    "aegis_decision": last_aegis.get("aegis_decision"),
                    "veritas_status": veritas_summary.get("veritas_status") if isinstance(veritas_summary, dict) else None,
                    "sentinel_status": sentinel_summary.get("sentinel_status") if isinstance(sentinel_summary, dict) else None,
                },
            }

            # Phase 13: AEGIS / ForgeShell / tool gateway lightweight summaries.
            priority_path = (PROJECTS.get(priority_project) or {}).get("path") if priority_project else None
            try:
                from AEGIS.aegis_contract import normalize_aegis_result
                aegis_normalized = normalize_aegis_result(last_aegis) if isinstance(last_aegis, dict) else normalize_aegis_result(None)
                aegis_summary = {k: aegis_normalized.get(k) for k in ("aegis_decision", "aegis_scope", "action_mode", "approval_required", "approval_signal_only", "workspace_valid", "file_guard_status")}
            except Exception:
                aegis_summary = {"aegis_decision": None, "aegis_scope": None, "action_mode": None, "approval_required": False}
            try:
                # Truthfulness fix (Phase 14): do NOT run live ForgeShell tests in dashboard generation.
                from AEGIS.forgeshell import get_forgeshell_status_cached_safe
                fs_res = get_forgeshell_status_cached_safe(project_path=priority_path)
                forgeshell_summary = {
                    "forgeshell_status": fs_res.get("forgeshell_status"),
                    "exit_code": fs_res.get("exit_code"),
                    "timeout_hit": bool(fs_res.get("timeout_hit")),
                    "forgeshell_security_level": fs_res.get("forgeshell_security_level"),
                    "summary_reason": fs_res.get("summary_reason"),
                }
            except Exception:
                forgeshell_summary = {
                    "forgeshell_status": "idle",
                    "exit_code": None,
                    "timeout_hit": False,
                    "forgeshell_security_level": "allowlisted_wrapper",
                    "summary_reason": "ForgeShell status unavailable.",
                }
            try:
                from AEGIS.tool_gateway import route_tool_request_safe
                tg_res = route_tool_request_safe(tool_family="evaluation", project_path=priority_path, action_mode="evaluation")
                tool_gateway_summary = {
                    "tool_gateway_status": tg_res.get("tool_gateway_status"),
                    "tool_family": tg_res.get("tool_family"),
                    "policy_decision": tg_res.get("policy_decision"),
                }
            except Exception:
                tool_gateway_summary = {"tool_gateway_status": "idle", "tool_family": None, "policy_decision": None}
        except Exception:
            genesis_summary = {"genesis_status": "error_fallback", "signals": {}}
    except Exception:
        portfolio_summary = {
            "portfolio_status": "error_fallback",
            "total_projects": 0,
            "active_projects": 0,
            "blocked_projects": 0,
            "priority_project": None,
            "portfolio_reason": "Forge portfolio summary failed.",
        }
        runtime_infrastructure_summary = {
            "runtime_infrastructure_status": "error_fallback",
            "available_runtimes": [],
            "future_runtimes": [],
            "reason": "Forge runtime infrastructure summary failed.",
        }
        execution_environment_summary = {
            "execution_environment_status": "error_fallback",
            "active_environments": [],
            "planned_environments": [],
            "runtime_target_mapping": [],
            "environments": [],
            "per_project_summaries": {},
            "reason": "Execution environment summary failed.",
            "runtime_isolation_posture": {
                "isolation_posture": "error_fallback",
                "file_scope_status": "unknown",
                "network_scope_status": "unknown",
                "secret_scope_status": "unknown",
                "connector_scope_status": "unknown",
                "mutation_scope_status": "unknown",
                "rollback_posture": "unknown",
                "isolation_reason": "Execution environment summary failed.",
                "runtime_restrictions": [],
                "allowed_execution_domains": [],
                "blocked_execution_domains": [],
                "destructive_risk_posture": "unknown",
                "generated_at": datetime.now().isoformat(),
            },
        }
        approval_summary = {
            "approval_status": "error_fallback",
            "pending_count_total": 0,
            "pending_by_project": {},
            "recent_approvals": [],
            "approval_types": [],
            "stale_count": 0,
            "approved_pending_apply_count": 0,
            "reason": "Approval summary failed.",
        }
        product_summary = {
            "product_status": "error_fallback",
            "draft_count": 0,
            "ready_count": 0,
            "restricted_count": 0,
            "total_count": 0,
            "products_by_project": {},
            "safety_indicators": {"safety_issues": [], "restricted_count": 0},
            "learning_linkage_present": False,
            "approval_linkage_present": False,
            "autonomy_linkage_present": False,
            "patch_linkage_present": False,
            "helix_linkage_present": False,
            "reason": "Product summary failed.",
        }
        autonomy_summary = {
            "autonomy_posture": "error_fallback",
            "last_autonomy_run": None,
            "last_stop_reason": "",
            "autonomy_capable": False,
            "approval_blocked": False,
            "recent_runs": [],
            "per_project": {},
            "execution_environment_posture": {
                "execution_environment_status": "error_fallback",
                "active_environments": [],
                "planned_environments": [],
                "reason": "",
            },
            "reason": "Autonomy summary failed.",
        }
        helix_summary = {
            "helix_posture": "error_fallback",
            "last_helix_run": None,
            "last_stop_reason": "",
            "approval_blocked": False,
            "safety_blocked": False,
            "requires_surgeon": False,
            "stage_distribution": {},
            "surgeon_invocation_frequency": 0.0,
            "approval_blocked_frequency": 0.0,
            "autonomy_linkage_presence": 0.0,
            "multi_approach_success_rate": 0.0,
            "repair_artifact_quality": {"repair_with_patch_count": 0, "repair_without_patch_count": 0, "repair_total": 0},
            "recent_runs": [],
            "per_project": {},
            "reason": "HELIX summary failed.",
        }
        patch_proposal_summary = {
            "patch_proposal_status": "error_fallback",
            "pending_count": 0,
            "proposed_count": 0,
            "approval_required_count": 0,
            "approved_pending_apply_count": 0,
            "approved_pending_apply_stale_count": 0,
            "rejected_count": 0,
            "blocked_count": 0,
            "applied_count": 0,
            "approval_blocked_count": 0,
            "status_counts": {},
            "by_project": {},
            "recent_proposals": [],
            "by_risk_level": {},
            "reason": "Patch proposal summary failed.",
        }
        meta_engine_summary = {}
        meta_engine_review_required_count = 0
        titan_summary = {
            "titan_status": "error_fallback",
            "execution_mode": "idle",
            "next_execution_action": "idle",
            "execution_reason": "TITAN summary failed.",
            "run_permitted": False,
        }
        leviathan_summary = {
            "leviathan_status": "error_fallback",
            "highest_leverage_project": None,
            "highest_leverage_reason": "LEVIATHAN summary failed.",
            "recommended_focus": "Review required.",
            "defer_projects": [],
        }
        helios_summary = {
            "helios_status": "error_fallback",
            "selected_improvement": None,
            "improvement_category": None,
            "improvement_reason": "HELIOS summary failed.",
            "execution_gated": True,
        }
        helios_proposal_summary = {"proposal_id": None, "target_area": None}
        veritas_summary = {
            "veritas_status": "error_fallback",
            "truth_reason": "VERITAS summary failed.",
            "contradictions_detected": False,
            "assumption_review_required": True,
            "truth_confidence": "low",
            "issues": [],
            "source_signals": {
                "state_validator": None,
                "guardrails": None,
                "prism_recommendation": None,
                "aegis_decision": None,
            },
        }
        sentinel_summary = {
            "sentinel_status": "error_fallback",
            "threat_reason": "SENTINEL summary failed.",
            "high_risk_detected": False,
            "review_required": True,
            "risk_level": "unknown",
            "active_warnings": [],
            "source_signals": {
                "safety_engine": None,
                "security_engine": None,
                "compliance_engine": None,
                "risk_engine": None,
                "aegis_decision": None,
                "deployment_preflight": None,
            },
        }
        memory_layer_summary = {
            "memory_layer_version": "2.0",
            "last_updated": "",
            "self_modification_policy": "approval_required",
            "advisory_only": True,
            "total_records": 0,
            "patterns_by_key": {},
            "records_by_project": {},
            "records_by_source": {},
            "records_by_scope": {"project": 0, "cross_project": 0},
            "records_by_category": {},
            "audit_event_count": 0,
            "denied_write_count": 0,
            "denied_read_count": 0,
            "recent_audit_events": [],
        }
        meta_engine_governance = {
            "status": "resolved",
            "conflict_type": "none",
            "involved_engines": [],
            "winning_priority": "",
            "resolution_basis": "fallback",
            "resolution_state": "resolved",
            "routing_outcome": "continue",
            "reason": "",
            "governance_trace": {},
        }

        genesis_summary = {"genesis_status": "error_fallback", "signals": {}}
        aegis_summary = {"aegis_decision": None, "aegis_scope": None, "action_mode": None, "approval_required": False}
        forgeshell_summary = {
            "forgeshell_status": "idle",
            "exit_code": None,
            "timeout_hit": False,
            "forgeshell_security_level": "allowlisted_wrapper",
            "summary_reason": "ForgeShell idle (dashboard cache not available).",
        }
        tool_gateway_summary = {"tool_gateway_status": "idle", "tool_family": None, "policy_decision": None}
        studio_loop_summary = {
            "studio_loop_status": "error_fallback",
            "selected_path": "idle",
            "selected_project": None,
            "loop_reason": "studio_loop_tick summary unavailable",
            "execution_started": False,
            "bounded_execution": True,
            "executed_command": None,
            "executed_result_summary": None,
            "stop_reason": "Safe fallback; no execution performed.",
        }
        prism_result = {}
        last_aegis_decision = None

    pending_count_total = sum(execution_package_pending_by_project.values())
    if pending_count_total > 0:
        execution_package_review_reason = f"{pending_count_total} execution package(s) pending human review."
        execution_package_review_status = "ok"
    else:
        execution_package_review_reason = "No pending execution packages."
        execution_package_review_status = "ok"
    approved_decision_count_total = sum(v.get("approved", 0) for v in execution_package_decision_counts_by_project.values())
    rejected_decision_count_total = sum(v.get("rejected", 0) for v in execution_package_decision_counts_by_project.values())
    pending_decision_count_total = sum(v.get("pending", 0) for v in execution_package_decision_counts_by_project.values())
    eligible_count_total = sum(v.get("eligible", 0) for v in execution_package_eligibility_counts_by_project.values())
    ineligible_count_total = sum(v.get("ineligible", 0) for v in execution_package_eligibility_counts_by_project.values())
    pending_eligibility_count_total = sum(v.get("pending", 0) for v in execution_package_eligibility_counts_by_project.values())
    released_count_total = sum(v.get("released", 0) for v in execution_package_release_counts_by_project.values())
    blocked_release_count_total = sum(v.get("blocked", 0) for v in execution_package_release_counts_by_project.values())
    pending_release_count_total = sum(v.get("pending", 0) for v in execution_package_release_counts_by_project.values())
    authorized_handoff_count_total = sum(v.get("authorized", 0) for v in execution_package_handoff_counts_by_project.values())
    blocked_handoff_count_total = sum(v.get("blocked", 0) for v in execution_package_handoff_counts_by_project.values())
    pending_handoff_count_total = sum(v.get("pending", 0) for v in execution_package_handoff_counts_by_project.values())
    prepared_cursor_bridge_count_total = sum(v.get("prepared", 0) for v in execution_package_cursor_bridge_counts_by_project.values())
    artifact_recorded_cursor_bridge_count_total = sum(v.get("artifact_recorded", 0) for v in execution_package_cursor_bridge_counts_by_project.values())
    denied_cursor_bridge_count_total = sum(v.get("denied", 0) for v in execution_package_cursor_bridge_counts_by_project.values())
    succeeded_execution_count_total = sum(v.get("succeeded", 0) for v in execution_package_execution_counts_by_project.values())
    failed_execution_count_total = sum(v.get("failed", 0) for v in execution_package_execution_counts_by_project.values())
    blocked_execution_count_total = sum(v.get("blocked", 0) for v in execution_package_execution_counts_by_project.values())
    rolled_back_execution_count_total = sum(v.get("rolled_back", 0) for v in execution_package_execution_counts_by_project.values())
    pending_execution_count_total = sum(v.get("pending", 0) for v in execution_package_execution_counts_by_project.values())
    duplicate_success_block_count_total = sum(execution_package_duplicate_success_block_count_by_project.values())
    retry_ready_execution_count_total = sum(execution_package_retry_ready_count_by_project.values())
    repair_required_execution_count_total = sum(execution_package_repair_required_count_by_project.values())
    rollback_repair_failed_count_total = sum(execution_package_rollback_repair_failed_count_by_project.values())
    integrity_verified_count_total = sum(execution_package_integrity_verified_count_by_project.values())
    integrity_issues_count_total = sum(execution_package_integrity_issues_count_by_project.values())
    pending_evaluation_count_total = sum(v.get("pending", 0) for v in execution_package_evaluation_counts_by_project.values())
    completed_evaluation_count_total = sum(v.get("completed", 0) for v in execution_package_evaluation_counts_by_project.values())
    blocked_evaluation_count_total = sum(v.get("blocked", 0) for v in execution_package_evaluation_counts_by_project.values())
    error_evaluation_count_total = sum(v.get("error_fallback", 0) for v in execution_package_evaluation_counts_by_project.values())
    pending_local_analysis_count_total = sum(v.get("pending", 0) for v in execution_package_local_analysis_counts_by_project.values())
    completed_local_analysis_count_total = sum(v.get("completed", 0) for v in execution_package_local_analysis_counts_by_project.values())
    blocked_local_analysis_count_total = sum(v.get("blocked", 0) for v in execution_package_local_analysis_counts_by_project.values())
    error_local_analysis_count_total = sum(v.get("error_fallback", 0) for v in execution_package_local_analysis_counts_by_project.values())
    portfolio_selection = evaluate_project_selection(states_by_project=states_by_project)
    persistent_kill_switch = read_portfolio_kill_switch()
    autonomy_trace_recent = read_portfolio_trace_tail(12)

    return {
        "summary_generated_at": now,
        "studio_name": STUDIO_NAME,
        "project_summary": project_summary,
        "project_autopilot_summary": {
            "autopilot_surface_status": "ok",
            "active_autopilot_projects": sorted(set(active_autopilot_projects)),
            "autopilot_status_by_project": autopilot_status_by_project,
            "iteration_counts_by_project": iteration_counts_by_project,
            "escalation_count_total": escalation_count_total,
            "paused_count_total": paused_count_total,
            "completed_count_total": completed_count_total,
            "blocked_count_total": blocked_count_total,
            "latest_autopilot_action_by_project": latest_autopilot_action_by_project,
            "stop_rail_status_by_project": stop_rail_status_by_project,
            "stop_rail_type_by_project": stop_rail_type_by_project,
            "stop_reason_by_project": stop_reason_by_project,
            "stop_rail_routing_outcome_by_project": stop_rail_routing_outcome_by_project,
            "rail_pause_count_total": rail_pause_count_total,
            "rail_escalate_count_total": rail_escalate_count_total,
            "rail_stop_count_total": rail_stop_count_total,
        },
        "project_autonomy_routing_summary": {
            "autonomy_routing_surface_status": "ok",
            "autonomy_mode_by_project": autonomy_mode_by_project,
            "routing_status_by_project": routing_status_by_project,
            "routed_action_by_project": routed_action_by_project,
            "project_selection_status_by_project": project_selection_status_by_project,
            "last_project_selection_reason_by_project": last_project_selection_reason_by_project,
            "stop_rail_status_by_project": stop_rail_status_by_project,
            "stop_rail_routing_outcome_by_project": stop_rail_routing_outcome_by_project,
            "paused_count_total": paused_count_total,
            "escalated_count_total": escalation_count_total,
            "low_risk_mode_count_total": low_risk_mode_count_total,
            "supervised_mode_count_total": supervised_mode_count_total,
            "assisted_mode_count_total": assisted_mode_count_total,
        },
        "project_selection_summary": {
            "selection_surface_status": "ok",
            "selected_project_id": portfolio_selection.get("selected_project_id") or "",
            "eligible_project_count": len(portfolio_selection.get("eligible_projects") or []),
            "blocked_project_count": len(portfolio_selection.get("blocked_projects") or []),
            "contention_detected": bool(portfolio_selection.get("contention_detected")),
            "last_selection_reason": str(portfolio_selection.get("selection_reason") or ""),
            "why_selected": str(portfolio_selection.get("why_selected") or ""),
            "why_not_selected": list(portfolio_selection.get("why_not_selected") or []),
            "next_action": str(portfolio_selection.get("next_action") or ""),
            "next_reason": str(portfolio_selection.get("next_reason") or ""),
            "routing_outcome": str(portfolio_selection.get("routing_outcome") or ""),
            "priority_basis": str(portfolio_selection.get("priority_basis") or ""),
            "eligible_projects": list(portfolio_selection.get("eligible_projects") or []),
            "blocked_projects": list(portfolio_selection.get("blocked_projects") or []),
            "candidate_project_ids": list(portfolio_selection.get("candidate_project_ids") or []),
            "recorded_at": str(portfolio_selection.get("recorded_at") or ""),
            "revenue_priority_summary": dict(portfolio_selection.get("revenue_priority_summary") or {}),
            "persistent_kill_switch": persistent_kill_switch,
        },
        "portfolio_autonomy_hardening_summary": {
            "hardening_status": "active",
            "persistent_kill_switch": persistent_kill_switch,
            "recent_trace_highlights": autonomy_trace_recent[-6:],
            "why_selected": str(portfolio_selection.get("why_selected") or ""),
            "next_action": str(portfolio_selection.get("next_action") or ""),
            "next_reason": str(portfolio_selection.get("next_reason") or ""),
            "revenue_priority_influence": dict(portfolio_selection.get("revenue_priority_summary") or {}),
        },
        "agent_summary": agent_summary,
        "policy_summary": policy_summary,
        "tool_summary": tool_summary,
        "engine_summary": engine_summary,
        "capability_summary": capability_summary,
        "runtime_target_summary": runtime_target_summary,
        "runtime_selection_defaults": runtime_selection_defaults,
        "runtime_target_selection_summary": {
            "selection_surface_status": "ok",
            "selected_target_by_project": selected_target_by_project,
            "selection_status_by_project": target_selection_status_by_project,
            "readiness_status_by_project": target_readiness_by_project,
            "availability_status_by_project": target_availability_by_project,
            "denial_reason_by_project": target_denial_reason_by_project,
            "last_selection_reason_by_project": last_target_selection_reason_by_project,
            "selection_status_count": target_selection_status_count,
        },
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
        "governance_resolution_state_by_project": governance_resolution_state_by_project,
        "governance_resolution_state_count": governance_resolution_state_count,
        "governance_routing_outcome_by_project": governance_routing_outcome_by_project,
        "governance_routing_outcome_count": governance_routing_outcome_count,
        "governance_conflict_status_by_project": governance_conflict_status_by_project,
        "governance_conflict_status_count": governance_conflict_status_count,
        "governance_conflict_type_by_project": governance_conflict_type_by_project,
        "governance_conflict_type_count": governance_conflict_type_count,
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
        "execution_package_review_summary": {
            "review_surface_status": execution_package_review_status,
            "pending_count_total": pending_count_total,
            "packages_by_project": execution_package_recent_by_project,
            "pending_by_project": execution_package_pending_by_project,
            "latest_package_id_by_project": latest_execution_package_id_by_project,
            "latest_package_path_by_project": latest_execution_package_path_by_project,
            "review_required_projects": sorted(set(execution_package_review_required_projects)),
            "sealed_count_total": execution_package_sealed_count_total,
            "reason": execution_package_review_reason,
        },
        "execution_package_decision_summary": {
            "decision_surface_status": "ok",
            "pending_count_total": pending_decision_count_total,
            "approved_count_total": approved_decision_count_total,
            "rejected_count_total": rejected_decision_count_total,
            "decision_counts_by_project": execution_package_decision_counts_by_project,
            "latest_decision_status_by_project": latest_execution_package_decision_status_by_project,
            "decision_required_projects": sorted(set(execution_package_decision_required_projects)),
            "reason": "No execution package decisions recorded." if approved_decision_count_total == 0 and rejected_decision_count_total == 0 else "Execution package decisions available.",
        },
        "execution_package_eligibility_summary": {
            "eligibility_surface_status": "ok",
            "pending_count_total": pending_eligibility_count_total,
            "eligible_count_total": eligible_count_total,
            "ineligible_count_total": ineligible_count_total,
            "eligibility_counts_by_project": execution_package_eligibility_counts_by_project,
            "latest_eligibility_status_by_project": latest_execution_package_eligibility_status_by_project,
            "eligible_projects": sorted(set(execution_package_eligible_projects)),
            "ineligible_projects": sorted(set(execution_package_ineligible_projects)),
            "reason": "No execution package eligibility checks recorded." if eligible_count_total == 0 and ineligible_count_total == 0 else "Execution package eligibility results available.",
        },
        "execution_package_release_summary": {
            "release_surface_status": "ok",
            "pending_count_total": pending_release_count_total,
            "released_count_total": released_count_total,
            "blocked_count_total": blocked_release_count_total,
            "release_counts_by_project": execution_package_release_counts_by_project,
            "latest_release_status_by_project": latest_execution_package_release_status_by_project,
            "released_projects": sorted(set(execution_package_released_projects)),
            "blocked_projects": sorted(set(execution_package_release_blocked_projects)),
            "reason": "No execution package release requests recorded." if released_count_total == 0 and blocked_release_count_total == 0 else "Execution package release results available.",
        },
        "execution_package_handoff_summary": {
            "handoff_surface_status": "ok",
            "pending_count_total": pending_handoff_count_total,
            "authorized_count_total": authorized_handoff_count_total,
            "blocked_count_total": blocked_handoff_count_total,
            "handoff_counts_by_project": execution_package_handoff_counts_by_project,
            "latest_handoff_status_by_project": latest_execution_package_handoff_status_by_project,
            "latest_executor_target_by_project": latest_execution_package_handoff_target_by_project,
            "authorized_projects": sorted(set(execution_package_handoff_authorized_projects)),
            "blocked_projects": sorted(set(execution_package_handoff_blocked_projects)),
            "reason": "No execution package handoff requests recorded." if authorized_handoff_count_total == 0 and blocked_handoff_count_total == 0 else "Execution package handoff results available.",
        },
        "execution_package_cursor_bridge_summary": {
            "bridge_surface_status": "ok",
            "prepared_count_total": prepared_cursor_bridge_count_total,
            "artifact_recorded_count_total": artifact_recorded_cursor_bridge_count_total,
            "denied_count_total": denied_cursor_bridge_count_total,
            "bridge_counts_by_project": execution_package_cursor_bridge_counts_by_project,
            "latest_bridge_status_by_project": latest_execution_package_cursor_bridge_status_by_project,
            "latest_bridge_task_id_by_project": latest_execution_package_bridge_task_id_by_project,
            "artifact_count_by_project": execution_package_cursor_bridge_artifact_count_by_project,
            "prepared_projects": sorted(set(cursor_bridge_prepared_projects)),
            "artifact_return_projects": sorted(set(cursor_bridge_artifact_return_projects)),
            "reason": "No governed Cursor bridge records available." if prepared_cursor_bridge_count_total == 0 and artifact_recorded_cursor_bridge_count_total == 0 and denied_cursor_bridge_count_total == 0 else "Governed Cursor bridge records available.",
        },
        "execution_package_execution_summary": {
            "execution_surface_status": "ok",
            "pending_count_total": pending_execution_count_total,
            "succeeded_count_total": succeeded_execution_count_total,
            "failed_count_total": failed_execution_count_total,
            "blocked_count_total": blocked_execution_count_total,
            "rolled_back_count_total": rolled_back_execution_count_total,
            "duplicate_success_blocked_count_total": duplicate_success_block_count_total,
            "retry_ready_count_total": retry_ready_execution_count_total,
            "repair_required_count_total": repair_required_execution_count_total,
            "rollback_repair_failed_count_total": rollback_repair_failed_count_total,
            "integrity_verified_count_total": integrity_verified_count_total,
            "integrity_issues_count_total": integrity_issues_count_total,
            "execution_counts_by_project": execution_package_execution_counts_by_project,
            "duplicate_success_blocked_count_by_project": execution_package_duplicate_success_block_count_by_project,
            "retry_ready_count_by_project": execution_package_retry_ready_count_by_project,
            "repair_required_count_by_project": execution_package_repair_required_count_by_project,
            "rollback_repair_failed_count_by_project": execution_package_rollback_repair_failed_count_by_project,
            "integrity_verified_count_by_project": execution_package_integrity_verified_count_by_project,
            "integrity_issues_count_by_project": execution_package_integrity_issues_count_by_project,
            "latest_execution_status_by_project": latest_execution_package_execution_status_by_project,
            "latest_execution_target_by_project": latest_execution_package_execution_target_by_project,
            "succeeded_projects": sorted(set(execution_package_execution_succeeded_projects)),
            "failed_projects": sorted(set(execution_package_execution_failed_projects)),
            "blocked_projects": sorted(set(execution_package_execution_blocked_projects)),
            "rolled_back_projects": sorted(set(execution_package_execution_rolled_back_projects)),
            "reason": "No execution package execution requests recorded." if succeeded_execution_count_total == 0 and failed_execution_count_total == 0 and blocked_execution_count_total == 0 and rolled_back_execution_count_total == 0 else "Execution package execution results available.",
        },
        "execution_package_evaluation_summary": {
            "evaluation_surface_status": "ok",
            "pending_count_total": pending_evaluation_count_total,
            "completed_count_total": completed_evaluation_count_total,
            "blocked_count_total": blocked_evaluation_count_total,
            "error_count_total": error_evaluation_count_total,
            "evaluation_counts_by_project": execution_package_evaluation_counts_by_project,
            "latest_evaluation_status_by_project": latest_execution_package_evaluation_status_by_project,
            "execution_quality_band_count_total": execution_quality_band_count_total,
            "integrity_band_count_total": integrity_band_count_total,
            "rollback_quality_band_count_total": rollback_quality_band_count_total,
            "failure_risk_band_count_total": failure_risk_band_count_total,
            "reason": "No execution package evaluations recorded." if completed_evaluation_count_total == 0 and blocked_evaluation_count_total == 0 and error_evaluation_count_total == 0 else "Execution package evaluation results available.",
        },
        "execution_package_local_analysis_summary": {
            "analysis_surface_status": "ok",
            "pending_count_total": pending_local_analysis_count_total,
            "completed_count_total": completed_local_analysis_count_total,
            "blocked_count_total": blocked_local_analysis_count_total,
            "error_count_total": error_local_analysis_count_total,
            "analysis_counts_by_project": execution_package_local_analysis_counts_by_project,
            "latest_analysis_status_by_project": latest_execution_package_local_analysis_status_by_project,
            "confidence_band_count_total": local_analysis_confidence_band_count_total,
            "suggested_next_action_count_total": local_analysis_suggested_next_action_count_total,
            "reason": "No execution package local analyses recorded." if completed_local_analysis_count_total == 0 and blocked_local_analysis_count_total == 0 and error_local_analysis_count_total == 0 else "Execution package local analysis results available.",
        },
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
        "runtime_route_by_project": runtime_route_by_project,
        "runtime_route_count": runtime_route_count,
        "model_route_by_project": model_route_by_project,
        "model_route_count": model_route_count,
        "deployment_preflight_count": deployment_preflight_count,
        "self_evolution_governance_summary": {
            "status": "ok",
            "recent_entries": self_change_entries,
            "recent_count": len(self_change_entries),
            "risk_count_total": self_change_risk_count_total,
            "approval_requirement_count_total": self_change_approval_requirement_count_total,
            "outcome_count_total": self_change_outcome_count_total,
            "gate_outcome_count_total": self_change_gate_outcome_count_total,
            "release_lane_count_total": self_change_release_lane_count_total,
            "validation_outcome_count_total": self_change_validation_outcome_count_total,
            "sandbox_required_count_total": self_change_sandbox_required_count_total,
            "sandbox_status_count_total": self_change_sandbox_status_count_total,
            "sandbox_result_count_total": self_change_sandbox_result_count_total,
            "promotion_status_count_total": self_change_promotion_status_count_total,
            "comparison_status_count_total": self_change_comparison_status_count_total,
            "confidence_band_count_total": self_change_confidence_band_count_total,
            "promotion_confidence_count_total": self_change_promotion_confidence_count_total,
            "recommendation_count_total": self_change_recommendation_count_total,
            "monitoring_status_count_total": self_change_monitoring_status_count_total,
            "rollback_trigger_outcome_count_total": self_change_rollback_trigger_outcome_count_total,
            "stable_status_count_total": self_change_stable_status_count_total,
            "rollback_scope_count_total": self_change_rollback_scope_count_total,
            "blast_radius_count_total": self_change_blast_radius_count_total,
            "rollback_status_count_total": self_change_rollback_status_count_total,
            "rollback_follow_up_validation_required_count_total": self_change_rollback_follow_up_validation_required_count_total,
            "mutation_rate_status_count_total": self_change_mutation_rate_status_count_total,
            "control_outcome_count_total": self_change_control_outcome_count_total,
            "cool_down_required_count_total": self_change_cool_down_required_count_total,
            "stability_state_count_total": self_change_stability_state_count_total,
            "turbulence_level_count_total": self_change_turbulence_level_count_total,
            "freeze_required_count_total": self_change_freeze_required_count_total,
            "freeze_scope_count_total": self_change_freeze_scope_count_total,
            "recovery_only_mode_count_total": self_change_recovery_only_mode_count_total,
            "escalation_required_count_total": self_change_escalation_required_count_total,
            "checkpoint_required_count_total": self_change_checkpoint_required_count_total,
            "checkpoint_scope_count_total": self_change_checkpoint_scope_count_total,
            "checkpoint_status_count_total": self_change_checkpoint_status_count_total,
            "executive_approval_required_count_total": self_change_executive_approval_required_count_total,
            "manual_hold_active_count_total": self_change_manual_hold_active_count_total,
            "manual_hold_scope_count_total": self_change_manual_hold_scope_count_total,
            "override_status_count_total": self_change_override_status_count_total,
            "rollout_stage_count_total": self_change_rollout_stage_count_total,
            "rollout_scope_count_total": self_change_rollout_scope_count_total,
            "rollout_status_count_total": self_change_rollout_status_count_total,
            "cohort_type_count_total": self_change_cohort_type_count_total,
            "stage_promotion_required_count_total": self_change_stage_promotion_required_count_total,
            "broader_rollout_blocked_count_total": self_change_broader_rollout_blocked_count_total,
            "trust_status_count_total": self_change_trust_status_count_total,
            "decay_state_count_total": self_change_decay_state_count_total,
            "revalidation_required_count_total": self_change_revalidation_required_count_total,
            "trust_outcome_count_total": self_change_trust_outcome_count_total,
            "drift_detected_count_total": self_change_drift_detected_count_total,
            "strategic_intent_category_count_total": self_change_strategic_intent_category_count_total,
            "alignment_status_count_total": self_change_alignment_status_count_total,
            "prohibited_goal_hit_count_total": self_change_prohibited_goal_hit_count_total,
            "executive_priority_match_count_total": self_change_executive_priority_match_count_total,
            "mission_scope_count_total": self_change_mission_scope_count_total,
            "strategic_outcome_count_total": self_change_strategic_outcome_count_total,
            "roi_band_count_total": self_change_roi_band_count_total,
            "value_status_count_total": self_change_value_status_count_total,
            "priority_value_count_total": self_change_priority_value_count_total,
            "recommended_action_count_total": self_change_recommended_action_count_total,
            "value_outcome_count_total": self_change_value_outcome_count_total,
            "protected_zone_hits": self_change_protected_zone_hits,
            "pending_approval_count_total": self_change_pending_approval_count_total,
            "success_count_total": self_change_success_count_total,
            "failure_count_total": self_change_failure_count_total,
            "rollback_required_count_total": self_change_rollback_required_count_total,
            "reason": "No self-change audit records available." if not self_change_entries else "Self-change audit records available.",
        },
        "self_improvement_backlog_count": backlog_count,
        "selected_improvement_summary": selected_improvement_summary,
        "change_gate_status_count": change_gate_status_count,
        # Forge OS Sprint 5 additions (summary-only).
        "portfolio_summary": portfolio_summary,
        "runtime_infrastructure_summary": runtime_infrastructure_summary,
        "execution_environment_summary": execution_environment_summary,
        "approval_summary": approval_summary,
        "product_summary": product_summary,
        "autonomy_summary": autonomy_summary,
        "helix_summary": helix_summary,
        "patch_proposal_summary": patch_proposal_summary,
        "release_readiness_summary": _build_release_readiness_from_dashboard(
            product_summary=product_summary,
            approval_summary=approval_summary,
            patch_proposal_summary=patch_proposal_summary,
            execution_environment_summary=execution_environment_summary,
            autonomy_summary=autonomy_summary,
            helix_summary=helix_summary,
        ),
        "cross_artifact_trace_summary": _build_cross_artifact_trace_for_dashboard(),
        "meta_engine_summary": meta_engine_summary,
        "meta_engine_review_required_count": meta_engine_review_required_count,
        "meta_engine_governance": meta_engine_governance,
        "memory_layer_summary": memory_layer_summary,
        # Phase 6 elite capability layers (summary-oriented).
        "titan_summary": titan_summary,
        "leviathan_summary": leviathan_summary,
        "helios_summary": helios_summary,
        "veritas_summary": veritas_summary,
        "sentinel_summary": sentinel_summary,
        "helios_proposal_summary": helios_proposal_summary,
        # Phase 10 visibility.
        "genesis_summary": genesis_summary,
        # Phase 12: bounded studio loop (selection-only).
        "studio_loop_summary": studio_loop_summary,
        # Phase 12: priority-project signals for cross-intelligence (read-only).
        "prism_result": prism_result,
        "last_aegis_decision": last_aegis_decision,
        # Phase 13: AEGIS / ForgeShell / tool gateway.
        "aegis_summary": aegis_summary,
        "forgeshell_summary": forgeshell_summary,
        "tool_gateway_summary": tool_gateway_summary,
        # PRISM v1 dashboard visibility (read-only persisted outputs).
        "prism_status_by_project": prism_status_by_project,
        "prism_recommendation_count": prism_recommendation_count,
        "prism_go_count": prism_go_count,
        "prism_revise_count": prism_revise_count,
        "prism_hold_count": prism_hold_count,
        "regression_status": regression_status,
    }
