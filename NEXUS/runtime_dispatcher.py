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
    build_runtime_execution_result,
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

    # AEGIS MVP (Phase 7): policy enforcement gate before any adapter call.
    try:
        from AEGIS.aegis_core import evaluate_action_safe

        project_path = (dispatch_plan.get("project") or {}).get("project_path")
        exec_block = (dispatch_plan or {}).get("execution") or {}

        aegis_request = {
            "project_name": (dispatch_plan.get("project") or {}).get("project_name"),
            "project_path": project_path,
            "runtime_target_id": runtime_target_id,
            "requires_human_approval": bool(exec_block.get("requires_human_approval", False)),
            "action": "adapter_dispatch_call",
        }

        aegis_res = evaluate_action_safe(request=aegis_request)
        aegis_decision = str(aegis_res.get("aegis_decision") or "allow").strip().lower()
        aegis_reason = str(aegis_res.get("aegis_reason") or "")
        aegis_scope = str(aegis_res.get("aegis_scope") or "runtime_dispatch_only").strip().lower()

        if aegis_decision == "deny":
            blocked = build_runtime_execution_result(
                runtime=runtime_target_id,
                status="blocked",
                message=f"AEGIS({aegis_scope}) deny: {aegis_reason or 'Policy denied action.'}",
                execution_status="blocked",
                execution_mode="safe_simulation",
                next_action="human_review",
                artifacts=[],
                errors=[{"reason": f"{aegis_scope}: {aegis_reason or 'aegis_deny'}"}],
            )
            return {
                "dispatch_status": "blocked",
                "runtime_target": runtime_target_id,
                "dispatch_result": blocked,
            }

        if aegis_decision == "approval_required":
            queued = build_runtime_execution_result(
                runtime=runtime_target_id,
                status="skipped",
                message=f"AEGIS({aegis_scope}) approval_required: {aegis_reason or 'Human approval required.'}",
                execution_status="queued",
                execution_mode="manual_only",
                next_action="human_review",
                artifacts=[],
                errors=[{"reason": f"{aegis_scope}: {aegis_reason or 'aegis_approval_required'}"}],
            )
            return {
                "dispatch_status": "skipped",
                "runtime_target": runtime_target_id,
                "dispatch_result": queued,
            }
    except Exception:
        # Fail-safe: if AEGIS fails, do not block execution.
        pass
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
