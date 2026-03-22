"""
NEXUS review-only execution package builder.

Builds a sealed execution envelope from an existing dispatch plan, AEGIS result,
and optional approval context. This layer is review-only and never executes.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any


def _derive_candidate_paths(dispatch_plan: dict[str, Any]) -> list[str]:
    project = dispatch_plan.get("project") or {}
    artifacts = dispatch_plan.get("artifacts") or {}
    project_path = str(project.get("project_path") or "").strip()
    target_files = artifacts.get("target_files") or []
    out: list[str] = []
    for item in target_files:
        s = str(item).strip()
        if not s:
            continue
        if project_path and not (":" in s or s.startswith("\\") or s.startswith("/")):
            out.append(f"{project_path}\\{s}".replace("/", "\\"))
        else:
            out.append(s)
    return out[:50]


def _derive_review_checklist(dispatch_plan: dict[str, Any], approval_required: bool, runtime_target_id: str) -> list[str]:
    routing = dispatch_plan.get("routing") or {}
    tool_name = str(routing.get("tool_name") or "").strip() or "unknown"
    runtime_node = str(routing.get("runtime_node") or "").strip() or "unknown"
    checklist = [
        f"Confirm runtime target '{runtime_target_id}' should remain review-only for this action.",
        f"Confirm routing from runtime node '{runtime_node}' via tool '{tool_name}' is expected.",
        "Confirm the command request and candidate paths are within project scope.",
        "Confirm the package remains sealed and is not handed to a live executor in Phase 1.",
        "Review rollback notes before any later activation step.",
    ]
    if approval_required:
        checklist.insert(0, "Confirm required human approval is resolved before any later execution handoff.")
    return checklist[:20]


def build_execution_package(
    *,
    dispatch_plan: dict[str, Any] | None = None,
    aegis_result: dict[str, Any] | None = None,
    approval_record: dict[str, Any] | None = None,
    approval_id: str | None = None,
    package_reason: str | None = None,
    package_status: str = "review_pending",
) -> dict[str, Any]:
    """
    Build a normalized review-only execution package.
    """
    plan = dispatch_plan or {}
    aegis = aegis_result or {}
    approval = approval_record or {}
    project = plan.get("project") or {}
    routing = plan.get("routing") or {}
    execution = plan.get("execution") or {}
    request = plan.get("request") or {}
    artifacts = plan.get("artifacts") or {}

    project_name = str(project.get("project_name") or "")
    project_path = str(project.get("project_path") or "")
    runtime_target_id = str(execution.get("runtime_target_id") or "local").strip().lower()
    requires_human_approval = bool(
        execution.get("requires_human_approval")
        or aegis.get("approval_required")
        or aegis.get("requires_human_review")
        or approval.get("requires_human")
    )

    approval_refs: list[str] = []
    if approval_id:
        approval_refs.append(str(approval_id))
    approval_record_id = approval.get("approval_id")
    if approval_record_id and approval_record_id not in approval_refs:
        approval_refs.append(str(approval_record_id))

    candidate_paths = _derive_candidate_paths(plan)
    expected_outputs = [str(x) for x in (artifacts.get("expected_outputs") or []) if str(x).strip()][:50]
    reason = str(
        package_reason
        or approval.get("reason")
        or aegis.get("aegis_reason")
        or "Review-only execution package created; live execution disabled."
    )

    return {
        "package_id": uuid.uuid4().hex[:16],
        "package_version": "1.0",
        "package_kind": "review_only_execution_envelope",
        "project_name": project_name,
        "project_path": project_path,
        "run_id": str(approval.get("run_id") or ""),
        "created_at": datetime.now().isoformat(),
        "package_status": package_status,
        "review_status": "pending",
        "sealed": True,
        "seal_reason": "Phase 1 review-only package. OpenClaw remains inactive; no execution authority granted.",
        "runtime_target_id": runtime_target_id,
        "runtime_target_name": runtime_target_id,
        "execution_mode": "manual_only",
        "requested_action": "adapter_dispatch_call",
        "requested_by": str(approval.get("requested_by") or routing.get("agent_name") or routing.get("runtime_node") or "workflow"),
        "requires_human_approval": requires_human_approval,
        "approval_id_refs": approval_refs,
        "aegis_decision": str(aegis.get("aegis_decision") or ""),
        "aegis_scope": str(aegis.get("aegis_scope") or ""),
        "reason": reason,
        "dispatch_plan_summary": {
            "dispatch_version": plan.get("dispatch_version"),
            "dispatch_planning_status": plan.get("dispatch_planning_status"),
            "ready_for_dispatch": bool(plan.get("ready_for_dispatch", False)),
            "planned_at": (plan.get("timestamps") or {}).get("planned_at"),
        },
        "routing_summary": {
            "runtime_node": routing.get("runtime_node"),
            "agent_name": routing.get("agent_name"),
            "tool_name": routing.get("tool_name"),
            "selection_status": routing.get("selection_status"),
            "selection_reason": routing.get("selection_reason"),
        },
        "execution_summary": {
            "runtime_target_id": runtime_target_id,
            "runtime_target_name": runtime_target_id,
            "requires_human_approval": bool(execution.get("requires_human_approval", False)),
            "can_execute": False,
            "review_only": True,
        },
        "command_request": {
            "request_type": request.get("request_type"),
            "task_type": request.get("task_type"),
            "summary": request.get("summary"),
            "priority": request.get("priority"),
        },
        "candidate_paths": candidate_paths,
        "expected_outputs": expected_outputs,
        "review_checklist": _derive_review_checklist(plan, requires_human_approval, runtime_target_id),
        "rollback_notes": [
            "Do not execute directly from this package in Phase 1.",
            "If package content is wrong, discard the package and regenerate from dispatch state.",
            "Any later activation must preserve approval checks and project-scope controls.",
        ],
        "runtime_artifacts": [],
        "metadata": {
            "openclaw_active": False,
            "future_executor": "OpenClaw",
            "review_only_phase": "phase_1",
        },
    }


def build_execution_package_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return build_execution_package(**kwargs)
    except Exception as e:
        return {
            "package_id": uuid.uuid4().hex[:16],
            "package_version": "1.0",
            "package_kind": "review_only_execution_envelope",
            "project_name": "",
            "project_path": "",
            "run_id": "",
            "created_at": datetime.now().isoformat(),
            "package_status": "error_fallback",
            "review_status": "pending",
            "sealed": True,
            "seal_reason": "Execution package build failed; package remains inert.",
            "runtime_target_id": "local",
            "runtime_target_name": "local",
            "execution_mode": "manual_only",
            "requested_action": "adapter_dispatch_call",
            "requested_by": "workflow",
            "requires_human_approval": True,
            "approval_id_refs": [],
            "aegis_decision": "",
            "aegis_scope": "",
            "reason": str(e),
            "dispatch_plan_summary": {},
            "routing_summary": {},
            "execution_summary": {"can_execute": False, "review_only": True},
            "command_request": {},
            "candidate_paths": [],
            "expected_outputs": [],
            "review_checklist": ["Review package build failure before any later use."],
            "rollback_notes": ["Discard this package; do not use it for execution."],
            "runtime_artifacts": [],
            "metadata": {"openclaw_active": False, "build_error": str(e)},
        }
