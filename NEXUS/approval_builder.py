"""
NEXUS approval builder (Phase 18).

Builds approval records from workflow state, tool metadata, execution environment.
Determines requires_human, approval_type, reason.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from NEXUS.execution_environment_registry import get_environment_definition, get_environment_for_runtime_target
from NEXUS.tool_registry import TOOL_REGISTRY


def build_approval_record(
    *,
    dispatch_plan: dict[str, Any] | None = None,
    aegis_result: dict[str, Any] | None = None,
    approval_type: str | None = None,
    reason: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """
    Build a normalized approval record from workflow state.

    Pulls from:
    - dispatch_plan: project, execution, routing
    - aegis_result: approval_required, aegis_reason
    - tool metadata: sensitivity, risk_level
    - execution environment: human_review_required

    Returns normalized record ready for append_approval_record.
    """
    plan = dispatch_plan or {}
    aegis = aegis_result or {}
    project = plan.get("project") or {}
    exec_block = plan.get("execution") or {}
    routing = plan.get("routing") or {}

    project_name = project.get("project_name") or ""
    project_path = project.get("project_path") or ""
    runtime_target_id = (exec_block.get("runtime_target_id") or "local").strip().lower()
    tool_name = (routing.get("tool_name") or "").strip()
    agent_name = (routing.get("agent_name") or routing.get("runtime_node") or "").strip()

    requires_human = bool(
        aegis.get("approval_required")
        or aegis.get("requires_human_review")
        or exec_block.get("requires_human_approval")
    )
    if not requires_human:
        env_id = get_environment_for_runtime_target(runtime_target_id)
        env_def = get_environment_definition(env_id)
        if env_def and env_def.get("human_review_required"):
            requires_human = True
    if not requires_human and tool_name:
        tool_meta = TOOL_REGISTRY.get(tool_name) or {}
        if tool_meta.get("human_review_recommended") or tool_meta.get("sensitivity") == "high":
            requires_human = True

    if not approval_type:
        if aegis.get("approval_required"):
            approval_type = "aegis_policy"
        elif exec_block.get("requires_human_approval"):
            approval_type = "dispatch_plan"
        elif tool_name and TOOL_REGISTRY.get(tool_name, {}).get("sensitivity") == "high":
            approval_type = "tool_sensitivity"
        else:
            approval_type = "execution_gate"

    if not reason:
        aegis_reason = str(aegis.get("aegis_reason") or "")
        if aegis_reason:
            reason = aegis_reason
        elif requires_human:
            reason = f"Human approval required for {approval_type}; tool={tool_name}; runtime={runtime_target_id}."
        else:
            reason = "Approval gate triggered."

    tool_meta = TOOL_REGISTRY.get(tool_name) or {}
    risk_level = str(tool_meta.get("risk_level") or "unknown")
    sensitivity = str(tool_meta.get("sensitivity") or "unknown")

    context: dict[str, Any] = {
        "runtime_target_id": runtime_target_id,
        "tool_name": tool_name,
        "agent_name": agent_name,
        "aegis_decision": aegis.get("aegis_decision"),
        "aegis_scope": aegis.get("aegis_scope"),
    }
    triage_category = "risky_external" if (
        approval_type in ("aegis_policy", "communication", "billing")
        or risk_level in ("high", "critical")
        or sensitivity in ("high", "critical")
    ) else ("internal_controlled" if approval_type in ("dispatch_plan", "execution_gate", "tool_sensitivity") else "internal_low_risk")
    triage_priority = "high" if triage_category == "risky_external" else ("medium" if triage_category == "internal_controlled" else "low")
    triage_batchable = triage_category == "internal_low_risk"
    triage_batch_key = (
        f"{triage_category}:{approval_type}:{runtime_target_id or 'unknown'}"
        if triage_batchable
        else ""
    )

    return {
        "approval_id": uuid.uuid4().hex[:16],
        "run_id": run_id or "",
        "project_name": project_name,
        "timestamp": datetime.now().isoformat(),
        "status": "pending",
        "approval_type": approval_type,
        "reason": reason,
        "requested_by": agent_name or "workflow",
        "requires_human": requires_human,
        "risk_level": risk_level,
        "sensitivity": sensitivity,
        "context": context,
        "triage_category": triage_category,
        "triage_priority": triage_priority,
        "triage_batchable": triage_batchable,
        "triage_batch_key": triage_batch_key,
        "decision": None,
        "decision_timestamp": None,
    }
