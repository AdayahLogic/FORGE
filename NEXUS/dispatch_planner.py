"""
NEXUS dispatch planning layer.

Produces a normalized dispatch plan from planning, routing, and execution bridge
outputs. Planning only; no execution. Tolerates missing data; safe defaults.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

DISPATCH_VERSION = "1.0"


def build_dispatch_plan(
    project_id: str | None = None,
    project_summary: dict | None = None,
    request: str | dict | None = None,
    planner_output: dict | None = None,
    router_output: dict | None = None,
    execution_bridge_packet: dict | None = None,
) -> dict[str, Any]:
    """
    Build a normalized dispatch plan from optional upstream inputs.

    Returns dict with: dispatch_version, dispatch_planning_status, ready_for_dispatch,
    project, request, routing, execution, artifacts, governance, timestamps.
    Tolerates missing data; uses safe defaults.
    """
    now_utc = datetime.now(timezone.utc).isoformat()
    packet = execution_bridge_packet or {}
    router = router_output or {}
    planner = planner_output or {}
    project_summary = project_summary or {}

    project_id = project_id or (project_summary.get("project_id") if isinstance(project_summary, dict) else None)
    project_name = None
    project_path = None
    if isinstance(project_summary, dict):
        project_name = project_summary.get("project_name") or project_summary.get("active_project")
        project_path = project_summary.get("project_path")
    project = {
        "project_id": project_id or "",
        "project_name": project_name or "",
        "project_path": project_path or "",
    }

    request_summary = ""
    if isinstance(request, str):
        request_summary = request[:500]
    elif isinstance(request, dict):
        request_summary = str(request.get("summary", request))[:500]
    request_type = "user_request"
    if planner and isinstance(planner, dict):
        request_type = planner.get("request_type") or request_type
    task_type = packet.get("runtime_node") or router.get("runtime_node") or ""
    if planner and isinstance(planner, dict) and planner.get("next_agent"):
        task_type = task_type or planner.get("next_agent")
    request_block = {
        "request_id": "",
        "request_type": request_type,
        "task_type": task_type,
        "summary": request_summary,
        "priority": "normal",
    }

    runtime_node = packet.get("runtime_node") or router.get("runtime_node") or "unknown"
    agent_name = router.get("runtime_node") or runtime_node
    tool_name = packet.get("primary_tool") or ""
    selection_status = packet.get("runtime_selection_status") or "selected"
    selection_reason = packet.get("runtime_selection_reason") or ""
    routing = {
        "runtime_node": runtime_node,
        "agent_name": agent_name,
        "tool_name": tool_name,
        "selection_status": selection_status,
        "selection_reason": selection_reason,
    }

    runtime_target_id = packet.get("selected_runtime_target") or "local"
    runtime_target_name = runtime_target_id
    requires_human = packet.get("human_review_required") or packet.get("runtime_review_required") or False

    # Generalized readiness: valid target present and selection not in failure/fallback set
    _placeholder_targets = ("", "unassigned", "unknown")
    _unready_selection_statuses = ("error_fallback", "unavailable", "rejected", "failed")
    _valid_target = (
        runtime_target_id is not None
        and str(runtime_target_id).strip() != ""
        and str(runtime_target_id).strip().lower() not in _placeholder_targets
    )
    _selection_unready = (selection_status or "").strip().lower() in _unready_selection_statuses
    ready_for_dispatch = _valid_target and not _selection_unready
    can_execute = ready_for_dispatch

    execution = {
        "execution_mode": "targeted_runtime",
        "runtime_target_id": runtime_target_id,
        "runtime_target_name": runtime_target_name,
        "requires_human_approval": requires_human,
        "can_execute": can_execute,
    }

    artifacts = {
        "expected_outputs": [],
        "target_files": [],
        "patch_strategy": "incremental",
    }
    if planner and isinstance(planner, dict) and planner.get("patch_request"):
        artifacts["patch_strategy"] = "patch_request_present"

    governance = {
        "policy_checked": True,
        "approval_status": "not_required" if not requires_human else "pending_review",
        "risk_level": "low",
    }

    return {
        "dispatch_version": DISPATCH_VERSION,
        "dispatch_planning_status": "planned",
        "ready_for_dispatch": ready_for_dispatch,
        "project": project,
        "request": request_block,
        "routing": routing,
        "execution": execution,
        "artifacts": artifacts,
        "governance": governance,
        "timestamps": {
            "planned_at": now_utc,
        },
    }


def build_dispatch_plan_safe(
    project_id: str | None = None,
    project_summary: dict | None = None,
    request: str | dict | None = None,
    planner_output: dict | None = None,
    router_output: dict | None = None,
    execution_bridge_packet: dict | None = None,
) -> dict[str, Any]:
    """
    Build dispatch plan; on any exception return fallback structure with
    dispatch_planning_status = "error_fallback", ready_for_dispatch = False.
    """
    try:
        return build_dispatch_plan(
            project_id=project_id,
            project_summary=project_summary or {},
            request=request,
            planner_output=planner_output,
            router_output=router_output,
            execution_bridge_packet=execution_bridge_packet,
        )
    except Exception:
        return {
            "dispatch_version": DISPATCH_VERSION,
            "dispatch_planning_status": "error_fallback",
            "ready_for_dispatch": False,
            "project": {"project_id": "", "project_name": "", "project_path": ""},
            "request": {"request_id": "", "request_type": "user_request", "task_type": "", "summary": "", "priority": "normal"},
            "routing": {"runtime_node": "unknown", "agent_name": "", "tool_name": "", "selection_status": "error_fallback", "selection_reason": "Dispatch planning failed."},
            "execution": {"execution_mode": "targeted_runtime", "runtime_target_id": "local", "runtime_target_name": "local", "requires_human_approval": True, "can_execute": False},
            "artifacts": {"expected_outputs": [], "target_files": [], "patch_strategy": "incremental"},
            "governance": {"policy_checked": False, "approval_status": "pending_review", "risk_level": "unknown"},
            "timestamps": {"planned_at": datetime.now(timezone.utc).isoformat()},
        }
