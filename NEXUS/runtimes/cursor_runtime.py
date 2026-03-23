"""
NEXUS Cursor runtime adapter.

Simulated dispatch only; no real execution.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from NEXUS.authority_model import enforce_component_authority_safe
from NEXUS.runtime_execution import build_runtime_execution_result

CURSOR_BRIDGE_PHASE = "phase_5_hardened"
CURSOR_BRIDGE_CONTRACT_VERSION = "1.0"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _string_list(value: Any, *, limit: int = 50) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = []
    out: list[str] = []
    for item in items:
        normalized = str(item or "").strip()
        if normalized:
            out.append(normalized)
    return out[:limit]


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def build_cursor_bridge_result(
    *,
    status: str,
    operation: str,
    actor: str,
    reason: str,
    authority_trace: dict[str, Any] | None = None,
    governance_trace: dict[str, Any] | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "status": str(status or "error").strip().lower(),
        "operation": str(operation or "").strip().lower(),
        "actor": str(actor or "cursor_bridge").strip() or "cursor_bridge",
        "reason": str(reason or "").strip(),
        "authority_trace": _dict_value(authority_trace),
        "governance_trace": _dict_value(governance_trace),
    }
    if isinstance(extra_fields, dict):
        result.update(extra_fields)
    return result


def normalize_cursor_bridge_handoff(
    dispatch_plan: dict[str, Any] | None,
    *,
    authority_trace: dict[str, Any] | None = None,
    governance_trace: dict[str, Any] | None = None,
    package_id: str | None = None,
    package_reference: dict[str, Any] | None = None,
    status: str = "prepared",
) -> dict[str, Any]:
    plan = dispatch_plan if isinstance(dispatch_plan, dict) else {}
    project = _dict_value(plan.get("project"))
    request = _dict_value(plan.get("request"))
    artifacts = _dict_value(plan.get("artifacts"))
    routing = _dict_value(plan.get("routing"))
    execution = _dict_value(plan.get("execution"))
    constraints = _dict_value(plan.get("constraints"))
    reference = _dict_value(package_reference)
    linked_package_id = str(package_id or reference.get("package_id") or plan.get("package_id") or "").strip()
    if linked_package_id:
        reference["package_id"] = linked_package_id
    if not reference and linked_package_id:
        reference = {"package_id": linked_package_id}
    requested_artifacts = _string_list(
        plan.get("requested_artifacts") or artifacts.get("expected_outputs") or request.get("requested_artifacts") or ["patch_summary", "changed_files"]
    )
    scope = {
        "project_path": str(plan.get("project_path") or project.get("project_path") or "").strip(),
        "target_files": _string_list(plan.get("target_files") or artifacts.get("target_files")),
        "expected_outputs": _string_list(plan.get("expected_outputs") or requested_artifacts),
    }
    normalized_constraints = {
        "requires_human_approval": bool(execution.get("requires_human_approval", False)),
        "execution_mode": str(execution.get("execution_mode") or "manual_only").strip().lower(),
        "can_execute": False,
        "review_only": True,
        "constraints": constraints,
    }
    return {
        "contract_version": CURSOR_BRIDGE_CONTRACT_VERSION,
        "bridge_task_id": str(plan.get("bridge_task_id") or uuid.uuid4().hex[:16]),
        "project_id": str(plan.get("project_id") or project.get("project_id") or plan.get("project_name") or project.get("project_name") or "").strip(),
        "package_id": linked_package_id,
        "package_reference": reference,
        "task_type": str(plan.get("task_type") or request.get("task_type") or request.get("request_type") or "development").strip().lower(),
        "objective": str(plan.get("objective") or request.get("summary") or request.get("objective") or "").strip(),
        "scope": scope,
        "constraints": _dict_value(plan.get("constraints")) or normalized_constraints,
        "requested_artifacts": requested_artifacts,
        "actor": str(plan.get("actor") or routing.get("agent_name") or routing.get("runtime_node") or "nexus").strip(),
        "created_at": str(plan.get("created_at") or ((plan.get("timestamps") or {}).get("planned_at")) or _utc_now_iso()),
        "status": str(status or "prepared").strip().lower(),
        "source_runtime": str(plan.get("source_runtime") or "cursor").strip().lower(),
        "authority_trace": _dict_value(authority_trace or plan.get("authority_trace")),
        "governance_trace": _dict_value(governance_trace or plan.get("governance_trace")),
    }


def normalize_cursor_artifact_return(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    package_reference = _dict_value(raw.get("package_reference"))
    package_id = str(raw.get("package_id") or package_reference.get("package_id") or "").strip()
    if package_id:
        package_reference["package_id"] = package_id
    return {
        "contract_version": CURSOR_BRIDGE_CONTRACT_VERSION,
        "bridge_task_id": str(raw.get("bridge_task_id") or "").strip(),
        "package_id": package_id,
        "package_reference": package_reference,
        "artifact_type": str(raw.get("artifact_type") or "").strip().lower(),
        "artifact_summary": str(raw.get("artifact_summary") or "").strip(),
        "changed_files": _string_list(raw.get("changed_files"), limit=100),
        "patch_summary": _dict_value(raw.get("patch_summary")),
        "validation_status": str(raw.get("validation_status") or "pending").strip().lower(),
        "source_runtime": str(raw.get("source_runtime") or "cursor").strip().lower(),
        "actor": str(raw.get("actor") or "cursor_bridge").strip() or "cursor_bridge",
        "recorded_at": str(raw.get("recorded_at") or _utc_now_iso()),
        "status": str(raw.get("status") or "returned").strip().lower(),
        "authority_trace": _dict_value(raw.get("authority_trace")),
        "governance_trace": _dict_value(raw.get("governance_trace")),
    }


def validate_cursor_artifact_return(
    payload: dict[str, Any] | None,
    *,
    required_package_id: str | None = None,
    expected_bridge_task_id: str | None = None,
) -> dict[str, Any]:
    normalized = normalize_cursor_artifact_return(payload)
    actor = normalized.get("actor") or "cursor_bridge"
    authority_trace = normalized.get("authority_trace") or {}
    governance_trace = normalized.get("governance_trace") or {}
    required_fields = {
        "bridge_task_id": normalized.get("bridge_task_id"),
        "artifact_type": normalized.get("artifact_type"),
        "artifact_summary": normalized.get("artifact_summary"),
        "actor": actor,
        "source_runtime": normalized.get("source_runtime"),
    }
    missing = [key for key, value in required_fields.items() if not str(value or "").strip()]
    if not normalized.get("package_id") and not _dict_value(normalized.get("package_reference")):
        missing.append("package_id")
    if missing:
        return build_cursor_bridge_result(
            status="denied",
            operation="validation",
            actor=actor,
            reason=f"Malformed Cursor artifact return; missing required fields: {', '.join(sorted(set(missing)))}.",
            authority_trace=authority_trace,
            governance_trace=governance_trace,
            extra_fields={"validation_status": "rejected_malformed", "artifact_payload": normalized},
        )

    raw = payload if isinstance(payload, dict) else {}
    authority_markers = {
        "can_execute": bool(raw.get("can_execute")),
        "execution_mode": str(raw.get("execution_mode") or "").strip().lower(),
        "approval_status": str(raw.get("approval_status") or "").strip().lower(),
        "governance_status": str(raw.get("governance_status") or "").strip().lower(),
        "execution_status": str(raw.get("execution_status") or "").strip().lower(),
    }
    implies_execution_authority = (
        authority_markers["can_execute"]
        or authority_markers["execution_mode"] in ("direct_local", "external_runtime")
        or authority_markers["approval_status"] not in ("", "pending", "not_requested")
        or authority_markers["governance_status"] not in ("", "advisory_only", "linked")
        or authority_markers["execution_status"] not in ("", "not_started", "returned", "simulated_execution")
        or normalized.get("artifact_type") in ("execution_receipt", "approval_decision", "governance_decision")
    )
    if implies_execution_authority:
        return build_cursor_bridge_result(
            status="denied",
            operation="validation",
            actor=actor,
            reason="Cursor artifact return implied execution, approval, or governance authority.",
            authority_trace=authority_trace,
            governance_trace=governance_trace,
            extra_fields={"validation_status": "rejected_authority_boundary", "artifact_payload": normalized},
        )

    if required_package_id and normalized.get("package_id") != str(required_package_id).strip():
        return build_cursor_bridge_result(
            status="denied",
            operation="validation",
            actor=actor,
            reason="Cursor artifact return bypassed package linkage.",
            authority_trace=authority_trace,
            governance_trace=governance_trace,
            extra_fields={"validation_status": "rejected_package_linkage", "artifact_payload": normalized},
        )

    if expected_bridge_task_id and normalized.get("bridge_task_id") != str(expected_bridge_task_id).strip():
        return build_cursor_bridge_result(
            status="denied",
            operation="validation",
            actor=actor,
            reason="Cursor artifact return bridge_task_id did not match the governed handoff.",
            authority_trace=authority_trace,
            governance_trace=governance_trace,
            extra_fields={"validation_status": "rejected_bridge_task_mismatch", "artifact_payload": normalized},
        )

    return build_cursor_bridge_result(
        status="ok",
        operation="validation",
        actor=actor,
        reason="Cursor artifact return validated.",
        authority_trace=authority_trace,
        governance_trace=governance_trace,
        extra_fields={"validation_status": "validated", "artifact_payload": normalized},
    )


def dispatch(dispatch_plan: dict[str, Any]) -> dict[str, Any]:
    """Simulate dispatch to Cursor runtime. Returns status and message."""
    execution = (dispatch_plan or {}).get("execution") or {}
    execution_requested = bool(execution.get("can_execute")) or str(execution.get("execution_mode") or "").strip().lower() in ("direct_local", "external_runtime")
    enforcement = enforce_component_authority_safe(
        component_name="cursor_bridge",
        actor="cursor_bridge",
        requested_actions=["prepare_ide_handoff", "package_generation_output", "execute_package"] if execution_requested else ["prepare_ide_handoff", "package_generation_output"],
        allowed_components=["cursor_bridge"],
        authority_context={"runtime_target_id": "cursor", "execution_requested": execution_requested},
        denied_action="execute_package" if execution_requested else "",
        reason_override="Cursor bridge remains planned-only in this phase and cannot gain execution authority." if execution_requested else None,
    )
    authority_trace = enforcement.get("authority_trace") or {}
    if enforcement.get("status") == "denied":
        cursor_bridge_summary = normalize_cursor_bridge_handoff(
            dispatch_plan,
            authority_trace=authority_trace,
            package_id=str((dispatch_plan or {}).get("package_id") or ""),
            package_reference=_dict_value((dispatch_plan or {}).get("package_reference")),
            status="denied",
        )
        return build_runtime_execution_result(
            runtime="cursor",
            status="blocked",
            message=str((enforcement.get("authority_denial") or {}).get("reason") or "Cursor bridge authority denied."),
            execution_status="blocked",
            execution_mode="safe_simulation",
            next_action="human_review",
            extra_fields={
                "authority_denial": enforcement.get("authority_denial") or {},
                "authority_trace": authority_trace,
                "cursor_bridge_result": build_cursor_bridge_result(
                    status="denied",
                    operation="handoff",
                    actor="cursor_bridge",
                    reason=str((enforcement.get("authority_denial") or {}).get("reason") or "Cursor bridge authority denied."),
                    authority_trace=authority_trace,
                    governance_trace=cursor_bridge_summary.get("governance_trace"),
                ),
                "cursor_bridge_summary": {
                    **cursor_bridge_summary,
                    "bridge_status": "denied",
                    "bridge_phase": CURSOR_BRIDGE_PHASE,
                    "authority_scope": "generation_bridge_only",
                    "execution_enabled": False,
                    "handoff_required": True,
                },
            },
        )
    cursor_bridge_summary = normalize_cursor_bridge_handoff(
        dispatch_plan,
        authority_trace=authority_trace,
        package_id=str((dispatch_plan or {}).get("package_id") or ""),
        package_reference=_dict_value((dispatch_plan or {}).get("package_reference")),
        status="prepared",
    )
    return build_runtime_execution_result(
        runtime="cursor",
        status="accepted",
        message="Governed Cursor bridge handoff prepared (simulated).",
        execution_status="queued",
        execution_mode="manual_only",
        next_action="await_cursor_artifact_return",
        extra_fields={
            "authority_trace": authority_trace,
            "cursor_bridge_result": build_cursor_bridge_result(
                status="ok",
                operation="handoff",
                actor="cursor_bridge",
                reason="Cursor bridge handoff prepared under governed review-only scope.",
                authority_trace=authority_trace,
                governance_trace=cursor_bridge_summary.get("governance_trace"),
            ),
            "cursor_bridge_summary": {
                **cursor_bridge_summary,
                "bridge_status": "prepared",
                "bridge_phase": CURSOR_BRIDGE_PHASE,
                "authority_scope": "generation_bridge_only",
                "execution_enabled": False,
                "handoff_required": True,
            },
        },
    )
