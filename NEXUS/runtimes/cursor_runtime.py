"""
NEXUS Cursor runtime adapter.

Simulated dispatch only; no real execution.
"""

from __future__ import annotations

from typing import Any

from NEXUS.authority_model import enforce_component_authority_safe
from NEXUS.runtime_execution import build_runtime_execution_result

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
                "cursor_bridge_summary": {
                    "bridge_status": "planned_only",
                    "bridge_phase": "phase_16_scaffold",
                    "authority_scope": "generation_bridge_only",
                    "execution_enabled": False,
                    "handoff_required": True,
                },
            },
        )
    return build_runtime_execution_result(
        runtime="cursor",
        status="accepted",
        message="Task routed to cursor runtime (simulated).",
        execution_status="simulated_execution",
        execution_mode="safe_simulation",
        next_action="human_review",
        extra_fields={
            "authority_trace": authority_trace,
            "cursor_bridge_summary": {
                "bridge_status": "planned_only",
                "bridge_phase": "phase_16_scaffold",
                "authority_scope": "generation_bridge_only",
                "execution_enabled": False,
                "handoff_required": True,
            },
        },
    )
