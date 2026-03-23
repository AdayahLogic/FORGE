"""
NEXUS Cursor runtime adapter.

Simulated dispatch only; no real execution.
"""

from __future__ import annotations

from typing import Any

from NEXUS.authority_model import evaluate_component_authority_safe
from NEXUS.runtime_execution import build_runtime_execution_result

def dispatch(dispatch_plan: dict[str, Any]) -> dict[str, Any]:
    """Simulate dispatch to Cursor runtime. Returns status and message."""
    authority_trace = evaluate_component_authority_safe(
        component_name="cursor_bridge",
        requested_actions=["prepare_ide_handoff", "package_generation_output"],
        authority_context={"runtime_target_id": "cursor"},
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
