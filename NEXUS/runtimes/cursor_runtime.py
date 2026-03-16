"""
NEXUS Cursor runtime adapter.

Simulated dispatch only; no real execution.
"""

from __future__ import annotations

from typing import Any

from NEXUS.runtime_execution import build_runtime_execution_result

def dispatch(dispatch_plan: dict[str, Any]) -> dict[str, Any]:
    """Simulate dispatch to Cursor runtime. Returns status and message."""
    return build_runtime_execution_result(
        runtime="cursor",
        status="accepted",
        message="Task routed to cursor runtime (simulated).",
        execution_status="simulated_execution",
        execution_mode="safe_simulation",
        next_action="human_review",
    )
