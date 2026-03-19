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
from NEXUS.tool_registry import TOOL_REGISTRY, TOOL_CONTRACT_VERSION, list_active_tools, list_planned_tools
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
    runtime_route_by_project: dict[str, str] = {}
    runtime_route_count: dict[str, int] = {}
    model_route_by_project: dict[str, str] = {}
    model_route_count: dict[str, int] = {}
    deployment_preflight_count: dict[str, int] = {}
    change_gate_status_count: dict[str, int] = {}
    regression_status_count: dict[str, int] = {}
    prism_status_by_project: dict[str, str] = {}
    prism_recommendation_count: dict[str, int] = {"go": 0, "revise": 0, "hold": 0}
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
            },
            studio_coordination_summary=studio_coordination_summary,
            studio_driver_summary=studio_driver_summary,
            project_name=(portfolio_summary.get("priority_project") or "jarvis") if isinstance(portfolio_summary, dict) else "jarvis",
            live_regression=False,
            helios_evaluation_mode="dashboard_cached",
        )

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
        }
        approval_summary = {
            "approval_status": "error_fallback",
            "pending_count_total": 0,
            "pending_by_project": {},
            "recent_approvals": [],
            "approval_types": [],
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
            "recent_runs": [],
            "per_project": {},
            "reason": "HELIX summary failed.",
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
        "runtime_route_by_project": runtime_route_by_project,
        "runtime_route_count": runtime_route_count,
        "model_route_by_project": model_route_by_project,
        "model_route_count": model_route_count,
        "deployment_preflight_count": deployment_preflight_count,
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
        "meta_engine_summary": meta_engine_summary,
        "meta_engine_review_required_count": meta_engine_review_required_count,
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
