"""
NEXUS runtime dispatch system.

Reads dispatch_plan, selects runtime adapter, and returns dispatch result.
Simulation only; no real execution.
"""

from __future__ import annotations

from typing import Any

from NEXUS.runtimes import RUNTIME_ADAPTERS
from NEXUS.runtime_execution import (
    build_runtime_execution_error,
    build_runtime_execution_skipped,
)


def dispatch(dispatch_plan: dict[str, Any]) -> dict[str, Any]:
    """
    Dispatch plan to the selected runtime adapter.

    If ready_for_dispatch is False, returns skipped.
    Otherwise chooses adapter by runtime_target_id, calls it, returns result.
    """
    exec_block = (dispatch_plan or {}).get("execution") or {}
    runtime_target_id = (exec_block.get("runtime_target_id") or "").strip().lower()

    if not dispatch_plan or not dispatch_plan.get("ready_for_dispatch", False):
        skipped = build_runtime_execution_skipped(
            runtime=runtime_target_id or "local",
            message="Dispatch skipped: dispatch plan not ready.",
            reason="not_ready",
        )
        return {
            "dispatch_status": "skipped",
            "runtime_target": runtime_target_id,
            "dispatch_result": skipped,
        }

    if not runtime_target_id:
        runtime_target_id = "local"

    adapter = RUNTIME_ADAPTERS.get(runtime_target_id)
    if not adapter:
        no_adapter = build_runtime_execution_skipped(
            runtime=runtime_target_id,
            message=f"No adapter for runtime '{runtime_target_id}' (simulated).",
            reason="no_adapter",
        )
        # keep status vocabulary aligned: top-level no_adapter, nested no_adapter
        no_adapter["status"] = "no_adapter"
        no_adapter["execution_mode"] = "manual_only"
        no_adapter["next_action"] = "human_review"
        return {
            "dispatch_status": "no_adapter",
            "runtime_target": runtime_target_id,
            "dispatch_result": no_adapter,
        }
    try:
        dispatch_result = adapter(dispatch_plan)
        # Adapters already return normalized schema in Step 59; enforce minimal keys just in case.
        if not isinstance(dispatch_result, dict):
            dispatch_result = build_runtime_execution_error(
                runtime=runtime_target_id,
                message="Adapter returned non-dict result.",
                error=str(type(dispatch_result)),
            )
        return {
            "dispatch_status": "accepted",
            "runtime_target": runtime_target_id,
            "dispatch_result": dispatch_result,
        }
    except Exception as e:
        err = build_runtime_execution_error(
            runtime=runtime_target_id,
            message="Dispatch adapter error.",
            error=str(e),
        )
        return {
            "dispatch_status": "error",
            "runtime_target": runtime_target_id,
            "dispatch_result": err,
        }
